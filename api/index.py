"""Single Vercel Python function; no database connection is made during import."""
from backend.hosted import create_handler

handler = create_handler()
