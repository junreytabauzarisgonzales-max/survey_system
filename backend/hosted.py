"""Lazy, environment-configured backend for Vercel's Python function runtime."""
import hashlib
import os
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from .db import connect, is_postgres, migrate
from .model import require
from .neon_services import NeonAuth, ObjectStorage
from .server import handler_for
from .service import Service

BODY_LIMIT = 4 * 1024 * 1024
ATTACHMENT_LIMIT = 2 * 1024 * 1024


def create_handler(environment=None, web_root=None):
    environment = os.environ if environment is None else environment
    ready = None
    lock = threading.Lock()

    def service():
        nonlocal ready
        if ready is None:
            with lock:
                if ready is None:
                    url = environment.get('DATABASE_URL', '')
                    require(is_postgres(url), 'Hosted database is not configured. Set DATABASE_URL to your Neon PostgreSQL connection URL.', 503)
                    if environment.get('AUTO_MIGRATE', '1') == '1':
                        migrate(environment.get('DATABASE_URL_UNPOOLED') or url)
                    ready = Service(url, attachment_limit=ATTACHMENT_LIMIT,
                                    auth=NeonAuth.from_env(environment),
                                    storage=ObjectStorage.from_env(environment))
        return ready

    class ServiceProxy:
        def __getattr__(self, name):
            return getattr(service(), name)

    def rate_limit(key, maximum):
        stamp = int(time.time())
        bucket = hashlib.sha256(key.encode()).hexdigest()
        with connect(service().path) as connection:
            # Atomic fixed windows are shared by all warm/cold function instances.
            row = connection.execute(
                'INSERT INTO request_limits(bucket,started_at,hits) VALUES(?,?,1) '
                'ON CONFLICT(bucket) DO UPDATE SET '
                'started_at=CASE WHEN request_limits.started_at<=? THEN excluded.started_at ELSE request_limits.started_at END, '
                'hits=CASE WHEN request_limits.started_at<=? THEN 1 ELSE request_limits.hits+1 END RETURNING hits',
                (bucket, stamp, stamp - 60, stamp - 60)).fetchone()
            if secrets.randbelow(100) == 0:
                connection.execute('DELETE FROM request_limits WHERE started_at<?', (stamp - 120,))
            return row['hits'] <= maximum

    base = handler_for(ServiceProxy(), web_root, rate_limiter=rate_limit, trust_proxy=True,
                       max_body_bytes=BODY_LIMIT, max_response_bytes=BODY_LIMIT)

    class Handler(base):
        def route(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            # Explicitly carry the API path through Vercel's catch-all rewrite.
            route = query.pop('__path', None)
            if route is not None:
                self.path = '/api/' + route[-1].strip('/')
                if query:
                    self.path += '?' + urlencode(query, doseq=True)
            request_path = urlsplit(self.path).path
            if web_root is not None and not request_path.startswith('/api/'):
                target = '/app/index.html' if request_path in ('/app', '/app/') or request_path.startswith('/survey/') else request_path
                return self.serve_web(target)
            configured = service()
            if urlsplit(self.path).path == '/api/health' and self.command == 'GET':
                with connect(configured.path) as connection:
                    connection.execute('SELECT 1').fetchone()
                return self.result({'status': 'ok', 'database': 'postgresql',
                                    'services': {'auth': bool(configured.auth), 'object_storage': bool(configured.storage),
                                                 'realtime': bool(environment.get('NEON_REALTIME_URL'))},
                                    'limits': {'request_bytes': BODY_LIMIT, 'attachment_bytes': ATTACHMENT_LIMIT, 'response_bytes': BODY_LIMIT}})
            return super().route()

    return Handler
