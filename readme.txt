Служба оформляет подписку к событиям журнала Microsoft-Windows-PrintService/Operational
---
Обновлять программу можно только из консоли запущенной с правами администратора!
---
Данная программа должна быть запущена в качестве Службы 'WINDOWS SERVICE'.
Программа принимает один из следующих аргументов:

log_collector.exe [options] install|update|remove|start|stop
Что делает - понятно: установка, обновление, удаление, запуск, остановка.

В рабочем каталоге с программой должны находиться два конфигурационных файла:
Конфиг логирования logging_config.ini (поставляется с программой)
Конфиг программы PrintLogCollector_config.ini (поставляется с программой)
[mssql]         ;DB MSSQL server settings
server=         'my_server'     Имя сервера базе данных
database=       'my_db'         Имя базы
user=           'my_username'   Имя пользователя
pass=           'my_password'   Пароль к базе данных
[printlogcollector]
bookmark_directory=ImportedBookmarks    ;Directory to backup imported bookmarks
bookmark_filename=bookmark.xml          ;Save stream to file when DB is not available
log_directory=Logs                      ;Directory to store log files
log_filename=PrintLogCollector.txt      ;Log filename
---
Необходимые компоненты для работы службы должны быть установлены на клиенте.
Microsoft ODBC Driver 17 for SQL Server:
https://www.microsoft.com/ru-ru/download/details.aspx?id=56567

Компонент Microsoft Visual C++ для Visual Studio 2015, 2017 и 2019:
https://support.microsoft.com/ru-ru/help/2977003/the-latest-supported-visual-c-downloads
---
Author: Dmitriy Bulygin <demetrius.storm@gmail.com>
PyCharm 2021.1.3 (Community Edition) / Python 3.8.10 / PyInstaller v4.4
LICENCE GNU GPLv3