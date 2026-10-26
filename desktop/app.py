"""Run with python -m desktop.app, or build using desktop/build.ps1."""
import base64
import logging
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend.db import backup, migrate
from backend.server import handler_for
from backend.service import Service


def data_directory():
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return root / 'StudentSurveyCreator'


class DeviceFiles:
    def __init__(self, database):
        self._database = Path(database)
        self._window = None

    def storage_info(self):
        return {'database': str(self._database), 'mode': 'local'}

    def save_file(self, name, content):
        import webview
        destination = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=Path(name).name)
        if not destination:
            return False
        target = Path(destination if isinstance(destination, str) else destination[0])
        if target.resolve() == self._database.resolve():
            raise ValueError('Choose a different filename from the active database.')
        target.write_bytes(base64.b64decode(content, validate=True))
        return True

    def save_backup(self):
        import webview
        destination = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename='survey-backup.sqlite')
        if not destination:
            return False
        target = Path(destination if isinstance(destination, str) else destination[0])
        if target.resolve() == self._database.resolve():
            raise ValueError('A backup cannot replace the active database.')
        backup(self._database, target)
        return True


def create_server(database, web_root):
    migrate(database)
    base = handler_for(Service(str(database)), web_root)

    class LocalHandler(base):
        def route(self):
            # Accept requests only addressed to this instance's loopback origin.
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                return self.result({'error': 'Invalid local origin'}, 403)
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                return self.result({'error': 'Invalid local origin'}, 403)
            return super().route()

    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalHandler)
    server.daemon_threads = True
    return server


def main():
    import webview
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=directory / 'desktop.log', level=logging.INFO)
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    web_root = root / 'web' / 'app-dist'
    if not (web_root / 'index.html').is_file():
        raise RuntimeError('Build the interface first: run npm ci and npm run build:app in web/.')
    database = directory / 'surveys.sqlite'
    server = create_server(database, web_root)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    files = DeviceFiles(database)
    try:
        files._window = webview.create_window(
            'Student Survey Creator — Local device',
            f'http://127.0.0.1:{server.server_port}',
            js_api=files, width=1280, height=860, min_size=(800, 600))
        webview.start(private_mode=True, gui='edgechromium' if sys.platform == 'win32' else None)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == '__main__':
    main()
