import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from backend.hosted import create_handler


class HostedConfigurationTest(unittest.TestCase):
    def test_unconfigured_host_returns_503_without_falling_back_to_sqlite(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), create_handler({}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as failure:
                urlopen(f'http://127.0.0.1:{server.server_port}/api/index?__path=health')
            self.assertEqual(failure.exception.code, 503)
            self.assertIn('DATABASE_URL', json.load(failure.exception)['error'])
            failure.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
