"""Apply migrations using DATABASE_URL without putting credentials in arguments."""
import os

from .db import is_postgres, migrate


def main():
    url = os.environ.get('DATABASE_URL_UNPOOLED') or os.environ.get('DATABASE_URL', '')
    if not is_postgres(url):
        raise SystemExit('Set DATABASE_URL or DATABASE_URL_UNPOOLED to your PostgreSQL connection URL first.')
    migrate(url)
    print('PostgreSQL migrations applied successfully.')


if __name__ == '__main__':
    main()
