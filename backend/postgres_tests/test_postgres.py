"""Run with TEST_POSTGRES_URL set to a dedicated PostgreSQL test database.

Every test creates/drops its own random schema; never uses public tables.
"""
import concurrent.futures
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql

from backend.db import connect, encode, migrate, new_id, now
from backend.hosted import BODY_LIMIT, create_handler
from backend.tests import test_platform as platform_suite
from backend.tests import test_public as public_suite


class DatabaseFixture:
    def database_target(self):
        url = os.environ['TEST_POSTGRES_URL']
        schema = 'survey_test_' + new_id().replace('-', '')
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

        def cleanup():
            with psycopg.connect(url, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

        self.addCleanup(cleanup)
        parsed = urlsplit(url)
        parameters = dict(parse_qsl(parsed.query))
        parameters['options'] = '-csearch_path=' + schema
        return urlunsplit(parsed._replace(query=urlencode(parameters)))


@unittest.skipUnless(os.environ.get('TEST_POSTGRES_URL'), 'Set TEST_POSTGRES_URL for PostgreSQL integration tests')
class PostgresPlatformTest(DatabaseFixture, platform_suite.PlatformTest):
    def test_backup_and_repeatable_migrations(self):
        migrate(self.path)
        migrate(self.path)
        with connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM migrations').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT name FROM projects WHERE id=?', (self.project['id'],)).fetchone()[0], self.project['name'])

    def test_concurrent_revision_checks_preserve_one_winner(self):
        draft = self.event(status='draft')
        self.s.submit(self.admin, draft)

        def update(number):
            try:
                self.s.submit(self.admin, {**draft, 'event_id': new_id(), 'revision': 1})
                return 'saved'
            except platform_suite.Problem as failure:
                return failure.status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(update, range(2)), ['saved', 409])

    def test_parameter_adapter_preserves_literals(self):
        with connect(self.path) as connection:
            row = connection.execute("SELECT '?' AS question, '100%' AS percent, ?::text AS parameter", ('value',)).fetchone()
            self.assertEqual((row[0], row['percent'], row['parameter']), ('?', '100%', 'value'))

    def test_typed_answer_filters_use_latest_or_original_answers(self):
        event = self.event()
        event['answers'][self.qs[4]['id']] = {'state': 'answered', 'value': True}
        self.s.submit(self.admin, event)

        def filtered(question, op, value, **options):
            return self.export(answer_filters=[{'question_id': question, 'op': op, 'value': value}], **options).count

        self.assertEqual(filtered(self.qs[2]['id'], 'gt', 100), 1)
        self.assertEqual(filtered(self.qs[2]['id'], 'lt', 100), 0)
        self.assertEqual(filtered(self.qs[2]['id'], 'equals', 123.45), 1)
        self.assertEqual(filtered(self.qs[0]['id'], 'equals', event['answers'][self.qs[0]['id']]['value']), 1)
        self.assertEqual(filtered(self.qs[4]['id'], 'equals', True), 1)
        self.assertEqual(filtered(self.qs[4]['id'], 'equals', False), 0)
        self.s.correct(self.admin, event['id'], {'answers': {**event['answers'], self.qs[2]['id']: {'state': 'answered', 'value': 77}}, 'reason': 'Verified amount'})
        self.assertEqual(filtered(self.qs[2]['id'], 'gt', 100), 0)
        self.assertEqual(filtered(self.qs[2]['id'], 'gt', 100, original=True), 1)

    def hosted_server(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), create_handler({'DATABASE_URL': self.path}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join()

        self.addCleanup(stop)
        return f'http://127.0.0.1:{server.server_port}'

    def test_vercel_rewrite_limits_and_database_backed_rate_limits(self):
        roots = [self.hosted_server(), self.hosted_server()]
        with urlopen(roots[0] + '/api/index?__path=health') as response:
            health = json.load(response)
        self.assertEqual(health['database'], 'postgresql')
        self.assertEqual(health['limits']['attachment_bytes'], 2 * 1024 * 1024)
        for index in range(11):
            with self.assertRaises(HTTPError) as failed:
                urlopen(Request(roots[index % 2] + '/api/index?__path=login', b'{"email":"missing@example.test","password":"incorrect"}', {'Content-Type': 'application/json'}))
            self.assertEqual(failed.exception.code, 401 if index < 10 else 429)
            failed.exception.close()
        with self.assertRaises(HTTPError) as too_large:
            urlopen(Request(roots[0] + '/api/index?__path=register', b'{}', {'Content-Length': str(BODY_LIMIT + 1)}))
        self.assertEqual(too_large.exception.code, 413)
        too_large.exception.close()
        with urlopen(Request(roots[0] + '/api/index?__path=projects/' + self.project['id'] + '/interviews&limit=1', headers={'Authorization': 'Bearer ' + self.login['token']})) as response:
            self.assertEqual(json.load(response), [])

    def test_hosted_export_rejects_oversize_before_csv_headers(self):
        event = self.event()
        event['answers'][self.qs[0]['id']]['value'] = 'x' * 100000
        with connect(self.path) as connection:
            for _ in range(45):
                connection.execute('INSERT INTO interviews(id,project_id,version_id,researcher_id,location,status,answers,consent,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                   (new_id(), self.project['id'], self.version['id'], self.admin['id'], 'north', 'completed', encode(event['answers']), 1, now(), now()))
        root = self.hosted_server()
        with self.assertRaises(HTTPError) as oversized:
            urlopen(Request(root + '/api/index?__path=exports/csv', encode({'project_id': self.project['id']}).encode(), {'Authorization': 'Bearer ' + self.login['token'], 'Content-Type': 'application/json'}))
        self.assertEqual(oversized.exception.code, 413)
        self.assertIn('narrow the export filters', json.load(oversized.exception)['error'])
        oversized.exception.close()
        with connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT state FROM export_audits').fetchone()[0], 'interrupted')


@unittest.skipUnless(os.environ.get('TEST_POSTGRES_URL'), 'Set TEST_POSTGRES_URL for PostgreSQL integration tests')
class PostgresPublicTest(DatabaseFixture, public_suite.PublicSurveyTest):
    def test_concurrent_public_retries_return_one_receipt(self):
        data = self.response()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.s.submit_public(self.link['token'], data), range(8)))
        self.assertEqual(len({result['receipt'] for result in results}), 1)
        self.assertEqual(len(self.s.interviews(self.admin, self.project['id'])), 1)
