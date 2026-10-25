"""Run: python -m backend.server --db data/agal.sqlite --port 8000"""
import argparse
import hashlib
import json
import logging
import mimetypes
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .db import backup, bootstrap, connect, migrate, now
from .exports import Export, analytics, analytics_overview
from .model import Problem, require
from .service import Service

LOG = logging.getLogger('agal')


def handler_for(service, web_root=None):
    attempts = {}
    public_attempts = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SurveyCreator/2.0'

        def log_message(self, fmt, *args):
            # Do not log URLs or bodies; query strings may contain sensitive filters.
            LOG.info('%s %s', self.command, args[1] if len(args) > 1 else '')

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_PUT(self):
            self.handle_request()

        def do_DELETE(self):
            self.handle_request()

        def headers_common(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")

        def result(self, data, status=200):
            content = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.headers_common()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def handle_request(self):
            try:
                self.route()
            except Problem as e:
                self.result({'error': str(e)}, e.status)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, KeyError) as e:
                self.result({'error': 'Invalid request: ' + str(e)}, 400)
            except sqlite3.IntegrityError:
                self.result({'error': 'Conflicting identifier or immutable record'}, 409)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOG.exception('Request failed')
                self.result({'error': 'Internal server error'}, 500)

        def route(self):
            parsed = urlparse(self.path)
            path = [p for p in parsed.path.strip('/').split('/') if p]
            if not path or path[0] != 'api':
                return self.serve_web(parsed.path)
            method = self.command
            data = {}
            length = int(self.headers.get('Content-Length', 0))
            if method in ('POST', 'PUT', 'DELETE'):
                if method != 'DELETE' or length:
                    require(0 < length <= 15 * 1024 * 1024, 'Request body must be 1 byte�?"15 MiB', 413)
                    data = json.loads(self.rfile.read(length))
                    require(isinstance(data, dict), 'Request object required')
            if path == ['api', 'health']:
                return self.result({'status': 'ok'})
            if path == ['api', 'login'] and method == 'POST':
                address = self.client_address[0]
                with lock:
                    recent = [t for t in attempts.get(address, []) if t > time.monotonic() - 60]
                    require(len(recent) < 10, 'Too many login attempts; retry in one minute', 429)
                    attempts[address] = recent + [time.monotonic()]
                return self.result(service.login(data))
            if path == ['api', 'register'] and method == 'POST':
                address = 'register:' + self.client_address[0]
                with lock:
                    recent = [t for t in attempts.get(address, []) if t > time.monotonic() - 60]
                    require(len(recent) < 5, 'Too many sign-up attempts; retry in one minute', 429)
                    attempts[address] = recent + [time.monotonic()]
                return self.result(service.register(data))
            if len(path) >= 4 and path[1:3] == ['public', 'surveys']:
                address = (self.client_address[0], method)
                with lock:
                    current = time.monotonic()
                    if address not in public_attempts and len(public_attempts) >= 4096:
                        for key in list(public_attempts):
                            if not public_attempts[key] or public_attempts[key][-1] < current - 60:
                                del public_attempts[key]
                        require(len(public_attempts) < 4096, 'Please try again shortly', 429)
                    recent = [t for t in public_attempts.get(address, []) if t > current - 60]
                    require(len(recent) < (60 if method == 'POST' else 180), 'Too many survey requests; retry in one minute', 429)
                    public_attempts[address] = recent + [current]
                if len(path) == 4 and method == 'GET':
                    return self.result(service.public_survey(path[3]))
                if len(path) == 5 and path[4] == 'responses' and method == 'POST':
                    return self.result(service.submit_public(path[3], data))
                raise Problem('Not found', 404)
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            actor = service.authenticate(token)
            query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            if path == ['api', 'me']:
                return self.result({k: actor[k] for k in ('id', 'name', 'email', 'admin')})
            if path == ['api', 'logout'] and method == 'POST':
                with connect(service.path) as c:
                    c.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
                return self.result({'ok': True})
            if path == ['api', 'users']:
                return self.result(service.create_user(actor, data) if method == 'POST' else service.users(actor))
            if path == ['api', 'templates'] and method == 'GET':
                return self.result(service.templates())
            if len(path) == 4 and path[1] == 'templates' and path[3] == 'apply' and method == 'POST':
                return self.result(service.apply_template(actor, path[2]))
            if path == ['api', 'projects']:
                return self.result(service.save_project(actor, data) if method == 'POST' else service.project_list(actor))
            if len(path) >= 3 and path[1] == 'projects':
                project = path[2]
                if len(path) == 3 and method == 'PUT':
                    return self.result(service.save_project(actor, data, project))
                if len(path) == 3 and method == 'DELETE':
                    return self.result(service.delete_project(actor, project, data))
                if len(path) == 4:
                    resource = path[3]
                    if resource == 'duplicate' and method == 'POST':
                        return self.result(service.duplicate_project(actor, project))
                    if resource == 'forms':
                        return self.result(service.save_form(actor, project, data) if method == 'POST' else service.forms(actor, project))
                    if resource == 'public-links' and method in ('GET', 'POST'):
                        return self.result(service.save_public_link(actor, project, data) if method == 'POST' else service.public_links(actor, project))
                    if resource == 'versions':
                        return self.result(service.versions(actor, project))
                    if resource == 'members':
                        return self.result(service.members(actor, project, data if method == 'PUT' else None))
                    if resource == 'respondents':
                        return self.result(service.save_respondent(actor, project, data) if method == 'POST' else service.respondents(actor, project))
                    if resource == 'interviews':
                        return self.result(service.interviews(actor, project, int(query.get('limit', 200)), query.get('after', '')))
                    if resource == 'analytics' and method == 'POST':
                        return self.result(analytics(service, actor, project, data))
                    if resource == 'analytics-overview' and method == 'POST':
                        return self.result(analytics_overview(service, actor, project, data))
                    if resource == 'retention' and method == 'POST':
                        require(data.get('confirm_project_id') == project, 'Confirm project ID to apply retention')
                        return self.result(service.retention(actor, project))
                    if resource == 'history':
                        return self.result(service.resource_history(actor, project, query.get('kind'), query.get('id')))
                    if resource == 'audits':
                        with connect(service.path) as c:
                            access = service.access(c, actor, project, 'manage')
                            records = [dict(r) for r in c.execute('SELECT * FROM export_audits WHERE project_id=? ORDER BY created_at DESC LIMIT 500', (project,))]
                            if not access['identifiable']:
                                for record in records:
                                    options = json.loads(record['options'])
                                    options['answer_filters'] = '[redacted]'
                                    record['options'] = json.dumps(options)
                            return self.result(records)
                if len(path) == 5 and path[3] == 'forms' and method == 'PUT':
                    return self.result(service.save_form(actor, project, data, path[4]))
                if len(path) == 5 and path[3] == 'public-links' and method == 'PUT':
                    return self.result(service.save_public_link(actor, project, data, path[4]))
            if len(path) == 4 and path[1] == 'forms' and path[3] == 'publish' and method == 'POST':
                return self.result(service.publish(actor, path[2], data.get('revision')))
            if path == ['api', 'sync'] and method == 'POST':
                events = data.get('events')
                require(isinstance(events, list) and len(events) <= 100, 'Use up to 100 sync events per batch')
                results = []
                for event in events:
                    try:
                        results.append({'ok': True, 'result': service.submit(actor, event)})
                    except Problem as e:
                        results.append({'ok': False, 'event_id': event.get('event_id'), 'error': str(e), 'status': e.status})
                return self.result({'results': results})
            if path == ['api', 'interviews'] and method == 'POST':
                return self.result(service.submit(actor, data))
            if len(path) == 3 and path[1] == 'interviews' and method == 'GET':
                with connect(service.path) as c:
                    row = c.execute('SELECT project_id FROM interviews WHERE id=?', (path[2],)).fetchone()
                    require(row, 'Interview not found', 404)
                    rows = service.interviews(actor, row['project_id'], limit=1, interview_id=path[2])
                    require(rows, 'Interview access denied', 403)
                    return self.result(rows[0])
            if len(path) == 4 and path[1] == 'interviews' and method == 'POST':
                if path[3] == 'corrections':
                    return self.result(service.correct(actor, path[2], data))
                if path[3] == 'attachments':
                    return self.result(service.attachment(actor, path[2], data))
            if len(path) == 3 and path[1] == 'attachments' and method == 'GET':
                with connect(service.path) as c:
                    row = c.execute('SELECT a.*,i.project_id,i.researcher_id FROM attachments a JOIN interviews i ON i.id=a.interview_id WHERE a.id=?', (path[2],)).fetchone()
                    require(row, 'Attachment not found', 404)
                    access = service.access(c, actor, row['project_id'])
                    require(access['identifiable'] and (access['role'] != 'researcher' or row['researcher_id'] == actor['id']), 'Attachment access denied', 403)
                    self.send_response(200)
                    self.headers_common()
                    self.send_header('Content-Type', row['mime'])
                    self.send_header('Content-Disposition', 'attachment; filename="attachment-' + row['id'] + '"')
                    self.send_header('Content-Length', str(len(row['content'])))
                    self.end_headers()
                    self.wfile.write(row['content'])
                    return
            if len(path) == 4 and path[1] == 'exports' and path[3] == 'manifest' and method == 'GET':
                with connect(service.path) as c:
                    row = c.execute('SELECT * FROM export_audits WHERE id=?', (path[2],)).fetchone()
                    require(row, 'Export not found', 404)
                    access = service.access(c, actor, row['project_id'])
                    require(row['actor_id'] == actor['id'] or access['role'] == 'manager', 'Export access denied', 403)
                    options = json.loads(row['options'])
                    require(not options.get('include_identifiers') or access['identifiable'], 'Identifiable export permission required', 403)
                    return self.result({'export_id': row['id'], 'interview_count': row['record_count'], 'exported_at': row['created_at'], 'state': row['state'], 'options': options})
            if len(path) == 3 and path[1] == 'exports' and method == 'POST':
                export = Export(service, actor, data)
                if path[2] == 'preview':
                    return self.result(export.preview())
                require(path[2] in ('csv', 'dictionary'), 'Not found', 404)
                iterator = export.dictionary() if path[2] == 'dictionary' else export.stream()
                # Open the export snapshot before sending headers.
                first = next(iterator)
                self.send_response(200)
                self.headers_common()
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', f'attachment; filename="survey-{path[2]}-{export.exported_at[:10]}.csv"')
                self.send_header('X-Record-Count', str(export.count))
                self.send_header('X-Exported-At', export.exported_at)
                self.send_header('X-Export-ID', export.audit_id if path[2] == 'csv' else '')
                self.end_headers()
                try:
                    self.wfile.write(first)
                    for chunk in iterator:
                        self.wfile.write(chunk)
                finally:
                    iterator.close()
                return
            raise Problem('Not found', 404)

        def serve_web(self, request_path):
            require(web_root is not None and self.command == 'GET', 'Not found', 404)
            root = Path(web_root).resolve()
            file = (root / request_path.lstrip('/')).resolve()
            require(file.is_relative_to(root), 'Not found', 404)
            if not file.is_file():
                file = root / 'index.html'
            require(file.is_file(), 'Build the web app first', 404)
            content = file.read_bytes()
            self.send_response(200)
            self.headers_common()
            self.send_header('Content-Type', mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/agal.sqlite')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--bootstrap-email')
    parser.add_argument('--backup')
    args = parser.parse_args()
    migrate(args.db)
    if args.backup:
        backup(args.db, args.backup)
        print('Verified backup created')
        return
    if args.bootstrap_email:
        import getpass
        bootstrap(args.db, args.bootstrap_email, getpass.getpass('Administrator password (8+ characters): '))
        print('Administrator created')
        return
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(Service(args.db), Path(__file__).parent.parent / 'web' / 'dist'))
    print(f'Student Survey Creator listening on http://{args.host}:{args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
