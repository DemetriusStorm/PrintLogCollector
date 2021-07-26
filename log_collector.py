import os
import json
from datetime import datetime, timezone

import configparser
import logging
from logging.config import fileConfig

import xmltodict

from dbcm import (
    UseDatabase,
    ConnectionErrorDB, CredentialsErrorDB, SQLError,
)
from constants import (
    FILE_IS_OPEN, DB_IS_AVAILABLE, EXC_INFO_TRACEBACK,
)

import sys
import socket
import win32event
import win32service
import win32serviceutil
import servicemanager

import base64

from winevt import EventLog

"""
Технические указание на будущее:
=================================================================================
(__file__) fails in "frozen" programs (created using py2exe, PyInstaller, cx_Freeze).
(sys.argv[0]) is work!
PyInstaller: Компиляция скрипта должна происходить не в .env,
             все пакеты и зависимости должны быть установлены глобально!
pyinstaller --clean --hiddenimport=win32timezone -F log_collector.py
=================================================================================
"""
# Рабочая версия смены каталога, работает только когда приложение запущено в режиме службы!
work_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
os.chdir(work_dir)
# Настройка путей к конфигурациям logger и app
config_app_path = os.path.join(work_dir, 'PrintLogCollector_config.ini')
config_logger_path = os.path.join(work_dir, 'logging_config.ini')
# Настройка конфига app
config_parser = configparser.ConfigParser()
config_parser.read(config_app_path)
# Достаем данные из файла конфигурации
database_host = config_parser['mssql']['server']
database_name = config_parser['mssql']['database']
database_user = config_parser['mssql']['user']
database_pwd = 'fail_password'
try:
    database_pwd = base64.b64decode(config_parser['mssql']['pass'].encode('utf-8').decode('utf-8')).decode('utf-8')
except Exception as err_decode:
    print(f'Не удалось декодировать пароль, вероятно, в значение были внесены изменения: {err_decode}')

bookmark_directory = config_parser['printlogcollector']['bookmark_directory']
bookmark_filename = config_parser['printlogcollector']['bookmark_filename']
log_directory = config_parser['printlogcollector']['log_directory']
log_filename = config_parser['printlogcollector']['log_filename']
# Инициализация директории хранения логов.
log_dir = os.path.join(work_dir, log_directory)
# Проверяем наличие директории для архива импортированных файлов.
if not os.path.exists(log_dir):
    os.mkdir(log_dir)

try:
    fileConfig(config_logger_path, defaults={f'logfilename': os.path.join(work_dir, log_directory, log_filename)})
except Exception as exc:
    print(exc)

logger = logging.getLogger()
logger_connect = logging.getLogger('info')
logger_db_insert = logging.getLogger('db_insert')
logger_file_insert = logging.getLogger('file_insert')

config = {'DRIVER={ODBC Driver 17 for SQL Server};',
          f'SERVER={database_host};',
          f'DATABASE={database_name};',
          f'UID={database_user};',
          f'PWD={database_pwd};',
          }

# Инициализация пути файла состояний.
path_flag_states = os.path.join(work_dir, 'states.json')
"""Значение флагов по умолчанию для определение состояния в первый запуск программы.
Подключение констант может происходить в нескольких ситуациях:
1. В случае первого запуска программы, когда еще не сохранен json с текущим состоянием программы
2. В случае, если отсутствует (был удалён по какой то причине) файл json."""
if not os.path.isfile(path_flag_states):
    try:
        logger.debug(f'Первый запуск программы, пробуем сохранить состояние программы значениями по умолчанию.')
        with open(path_flag_states, 'w') as save_states:
            json.dump(
                {'_FILE_IS_OPEN': FILE_IS_OPEN,  # Флаг работы с файлом, по умолчанию файл закрыт.
                 '_DB_IS_AVAILABLE': DB_IS_AVAILABLE,  # Флаг работы с базой, по умолчанию БД доступна.
                 '_EXC_INFO_TRACEBACK': EXC_INFO_TRACEBACK,  # Флаг работы с исключениями, по умолчанию выключен.
                 }, save_states)
            logger.debug(f'Сохранили текущее состояние программы.')
    except Exception as exc_dump:
        logger.critical(f'Текущее состояние программы сохранить не удалось, по причине {exc_dump}')


