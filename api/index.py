"""Single Vercel Python function; no database connection is made during import."""
from backend.hosted import create_handler


class handler(create_handler()):
    pass
