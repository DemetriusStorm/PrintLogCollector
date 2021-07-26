"""Менеджер контекста базы данных."""

import pyodbc
from pyodbc import InterfaceError, OperationalError, ProgrammingError


class ConnectionErrorDB(Exception):
    pass


class CredentialsErrorDB(Exception):
    pass


class SQLError(Exception):
    pass


pyodbc.pooling = False


class UseDatabase:
    def __init__(self, config: str) -> None:
        self.configuration = config

    def __enter__(self) -> 'cursor':
        try:
            self.conn = pyodbc.connect(self.configuration, attrs_before={}, timeout=1)
            self.cursor = self.conn.cursor()
            return self.cursor
        except OperationalError as err:
            raise ConnectionErrorDB(err)
        except InterfaceError as err:
            raise ConnectionErrorDB(err)
        except ProgrammingError as err:
            raise CredentialsErrorDB(err)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

        if exc_type is ProgrammingError:
            raise SQLError(exc_val)
        elif exc_type:
            raise SQLError(exc_val)