def change_current_state(new_states: dict):
    """Изменение текущего состояние флагов."""
    if os.path.isfile(path_flag_states):
        # Создадим новый словарь с текущими состояниями и запишем их в файл states.json
        new_states_flag = dict(load_state_app(), **new_states)
        try:
            with open(os.path.join(work_dir, 'states.json'), 'w') as output:
                json.dump(new_states_flag, output)
        except Exception as save_dump_err:
            logger.critical(f'Текущее состояние программы сохранить не удалось, по причине {save_dump_err}')


def load_state_app() -> dict:
    """Загрузка файла state.json с состоянием флагов."""
    try:
        with open(os.path.join(work_dir, 'states.json'), 'r') as fp:
            current_state = json.load(fp)
            return current_state
    except Exception as load_err:
        logger.critical(f'Текущее состояние программы загрузить не удалось, по причине {load_err}')


def bookmark_event(incoming_event):
    """Запись потока в файл, в случае отсутствия связи с БД."""
    logger.debug(f'Инициирована запись данных в файл по причине ошибки обращения к БД.')
    try:
        def add_bookmark(event: str) -> None:
            with open(bookmark_filename, 'a') as bookmark_in:
                bookmark_in.write(f'{event}\n')
                logger.debug(f'Данные записаны в файл: {str(event)}')

        # Необходимо перед записью Event в bookmark.xml проверить наличие Event в файле.
        # Ситуация, с уже существующей Event в файле, может произойти если при считывании Event из файла
        # произошла ошибка обращения к БД, текущая Event может попасть в файл повторно. (почему?)
        if os.path.isfile(bookmark_filename):
            with open(bookmark_filename, 'r') as bm_file:
                for num, current_event in enumerate(bm_file.readlines(), start=1):
                    # Сверяем EventRecordID текущей и переданной Event.
                    parsed_event = parse_event_xml(current_event)
                    current_eventrecordid = parsed_event.get('Event').get('System').get('EventRecordID')
                    # Если совпал, уведомляем в лог о дубле и прерываемся.
                    parsed_incoming_event = parse_event_xml(incoming_event)
                    if current_eventrecordid == parsed_incoming_event.get('Event').get('System').get('EventRecordID'):
                        logger.debug(
                            f'EventRecordID из потока "{current_eventrecordid}" уже присутствует в файле, строка #{num}'
                        )
                        break
                else:
                    add_bookmark(incoming_event)  # Если совпадения нет, добавляем Event в файл.
        else:
            add_bookmark(incoming_event)
    except (FileExistsError, FileNotFoundError) as err_exist:
        logger.error(f'Ошибка файловой операции: {err_exist}')
    except Exception as err_exc:
        logger.error(f'Что-то пошло не так: {err_exc}')


def dt_translate_and_format(utc_dt: str) -> str:
    """
    Конвертация даты/времени формата '%Y-%m-%dT%H:%M:%S.fZ' из UTC 00Z в текущее время с локальным часовым поясом.
    Данные подготовлены сразу для импорта в БД.
    Для загрузки xml данных конвертированных из ручной выгрузки Event, формат даты SystemTime отличается
    от формата по прямому запросу к журналу. '%Y-%m-%d %H:%M:%S.f'. Сделаем выборку.
    """
    if 'T' in utc_dt:
        convert_to_dt = datetime.strptime(utc_dt[:19], '%Y-%m-%dT%H:%M:%S')
    else:
        convert_to_dt = datetime.strptime(utc_dt[:19], '%Y-%m-%d %H:%M:%S')
    local_dt = convert_to_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_event_xml(event: str) -> 'OrderedDict':
    return xmltodict.parse(event,
                           process_namespaces=True,
                           namespaces={'http://schemas.microsoft.com/win/2004/08/events/event': None,
                                       'http://manifests.microsoft.com/win/2005/08/windows/printing/'
                                       'spooler/core/events': None})


