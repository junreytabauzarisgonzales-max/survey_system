"""PostgreSQL adapter for the service's parameterized SQL and row interface.

Imported only for PostgreSQL URLs; offline SQLite installations need no driver.
"""
import re
import sqlite3
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        return (Row(row) for row in self._cursor)


def sql_parameters(sql):
    """Convert only unquoted qmark parameters; preserve SQL string literals."""
    pieces = re.split(r"('(?:''|[^'])*')", sql.replace('%', '%%'))
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(r'\browid\b', '_sequence', pieces[index]).replace('?', '%s')
    # psycopg requires literal percent signs to be doubled when binding parameters.
    return ''.join(pieces)


class Connection:
    def __init__(self, url):
        try:
            self.raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10,
                                       prepare_threshold=None)
        except psycopg.OperationalError:
            # Never expose connection strings or credentials through error responses/logs.
            raise ConnectionError('PostgreSQL connection unavailable') from None

    def execute(self, sql, parameters=()):
        try:
            if sql.strip().upper() == 'BEGIN IMMEDIATE':
                # Match SQLite's serialized read/check/write transactions across
                # all Vercel instances, including idempotency and revision checks.
                return Cursor(self.raw.execute('SELECT pg_advisory_xact_lock(724116901)'))
            if sql.strip().upper() == 'BEGIN':
                return Cursor(self.raw.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            query = sql_parameters(sql)
            arguments = tuple(int(value) if isinstance(value, bool) else value for value in parameters)
            return Cursor(self.raw.execute(query, arguments))
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('Conflicting identifier or immutable record') from None

    def iterate(self, sql, parameters=()):
        """Server-side cursor: CSV data is fetched in bounded batches."""
        with self.raw.cursor(name='survey_export') as cursor:
            cursor.itersize = 100
            cursor.execute(sql_parameters(sql), tuple(parameters))
            for row in cursor:
                yield Row(row)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.raw.rollback() if kind else self.raw.commit()
        finally:
            self.raw.close()


def migrate(url):
    from .db import now
    with Connection(url) as connection:
        connection.raw.execute('SELECT pg_advisory_xact_lock(724116902)')
        connection.raw.execute('CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for script in sorted((Path(__file__).parent / 'postgres_migrations').glob('*.sql')):
            if not connection.execute('SELECT 1 FROM migrations WHERE name=?', (script.name,)).fetchone():
                connection.raw.execute(script.read_text(encoding='utf-8'), prepare=False)
                connection.execute('INSERT INTO migrations VALUES(?,?)', (script.name, now()))
