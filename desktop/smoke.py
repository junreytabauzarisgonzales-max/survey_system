"""Opt-in native window/bridge smoke check; uses only a temporary database."""
import tempfile
import threading
import time
from pathlib import Path

import webview

from .app import DeviceFiles, create_server


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='survey-desktop-check-') as directory:
        database = Path(directory) / 'surveys.sqlite'
        server = create_server(database, Path(__file__).resolve().parents[1] / 'web' / 'app-dist')
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        files = DeviceFiles(database)
        window = webview.create_window('Desktop verification',
                                      f'http://127.0.0.1:{server.server_port}', js_api=files)
        files._window = window

        def verify():
            try:
                if not window.events.loaded.wait(30):
                    raise RuntimeError('Native window did not load.')
                for _ in range(100):
                    text = window.evaluate_js('document.body.innerText') or ''
                    if 'Your surveys and responses are saved on this PC.' in text:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError('Local desktop interface did not render.')
                methods = window.evaluate_js('Object.keys(window.pywebview.api).sort()')
                if methods != ['save_backup', 'save_file', 'storage_info']:
                    raise RuntimeError(f'Unexpected native methods: {methods}')
                window.evaluate_js('window.pywebview.api.storage_info()', callback=results.append)
                for _ in range(50):
                    if results:
                        break
                    time.sleep(0.1)
                if not results or results[0].get('database') != str(database):
                    raise RuntimeError('Native storage bridge did not respond.')
                results.append('passed')
            except Exception as error:
                results.append(str(error))
            finally:
                window.destroy()

        try:
            webview.start(verify, gui='edgechromium', private_mode=True)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
    if not results or results[-1] != 'passed':
        raise RuntimeError(f'Desktop smoke check failed: {results}')
    print('Native Windows interface and local storage bridge passed.')


if __name__ == '__main__':
    main()
