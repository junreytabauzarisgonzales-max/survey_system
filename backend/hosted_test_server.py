"""Isolated PostgreSQL-backed preview for the combined hosted browser tests."""
import atexit
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql

from .db import new_id
from .hosted import create_handler


if __name__ == '__main__':
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        raise SystemExit('Set TEST_POSTGRES_URL to an isolated test database, not your production database.')
    schema = 'survey_browser_' + new_id().replace('-', '')
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

    def cleanup():
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    atexit.register(cleanup)
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query))
    query['options'] = '-csearch_path=' + schema
    target = urlunsplit(parsed._replace(query=urlencode(query)))
    root = Path(__file__).resolve().parent.parent / 'web' / 'dist'
    server = ThreadingHTTPServer(('127.0.0.1', 8766), create_handler({'DATABASE_URL': target}, root))
    try:
        server.serve_forever()
    finally:
        server.server_close()
