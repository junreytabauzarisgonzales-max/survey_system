import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.db import backup, connect
from desktop.app import create_server


class LocalDesktopTest(unittest.TestCase):
    def test_local_persistence_backup_and_origin_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'surveys.sqlite'
            server = create_server(database, Path(__file__).resolve().parents[2] / 'web' / 'app-dist')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                data = json.dumps({'name': 'Local owner', 'email': 'local@example.org',
                                   'password': 'local-password-123'}).encode()
                with urlopen(Request(base + '/api/register', data=data,
                                     headers={'Content-Type': 'application/json'})) as response:
                    session = json.load(response)
                payload = json.dumps({'name': 'Saved on this PC', 'description': 'Offline survey'}).encode()
                with urlopen(Request(base + '/api/projects', data=payload,
                                     headers={'Authorization': 'Bearer ' + session['token'],
                                              'Content-Type': 'application/json'})) as response:
                    project = json.load(response)
                for headers in ({'Host': 'untrusted.example'}, {'Origin': 'https://untrusted.example'}):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base + '/api/health', headers=headers))
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
                archive = Path(directory) / 'backup.sqlite'
                backup(database, archive)
                with connect(archive) as conn:
                    self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                    self.assertEqual(conn.execute('SELECT name FROM projects WHERE id=?', (project['id'],)).fetchone()[0], 'Saved on this PC')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            # Opening a new desktop instance preserves the original records.
            reopened = create_server(database, directory)
            reopened.server_close()
            with connect(database) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
