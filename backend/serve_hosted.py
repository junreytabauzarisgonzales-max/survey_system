"""Serve the combined hosted build locally with the real Neon environment."""
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from .hosted import create_handler


if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8765'))
    web_root = Path(__file__).resolve().parent.parent / 'web' / 'dist'
    server = ThreadingHTTPServer((host, port), create_handler(os.environ, web_root))
    print(f'Hosted survey app listening on http://{host}:{port}')
    try:
        server.serve_forever()
    finally:
        server.server_close()