def load_bookmark(action: str, pContext: str):
    """Импорт данных из временного хранилища в БД."""
    change_current_state({'_FILE_IS_OPEN': True})  # Поднимаем флаг работы с файлом.
    bookmark_dir = os.path.join(work_dir, bookmark_directory)
    # Проверяем наличие директории для архива импортированных файлов.
    if not os.path.exists(bookmark_dir):
        os.mkdir(bookmark_dir)
    try:
        # Проверяем наличие bookmark.xml, если есть, пробуем обработать через стандартный handle_event.
        if os.path.isfile(bookmark_filename):
            logger.debug(f'С прошлой сессии обнаружен {bookmark_filename}, будет произведен импорт данных в БД.')
            with open(bookmark_filename, 'r') as bm_file:
                logger.debug(f'Файл {bookmark_filename} открыт.')
                for num, event in enumerate(bm_file.readlines(), start=1):
                    logger_db_insert.debug(f'Запись #{num} отправлена на загрузку.')
                    handle_event(action, pContext, event)

            logger_db_insert.debug(f'Все Events из {bookmark_filename} обработаны.')
            name, ext = bookmark_filename.split('.')
            bookmark_new = datetime.now().strftime(f'{name}_%Y%m%d%H%M%S%f_imported.{ext}')
            os.rename(bookmark_filename, os.path.join(bookmark_dir, bookmark_new))
            logger.debug(
                f'Файл {bookmark_filename} переименован и перемещен в архив {os.path.join(bookmark_dir, bookmark_new)}.'
            )
    except (FileExistsError, FileNotFoundError):
        pass
    except Exception as err_exc:
        logger.error(f'Возникло исключение при обработке {bookmark_filename}: {err_exc}')
    finally:
        # В любом случае опускаем флаг работы с файлом. Файл снова доступен для работы других процессов.
        change_current_state({'_FILE_IS_OPEN': False})


def handle_except(error_msg: str) -> None:
    _traceback = load_state_app()
    if not _traceback['_EXC_INFO_TRACEBACK']:
        logger_connect.error(error_msg)
    change_current_state({
        '_DB_IS_AVAILABLE': False,  # Опускаем флаг доступности базы.
        '_EXC_INFO_TRACEBACK': True,  # Поднимаем флаг, текущее исключение активно.
    })


