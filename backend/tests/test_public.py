import base64
import csv
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.db import bootstrap, connect, encode, migrate, new_id, now
from backend.exports import Export, analytics
from backend.model import Problem
from backend.server import handler_for
from backend.service import Service


class PublicSurveyTest(unittest.TestCase):
    def database_target(self):
        return str(Path(self.temp.name) / 'db.sqlite')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agal-public-')
        self.path = self.database_target()
        migrate(self.path)
        bootstrap(self.path, 'admin@example.test', 'public-test-password')
        with connect(self.path) as c:
            self.admin = dict(c.execute('SELECT * FROM users').fetchone())
        self.s = Service(self.path)
        self.project = self.s.save_project(self.admin, {
            'name': 'Public research', 'description': 'Internal description',
            'config': {'objectives': 'Private internal objectives', 'consent': 'Participation is voluntary.',
                       'locations': [{'id': 'north', 'label': 'North district'}]}})
        self.story, self.choices, self.private = new_id(), new_id(), new_id()
        self.schema = {'sections': [{'id': new_id(), 'label': 'Your experience', 'questions': [
            {'id': self.story, 'label': 'Tell us your story', 'type': 'text', 'required': True},
            {'id': self.choices, 'label': 'Your activities', 'type': 'multiple', 'choices': [{'code': 'a', 'label': 'Activity A'}, {'code': 'b', 'label': 'Activity B'}]},
            {'id': self.private, 'label': 'Contact (optional)', 'type': 'text', 'sensitive': True},
        ]}]}
        self.form = self.s.save_form(self.admin, self.project['id'], {'name': 'Public questionnaire', 'draft': self.schema})
        self.version = self.s.publish(self.admin, self.form['id'], 1)
        self.link = self.make_link()

    def tearDown(self):
        self.temp.cleanup()

    def make_link(self, version=None, **kwargs):
        return self.s.save_public_link(self.admin, self.project['id'], {'name': 'Open invitation', 'version_id': (version or self.version)['id'], **kwargs})

    def response(self, **kwargs):
        return {'submission_id': new_id(), 'consent': True, 'answers': {
            self.story: {'state': 'answered', 'value': 'Kumusta, "ñ"\n🌿'},
            self.choices: {'state': 'answered', 'value': ['a', 'b']},
            self.private: {'state': 'answered', 'value': 'Protected contact'},
        }, **kwargs}

    def update_link(self, **changes):
        self.link = self.s.save_public_link(self.admin, self.project['id'], {**self.link, **changes}, self.link['id'])
        return self.link

    def public_interview(self):
        return self.s.interviews(self.admin, self.project['id'])[0]

    def test_public_schema_is_minimal_and_does_not_require_a_user(self):
        survey = self.s.public_survey(self.link['token'])
        self.assertEqual(set(survey), {'title', 'project_name', 'version_number', 'schema', 'locations', 'attachment_limit'})
        self.assertEqual(survey['attachment_limit'], 10 * 1024 * 1024)
        self.assertEqual(survey['title'], 'Public questionnaire')
        self.assertNotIn('Private internal objectives', encode(survey))
        self.assertNotIn(self.admin['email'], encode(survey))
        self.assertNotIn(self.admin['id'], encode(survey))
        self.assertEqual(survey['schema']['consent'], 'Participation is voluntary.')

    def test_submission_is_completed_without_fake_researcher_and_receipt_is_minimal(self):
        result = self.s.submit_public(self.link['token'], self.response())
        self.assertEqual(set(result), {'submitted', 'receipt'})
        row = self.public_interview()
        self.assertEqual(row['source'], 'public_link')
        self.assertEqual(row['public_link_id'], self.link['id'])
        self.assertIsNone(row['researcher_id'])
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['answers'][self.choices]['value'], ['a', 'b'])
        with connect(self.path) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE interviews SET answers=? WHERE id=?', ('{}', row['id']))

    def test_identical_retries_are_idempotent_but_edits_conflict(self):
        data = self.response()
        result = self.s.submit_public(self.link['token'], data)
        self.assertEqual(result, self.s.submit_public(self.link['token'], dict(reversed(list(data.items())))))
        changed = json.loads(encode(data))
        changed['answers'][self.story]['value'] = 'Changed'
        with self.assertRaises(Problem) as conflict:
            self.s.submit_public(self.link['token'], changed)
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(len(self.s.interviews(self.admin, self.project['id'])), 1)

    def test_validation_consent_and_field_spoofing_cannot_create_records(self):
        for data in (self.response(consent=False), self.response(answers={}), self.response(version_id=new_id()), self.response(researcher_id=self.admin['id'])):
            with self.assertRaises(Problem):
                self.s.submit_public(self.link['token'], data)
        self.assertEqual(self.s.interviews(self.admin, self.project['id']), [])

    def test_link_is_version_pinned_after_form_and_consent_changes(self):
        self.schema['sections'][0]['questions'][0]['label'] = 'Revised story'
        form = self.s.save_form(self.admin, self.project['id'], {**self.form, 'draft': self.schema}, self.form['id'])
        self.s.save_project(self.admin, {**self.project, 'config': {**self.project['config'], 'consent': 'New consent'}}, self.project['id'])
        newer = self.s.publish(self.admin, form['id'], form['revision'])
        survey = self.s.public_survey(self.link['token'])
        self.assertEqual(survey['schema']['sections'][0]['questions'][0]['label'], 'Tell us your story')
        self.assertEqual(survey['schema']['consent'], 'Participation is voluntary.')
        self.s.submit_public(self.link['token'], self.response())
        self.assertEqual(self.public_interview()['version_id'], self.version['id'])
        with self.assertRaises(Problem):
            self.update_link(version_id=newer['id'])

    def test_disable_and_expiration_stop_new_responses_but_preserve_receipt(self):
        data = self.response()
        result = self.s.submit_public(self.link['token'], data)
        self.update_link(enabled=False)
        for call in (lambda: self.s.public_survey(self.link['token']), lambda: self.s.submit_public(self.link['token'], self.response())):
            with self.assertRaises(Problem) as unavailable:
                call()
            self.assertEqual(unavailable.exception.status, 410)
        self.assertEqual(result, self.s.submit_public(self.link['token'], data))
        self.update_link(enabled=True, expires_at='2000-01-01T00:00:00Z')
        with self.assertRaises(Problem):
            self.s.public_survey(self.link['token'])

    def test_archived_project_and_form_stop_public_collection(self):
        self.s.save_form(self.admin, self.project['id'], {**self.form, 'archived': True}, self.form['id'])
        with self.assertRaises(Problem):
            self.s.submit_public(self.link['token'], self.response())
        self.s.save_project(self.admin, {**self.project, 'archived': True}, self.project['id'])
        with self.assertRaises(Problem):
            self.s.public_survey(self.link['token'])

    def test_manager_permissions_scope_and_history(self):
        user_id = new_id()
        with connect(self.path) as c:
            c.execute('INSERT INTO users VALUES(?,?,?,?,0,1)', (user_id, 'researcher@example.test', 'Researcher', 'unused-in-service-tests'))
            user = dict(c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
        self.s.members(self.admin, self.project['id'], {'user_id': user_id, 'role': 'researcher', 'identifiable': False})
        with self.assertRaises(Problem):
            self.s.public_links(user, self.project['id'])
        self.s.members(self.admin, self.project['id'], {'user_id': user_id, 'role': 'manager', 'identifiable': False})
        with self.assertRaises(Problem):
            self.s.save_public_link(user, self.project['id'], {'name': 'Protected survey', 'version_id': self.version['id']})
        other = self.s.save_project(self.admin, {'name': 'Other project'})
        with self.assertRaises(Problem):
            self.s.save_public_link(self.admin, other['id'], {'name': 'Wrong project', 'version_id': self.version['id']})
        self.update_link(enabled=False)
        self.assertEqual(len(self.s.resource_history(self.admin, self.project['id'], 'public_link', self.link['id'])), 2)

    def test_creator_permission_revocation_stops_protected_public_link(self):
        user_id = new_id()
        with connect(self.path) as c:
            c.execute('INSERT INTO users VALUES(?,?,?,?,0,1)', (user_id, 'manager@example.test', 'Manager', 'unused-in-service-tests'))
            user = dict(c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
        self.s.members(self.admin, self.project['id'], {'user_id': user_id, 'role': 'manager', 'identifiable': True})
        link = self.s.save_public_link(user, self.project['id'], {'name': 'Invitation', 'version_id': self.version['id']})
        self.s.public_survey(link['token'])
        self.s.members(self.admin, self.project['id'], {'user_id': user_id, 'role': 'manager', 'identifiable': False})
        with self.assertRaises(Problem) as denied:
            self.s.public_survey(link['token'])
        self.assertEqual(denied.exception.status, 410)

    def test_public_responses_feed_exports_analytics_and_researcher_scoping(self):
        self.s.submit_public(self.link['token'], self.response())
        export = Export(self.s, self.admin, {'project_id': self.project['id'], 'source': 'public_link', 'format': 'long'})
        rows = list(csv.DictReader(io.StringIO(b''.join(export.stream()).decode('utf-8'))))
        self.assertEqual(rows[0]['source'], 'public_link')
        self.assertEqual(rows[0]['answer_value'], 'Kumusta, "ñ"\n🌿')
        self.assertFalse(any(row['question_id'] == self.private for row in rows))
        values = analytics(self.s, self.admin, self.project['id'], {'source': 'public_link'})
        multiple = next(v for v in values if v['question_id'] == self.choices)
        self.assertEqual(multiple['categories'], {'a': 1, 'b': 1})
        with connect(self.path) as c:
            user_id = new_id()
            c.execute('INSERT INTO users VALUES(?,?,?,?,0,1)', (user_id, 'scoped@example.test', 'Scoped', 'unused-in-service-tests'))
            user = dict(c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
        self.s.members(self.admin, self.project['id'], {'user_id': user_id, 'role': 'researcher', 'identifiable': True})
        self.assertEqual(self.s.interviews(user, self.project['id']), [])
        self.assertEqual(Export(self.s, user, {'project_id': self.project['id']}).count, 0)

    def test_public_attachments_are_bound_to_this_submission_and_transactional(self):
        media_id, qid = new_id(), new_id()
        self.schema['sections'][0]['questions'].append({'id': qid, 'label': 'Optional photo', 'type': 'media'})
        form = self.s.save_form(self.admin, self.project['id'], {**self.form, 'draft': self.schema}, self.form['id'])
        version = self.s.publish(self.admin, form['id'], form['revision'])
        link = self.make_link(version)
        data = self.response()
        data['answers'][qid] = {'state': 'answered', 'value': [media_id]}
        with self.assertRaises(Problem):
            self.s.submit_public(link['token'], data)
        self.assertEqual(self.s.interviews(self.admin, self.project['id']), [])
        data['attachments'] = [{'id': media_id, 'question_id': qid, 'filename': 'photo.png', 'mime': 'image/png', 'content': base64.b64encode(b'\x89PNG\r\n\x1a\n').decode()}]
        result = self.s.submit_public(link['token'], data)
        self.assertEqual(result, self.s.submit_public(link['token'], data))
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM attachments').fetchone()[0], 1)
        reused = self.response()
        reused['answers'][qid] = {'state': 'answered', 'value': [media_id]}
        reused['attachments'] = data['attachments']
        with self.assertRaises(Problem):
            self.s.submit_public(link['token'], reused)
        self.assertEqual(len(self.s.interviews(self.admin, self.project['id'])), 1)

    def test_receipts_survive_retention_without_resubmitting_deleted_interviews(self):
        data = self.response()
        result = self.s.submit_public(self.link['token'], data)
        with connect(self.path) as c:
            c.execute('DELETE FROM interviews WHERE source=\'public_link\'')
        self.assertEqual(result, self.s.submit_public(self.link['token'], data))
        self.assertEqual(self.s.interviews(self.admin, self.project['id']), [])

    def test_anonymous_http_can_submit_but_never_read_responses_or_management(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.s))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}/api'
        path = '/public/surveys/' + self.link['token']
        try:
            with urlopen(root + path) as response:
                self.assertEqual(json.load(response)['title'], 'Public questionnaire')
            with urlopen(Request(root + path + '/responses', encode(self.response()).encode(), {'Content-Type': 'application/json'})) as response:
                self.assertEqual(set(json.load(response)), {'submitted', 'receipt'})
            for route in (f'/projects/{self.project["id"]}/public-links', f'/interviews/{self.public_interview()["id"]}', '/projects'):
                with self.assertRaises(HTTPError) as denied:
                    urlopen(root + route)
                self.assertEqual(denied.exception.code, 401)
            with self.assertRaises(HTTPError) as denied:
                urlopen(root + path + '/responses')
            self.assertEqual(denied.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class PublicMigrationTest(unittest.TestCase):
    def test_failed_foreign_key_validation_rolls_back_the_table_rebuild(self):
        with tempfile.TemporaryDirectory(prefix='agal-rollback-') as directory:
            path = str(Path(directory) / 'invalid.sqlite')
            initial = Path(__file__).parent.parent / 'migrations' / '001_initial.sql'
            with connect(path) as c:
                c.executescript(initial.read_text(encoding='utf-8'))
                c.execute('CREATE TABLE migrations(name TEXT PRIMARY KEY,applied_at TEXT NOT NULL)')
                c.execute('INSERT INTO migrations VALUES(?,?)', (initial.name, now()))
                c.commit()
                c.execute('PRAGMA foreign_keys=OFF')
                c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)', (new_id(), new_id(), new_id(), 'orphan.pdf', 'application/pdf', b'original bytes', now()))
            with self.assertRaises(sqlite3.IntegrityError):
                migrate(path)
            with connect(path) as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='public_links'").fetchone()[0], 0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM migrations').fetchone()[0], 1)
                researcher = next(row for row in c.execute('PRAGMA table_info(interviews)') if row['name'] == 'researcher_id')
                self.assertEqual(researcher['notnull'], 1)
                self.assertEqual(c.execute('SELECT content FROM attachments').fetchone()[0], b'original bytes')

    def test_existing_responses_children_and_immutability_survive_upgrade(self):
        with tempfile.TemporaryDirectory(prefix='agal-migration-') as directory:
            path = str(Path(directory) / 'old.sqlite')
            initial = Path(__file__).parent.parent / 'migrations' / '001_initial.sql'
            with connect(path) as c:
                c.executescript(initial.read_text(encoding='utf-8'))
                c.execute('CREATE TABLE migrations(name TEXT PRIMARY KEY,applied_at TEXT NOT NULL)')
                c.execute('INSERT INTO migrations VALUES(?,?)', (initial.name, now()))
            bootstrap(path, 'old@example.test', 'old-test-password')
            with connect(path) as c:
                admin = dict(c.execute('SELECT * FROM users').fetchone())
            service = Service(path)
            project = service.save_project(admin, {'name': 'Existing research'})
            qid = new_id()
            schema = {'sections': [{'id': new_id(), 'label': 'Original', 'questions': [{'id': qid, 'label': 'Story', 'type': 'text'}]}]}
            form = service.save_form(admin, project['id'], {'name': 'Existing form', 'draft': schema})
            version = service.publish(admin, form['id'], 1)
            event = {'event_id': new_id(), 'id': new_id(), 'version_id': version['id'], 'status': 'completed', 'consent': True, 'answers': {qid: {'state': 'answered', 'value': 'Preserve ñ, "quotes"\nand lines'}}}
            service.submit(admin, event)
            correction = service.correct(admin, event['id'], {'answers': {qid: {'state': 'answered', 'value': 'Corrected'}}, 'reason': 'Verified'})
            with connect(path) as c:
                c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)', (new_id(), event['id'], qid, 'existing.pdf', 'application/pdf', b'preserve bytes', now()))
                original = dict(c.execute('SELECT * FROM interviews').fetchone())
            migrate(path)
            migrate(path)
            with connect(path) as c:
                migrated = dict(c.execute('SELECT * FROM interviews').fetchone())
                self.assertEqual({key: migrated[key] for key in original}, original)
                self.assertEqual(migrated['source'], 'researcher')
                self.assertIsNone(migrated['public_link_id'])
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(c.execute('SELECT content FROM attachments').fetchone()[0], b'preserve bytes')
                self.assertEqual(c.execute('SELECT id FROM corrections').fetchone()[0], correction['id'])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM sync_events').fetchone()[0], 1)
                with self.assertRaises(sqlite3.IntegrityError):
                    c.execute('UPDATE interviews SET answers=?', ('{}',))
            rows = list(csv.DictReader(io.StringIO(b''.join(Export(service, admin, {'project_id': project['id'], 'format': 'long'}).stream()).decode())))
            self.assertEqual(rows[0]['answer_value'], 'Corrected')


if __name__ == '__main__':
    unittest.main()
