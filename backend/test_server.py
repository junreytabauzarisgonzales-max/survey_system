"""Isolated browser-test server; never points at the real research database."""
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from .db import bootstrap, migrate
from .server import handler_for
from .service import Service

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='agal-browser-') as directory:
        db = str(Path(directory) / 'test.sqlite')
        migrate(db)
        bootstrap(db, 'browser@example.test', 'browser-test-password')
        ThreadingHTTPServer(('127.0.0.1', 8765), handler_for(Service(db), Path(__file__).parent.parent / 'web' / 'app-dist')).serve_forever()