def handle_event(action: str, pContext: str, event) -> None:
    """Основной метод обработки потока данных."""
    event_xml_dump = event
    # Пробуем снять дамп в xml с обработкой исключения, на случай, если переданы данные из bookmark.xml,
    # исключение сработает, т.к. данные уже в формате xml и конвертация не требуется.
    try:
        event_xml_dump = event_xml_dump.xml
    except Exception:
        pass

    # Если файл (существует И не используется) И база доступна - загружаем данные в БД.
    current_states = load_state_app()
    if (os.path.isfile(bookmark_filename) and not current_states['_FILE_IS_OPEN']) \
            and current_states['_DB_IS_AVAILABLE']:
        load_bookmark(action, pContext)

    parsed_event = parse_event_xml(event_xml_dump)

    dtcreated = dt_translate_and_format(
        str(parsed_event.get('Event').get('System').get('TimeCreated').get('@SystemTime'))
    )
    eventrecordid = parsed_event.get('Event').get('System').get('EventRecordID')
    printserver = str(parsed_event.get('Event').get('System').get('Computer')).lower()
    document = parsed_event.get('Event').get('UserData').get('DocumentPrinted').get('Param2')
    document = 'Неизвестный документ.' if document is None else str(document)[:221]
    username = str(parsed_event.get('Event').get('UserData').get('DocumentPrinted').get('Param3')).lower()
    computer = str(parsed_event.get('Event').get('UserData').get('DocumentPrinted').get('Param4')).lower()
    computer = computer[2:] if '\\' in computer else computer
    printer = str(parsed_event.get('Event').get('UserData').get('DocumentPrinted').get('Param5')).lower()
    count = parsed_event.get('Event').get('UserData').get('DocumentPrinted').get('Param8')

    try:
        with UseDatabase(''.join(config)) as cursor:
            change_current_state({
                '_DB_IS_AVAILABLE': True,  # Поднимаем флаг. БД доступна.
                '_EXC_INFO_TRACEBACK': False,  # Опускаем флаг. Исключений больше нет.
            })

            _SQL = """INSERT INTO Logs
                              (DTCREATED, DATECREATED, TIMECREATED, EVENTRECORDID, PRINTSERVER,
                              DOCNAME, USERNAME, COMPUTER, PRINTER, COUNT)
                              VALUES
                              (?,?,?,?,?,?,?,?,?,?)"""
            _CHECK_DOUBLES = f"""
                SELECT * FROM Logs WHERE eventrecordid={eventrecordid} AND printserver=LOWER('{printserver}')
                """
            logs = [dtcreated, eventrecordid, computer, printer, username]
            # Проверяем данные в базе на совпадение по (eventrecordid and printserver),
            # так как eventrecordid в разрезе всей компании НЕ уникален!
            cursor.execute(_CHECK_DOUBLES)
            contents = cursor.fetchall()
            _date, _time = dtcreated[:10], dtcreated[11:]
            if not contents:  # Если совпадения не найдены, выполняем вставку Event в БД.
                cursor.execute(_SQL, [dtcreated,
                                      _date,
                                      _time,
                                      eventrecordid,
                                      printserver,
                                      document,
                                      username,
                                      computer,
                                      printer,
                                      count, ])
                logger_connect.info(logs)
            else:
                # Иначе говорим, что поймали двойника и показываем оригинал из БД.
                logger_db_insert.debug(
                    f'Обнаружена попытка импорта дублирующей записи. Запрос на импорт отклонен: {contents}'
                )
    except ConnectionErrorDB as err_conn:
        handle_except(error_msg=f'База данных включена? Ошибка: {err_conn}')
        bookmark_event(event_xml_dump)  # Записываем Event в файл для хранения, пока БД не доступна.
    except CredentialsErrorDB as err_cred:
        handle_except(error_msg=f'Проблемы с идентификатором пользователь/пароль.. Ошибка: {err_cred}')
        bookmark_event(event_xml_dump)
    except SQLError as err_sql:
        handle_except(error_msg=f'Ошибка в запросе: {err_sql}')
        bookmark_event(event_xml_dump)
    except Exception as err_exc:
        handle_except(error_msg=f'Что-то пошло не так: {err_exc}')
        bookmark_event(event_xml_dump)


class PrintLogCollector(win32serviceutil.ServiceFramework):
    _svc_name_ = 'PrintLogCollector'
    _svc_display_name_ = 'PrintLogCollector'
    _svc_description_ = """Служба сбора данных журнала Microsoft-Windows-PrintService/Operational."""

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        logger.debug(f'*** Служба остановлена. ***')

    def SvcShutdown(self):
        logger.debug(f'*** Отправлена команда на выключение или перезагрузку сервера. ***')
        self.SvcStop()

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ''))
        try:
            if os.path.isfile(config_app_path):
                pass
        except Exception as exc_run:
            logging.critical(f'*** Конфиг программы {_svc_name}_config.ini не обнаружен {exc_run} ***')
            logging.info('*** Пожалуйста, запустите log_collector.exe в консоли и ознакомьтесь с инструкцией. ***')
            self.SvcStop()
        logger.debug(f'*** Служба запущена. ***')
        load_state_app()
        self.main()
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

    def main(self):
        logger.debug(f'Start handler {_svc_name} {current_ver}.')
        # Запускаем основной handle event
        cb = EventLog.Subscribe('Microsoft-Windows-PrintService/Operational',
                                'Event/System[EventID=307]',
                                handle_event,
                                )


if __name__ == '__main__':
    _svc_name = 'PrintLogCollector'
    current_ver = 'v1.1.230721'
    from pywintypes import error

    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintLogCollector)
        try:
            servicemanager.StartServiceCtrlDispatcher()
        except error as err:
            print(f'PrintLogCollector {current_ver}')
            print("""
Вы запустили эту программу из консоли, за дополнительной информацией обращайтесь к файлу readme.txt
Данная программа должна быть запущена в качестве Службы 'WINDOWS SERVICE'.
          
log_collector.exe [options] install|update|remove|start|stop""")
    else:
        win32serviceutil.HandleCommandLine(PrintLogCollector)
