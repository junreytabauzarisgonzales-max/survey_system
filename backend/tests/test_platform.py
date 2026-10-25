import csv
import io
import json
import sqlite3
import tempfile
import threading
import tracemalloc
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.db import backup, bootstrap, connect, encode, migrate, new_id, now
from backend.exports import Export, analytics, analytics_overview
from backend.model import Problem, validate_answers, validate_schema
from backend.server import handler_for
from backend.service import Service


class PlatformTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'db.sqlite')
        migrate(self.path)
        bootstrap(self.path, 'admin@example.test', 'long-test-password')
        self.s = Service(self.path)
        self.login = self.s.login({'email': 'admin@example.test', 'password': 'long-test-password'})
        self.admin = self.s.authenticate(self.login['token'])
        self.project = self.s.save_project(self.admin, {'name': 'Independent research', 'config': {'consent': 'May we collect this information?', 'locations': [{'id': 'north', 'label': 'North'}]}})
        self.qs = [
            {'id': new_id(), 'label': 'Filipino text', 'type': 'text', 'required': True},
            {'id': new_id(), 'label': 'Activities', 'type': 'multiple', 'choices': [{'code': 'a', 'label': 'Activity A'}, {'code': 'b', 'label': 'Activity B'}]},
            {'id': new_id(), 'label': 'Amount', 'type': 'currency'},
            {'id': new_id(), 'label': 'Private name', 'type': 'text', 'sensitive': True},
            {'id': new_id(), 'label': 'Optional response', 'type': 'boolean'},
        ]
        self.schema = {'sections': [{'id': new_id(), 'label': 'Custom section', 'questions': self.qs}]}
        self.form = self.s.save_form(self.admin, self.project['id'], {'name': 'Completely custom questionnaire', 'draft': self.schema})
        self.version = self.s.publish(self.admin, self.form['id'], 1)

    def tearDown(self):
        self.temp.cleanup()

    def event(self, **extra):
        answers = {self.qs[0]['id']: {'state': 'answered', 'value': 'Kumusta, "magsasaka"\nÑ, ₱, 🌿'},
                   self.qs[1]['id']: {'state': 'answered', 'value': ['a', 'b']},
                   self.qs[2]['id']: {'state': 'answered', 'value': 123.45},
                   self.qs[3]['id']: {'state': 'answered', 'value': 'Protected person'},
                   self.qs[4]['id']: {'state': 'not_sure'}}
        return {'event_id': new_id(), 'id': new_id(), 'version_id': self.version['id'], 'status': 'completed', 'consent': True, 'answers': answers, 'location': 'north', **extra}

    def export(self, **options):
        return Export(self.s, self.admin, {'project_id': self.project['id'], **options})

    @staticmethod
    def parse(export):
        return list(csv.DictReader(io.StringIO(b''.join(export.stream()).decode('utf-8'))))

    def researcher(self, identifiable=False):
        user = self.s.create_user(self.admin, {'name': 'Researcher', 'email': new_id() + '@test.local', 'password': 'researcher-password'})
        self.s.members(self.admin, self.project['id'], {'user_id': user['id'], 'role': 'researcher', 'identifiable': identifiable})
        with connect(self.path) as c:
            return dict(c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone())

    def test_custom_questionnaire_utf8_and_multiple_choices(self):
        event = self.event()
        self.s.submit(self.admin, event)
        export = self.export(format='analysis')
        rows = self.parse(export)
        self.assertEqual(len(rows), 1)
        prefix = export.prefix(self.version, self.qs[1])
        self.assertEqual((rows[0][prefix + '__a'], rows[0][prefix + '__b']), ('1', '1'))
        self.assertEqual(rows[0][export.prefix(self.version, self.qs[0])], event['answers'][self.qs[0]['id']]['value'])
        self.assertEqual(rows[0][export.prefix(self.version, self.qs[2])], '123.45')
        self.assertNotIn('respondent_id', rows[0])
        self.assertFalse(any(self.qs[3]['id'] in col for col in rows[0]))
        self.assertIn(b'Activity A', b''.join(export.dictionary()))

    def test_version_labels_and_immutable_versions(self):
        self.s.submit(self.admin, self.event())
        self.qs[0]['label'] = 'New label'
        form = self.s.save_form(self.admin, self.project['id'], {**self.form, 'draft': self.schema}, self.form['id'])
        self.s.publish(self.admin, form['id'], form['revision'])
        self.assertEqual(self.parse(self.export(format='long'))[0]['question_label'], 'Filipino text')
        with connect(self.path) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE versions SET schema=? WHERE id=?', ('{}', self.version['id']))
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('DELETE FROM versions WHERE id=?', (self.version['id'],))

    def test_raw_preserves_original_types_and_states(self):
        event = self.event()
        self.s.submit(self.admin, event)
        for row in self.parse(self.export(format='raw', include_identifiers=True)):
            self.assertEqual(json.loads(row['answer_value']), event['answers'][row['question_id']])

    def test_idempotency_and_duplicate_protection(self):
        event = self.event()
        first = self.s.submit(self.admin, event)
        self.assertEqual(first, self.s.submit(self.admin, event))
        with self.assertRaises(Problem):
            self.s.submit(self.admin, {**event, 'status': 'draft'})
        with self.assertRaises(Problem):
            self.s.submit(self.admin, {**event, 'event_id': new_id()})
        self.assertEqual(self.export().count, 1)

    def test_draft_optimistic_lock_and_completion(self):
        event = self.event(status='draft')
        self.s.submit(self.admin, event)
        with self.assertRaises(Problem):
            self.s.submit(self.admin, {**event, 'event_id': new_id(), 'revision': 0})
        self.s.submit(self.admin, {**event, 'event_id': new_id(), 'revision': 1, 'status': 'completed'})
        self.assertEqual(self.export(status='completed').count, 1)

    def test_corrections_keep_original_and_detect_stale_edits(self):
        event = self.event()
        self.s.submit(self.admin, event)
        amended = {**event['answers'], self.qs[2]['id']: {'state': 'answered', 'value': 77}}
        self.s.correct(self.admin, event['id'], {'answers': amended, 'reason': 'Checked receipt'})
        with self.assertRaises(Problem):
            self.s.correct(self.admin, event['id'], {'answers': amended, 'reason': 'Stale'})
        prefix = self.export().prefix(self.version, self.qs[2])
        self.assertEqual(self.parse(self.export())[0][prefix], '77')
        self.assertEqual(self.parse(self.export(original=True))[0][prefix], '123.45')
        self.assertEqual(self.s.interviews(self.admin, self.project['id'])[0]['answers'][self.qs[2]['id']]['value'], 123.45)

    def test_privacy_and_project_and_researcher_isolation(self):
        self.s.submit(self.admin, self.event())
        user = self.researcher()
        with self.assertRaises(Problem):
            Export(self.s, user, {'project_id': self.project['id'], 'include_identifiers': True})
        self.assertEqual(Export(self.s, user, {'project_id': self.project['id']}).count, 0)
        self.assertEqual(self.s.interviews(user, self.project['id']), [])
        with self.assertRaises(Problem):
            self.s.submit(user, self.event())
        other = self.s.save_project(self.admin, {'name': 'Other project'})
        with self.assertRaises(Problem):
            Export(self.s, user, {'project_id': other['id']})

    def test_formula_protection_and_negative_numbers(self):
        event = self.event()
        event['answers'][self.qs[0]['id']]['value'] = '  =HYPERLINK("bad")'
        event['answers'][self.qs[2]['id']]['value'] = -8.25
        self.s.submit(self.admin, event)
        row = self.parse(self.export())[0]
        self.assertTrue(row[self.export().prefix(self.version, self.qs[0])].startswith("'"))
        self.assertEqual(row[self.export().prefix(self.version, self.qs[2])], '-8.25')
        self.assertEqual(json.loads(self.parse(self.export(format='raw'))[0]['answer_value'])['value'], '  =HYPERLINK("bad")')

    def test_conditional_engine_and_validation(self):
        first = {'id': new_id(), 'label': 'Show?', 'type': 'boolean'}
        second = {'id': new_id(), 'label': 'Details', 'type': 'number', 'required': True, 'validation': {'min': 1}, 'condition': {'question_id': first['id'], 'op': 'equals', 'value': True}}
        schema = {'sections': [{'id': new_id(), 'label': 'Rules', 'questions': [first, second]}]}
        validate_schema(schema)
        a = {first['id']: {'state': 'answered', 'value': False}}
        self.assertEqual(validate_answers(schema, a, True)[second['id']]['state'], 'skipped')
        with self.assertRaises(Problem):
            validate_answers(schema, {first['id']: {'state': 'answered', 'value': True}}, True)
        second['condition']['op'] = '__import__'
        with self.assertRaises(Problem):
            validate_schema(schema)

    def test_location_requires_explicit_consent(self):
        q = {'id': new_id(), 'label': 'Position', 'type': 'location'}
        schema = {'sections': [{'id': new_id(), 'label': 'Location', 'questions': [q]}]}
        answers = {q['id']: {'state': 'answered', 'value': {'latitude': 10, 'longitude': 122}}}
        with self.assertRaises(Problem):
            validate_answers(schema, answers)
        validate_answers(schema, answers, location_consent=True)

    def test_required_empty_answers_cannot_complete_but_drafts_can_autosave(self):
        event=self.event()
        event['answers'][self.qs[0]['id']]['value']='   '
        with self.assertRaises(Problem):
            self.s.submit(self.admin,event)
        event['status']='draft'
        self.s.submit(self.admin,event)

    def test_analytics_denominators(self):
        self.s.submit(self.admin, self.event())
        values = analytics(self.s, self.admin, self.project['id'], {'group_by_location': True})
        boolean = next(v for v in values if v['question_id'] == self.qs[4]['id'])
        self.assertEqual((boolean['total'], boolean['answered'], boolean['categories']), (1, 0, {}))
        multiple = next(v for v in values if v['question_id'] == self.qs[1]['id'])
        self.assertEqual(multiple['percentages'], {'a': 100, 'b': 100})
        amount = next(v for v in values if v['question_id'] == self.qs[2]['id'])
        self.assertEqual((amount['mean'], amount['median'], amount['mode'], amount['stdev']), (123.45, 123.45, 123.45, 0.0))
        self.assertEqual(amount['histogram'][0]['count'], 1)

    def test_analytics_overview_counts_and_timeline(self):
        self.s.submit(self.admin, self.event())
        result = analytics_overview(self.s, self.admin, self.project['id'], {})
        self.assertEqual((result['total'], result['completed'], result['draft']), (1, 1, 0))
        self.assertEqual(result['sources'], {'researcher': 1})
        self.assertEqual(len(result['timeline']), 1)
        self.assertEqual(result['timeline'][0]['count'], 1)

    def test_self_registration_creates_an_isolated_workspace(self):
        account = self.s.register({'name': 'Student', 'email': 'student@example.test', 'password': 'student-password'})
        self.assertEqual(set(account['user']), {'id', 'name', 'email', 'admin'})
        actor = self.s.authenticate(account['token'])
        self.assertFalse(actor['admin'])
        project = self.s.save_project(actor, {'name': 'My first survey', 'config': {}})
        self.assertEqual([p['id'] for p in self.s.project_list(actor)], [project['id']])
        with self.assertRaises(Problem):
            self.s.interviews(actor, self.project['id'])
        with self.assertRaises(Problem):
            self.s.users(actor)
        form = self.s.save_form(actor, project['id'], {'name': 'Student questions', 'draft': self.schema})
        self.assertEqual(self.s.publish(actor, form['id'], 1)['number'], 1)
        template = self.s.apply_template(actor, 'agal-livelihood-starter')
        self.assertIn(template['id'], [p['id'] for p in self.s.project_list(actor)])
        with self.assertRaises(Problem):
            self.s.register({'name': 'Duplicate', 'email': 'student@example.test', 'password': 'student-password'})

    def test_team_invitation_by_email(self):
        account = self.s.register({'name': 'Viewer', 'email': 'viewer@example.test', 'password': 'viewer-password'})
        self.s.members(self.admin, self.project['id'], {'email': account['user']['email'], 'role': 'viewer', 'identifiable': False})
        self.assertEqual(self.s.project_list(self.s.authenticate(account['token']))[0]['id'], self.project['id'])
        with self.assertRaises(Problem):
            self.s.members(self.admin, self.project['id'], {'email': 'missing@example.test', 'role': 'viewer', 'identifiable': False})

    def test_filters_and_audit(self):
        self.s.submit(self.admin, self.event())
        self.assertEqual(self.export(location='elsewhere').count, 0)
        self.assertEqual(self.export(form_ids=[self.form['id']], version_ids=[self.version['id']]).count, 1)
        self.assertEqual(self.export(**{'from': '2099-01-01T00:00:00Z'}).count, 0)
        export = self.export()
        self.parse(export)
        with connect(self.path) as c:
            audit = c.execute('SELECT * FROM export_audits WHERE id=?', (export.audit_id,)).fetchone()
            self.assertEqual((audit['state'], audit['record_count']), ('completed', 1))

    def test_archive_history_and_duplicate(self):
        self.s.submit(self.admin, self.event())
        duplicate = self.s.duplicate_project(self.admin, self.project['id'])
        self.assertEqual(len(self.s.forms(self.admin, duplicate['id'])), 1)
        self.assertEqual(self.s.versions(self.admin, duplicate['id']), [])
        self.s.save_project(self.admin, {**self.project, 'archived': True}, self.project['id'])
        with self.assertRaises(Problem):
            self.s.submit(self.admin, self.event())
        self.assertEqual(len(self.s.resource_history(self.admin, self.project['id'], 'project', self.project['id'])), 2)

    def test_delete_project_purges_all_survey_data(self):
        event = self.event()
        self.s.submit(self.admin, event)
        link = self.s.save_public_link(self.admin, self.project['id'], {'version_id': self.version['id'], 'name': 'Share'})
        self.s.submit_public(link['token'], {'submission_id': new_id(), 'answers': event['answers'], 'consent': True})
        attachment = new_id()
        with connect(self.path) as c:
            c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)', (attachment, event['id'], self.qs[0]['id'], 'note.txt', 'text/plain', b'note', now()))
            c.execute('INSERT INTO history VALUES(?,?,?,?,?,?)', (new_id(), 'attachment', attachment, self.admin['id'], encode({'filename': 'note.txt'}), now()))
        with self.assertRaises(Problem):
            self.s.delete_project(self.admin, self.project['id'], {'confirm_name': 'Wrong title'})
        self.assertEqual(len(self.s.project_list(self.admin)), 1)
        result = self.s.delete_project(self.admin, self.project['id'], {'confirm_name': self.project['name']})
        self.assertEqual((result['forms'], result['versions'], result['links'], result['responses']), (1, 1, 1, 2))
        self.assertEqual(self.s.project_list(self.admin), [])
        with connect(self.path) as c:
            for table in ('projects', 'forms', 'versions', 'public_links', 'public_receipts', 'interviews', 'respondents', 'attachments', 'corrections', 'sync_events', 'export_audits', 'retention_events', 'memberships', 'project_deletions', 'history'):
                self.assertEqual(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0, table)

    def test_large_export_has_bounded_memory(self):
        sample = self.event()
        with connect(self.path) as c:
            for _ in range(3000):
                c.execute('INSERT INTO interviews(id,project_id,version_id,researcher_id,respondent_id,location,status,answers,consent,location_consent,created_at,updated_at,revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)', (new_id(), self.project['id'], self.version['id'], self.admin['id'], None, 'north', 'completed', encode(sample['answers']), 1, 0, now(), now()))
        export = self.export()
        tracemalloc.start()
        chunks = sum(1 for _ in export.stream())
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertEqual(chunks, 3002)
        self.assertLess(peak, 2_000_000)

    def test_backup_and_repeatable_migrations(self):
        migrate(self.path)
        target = str(Path(self.temp.name) / 'backup.sqlite')
        backup(self.path, target)
        with connect(target) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_answer_filters_metadata_selection_and_privacy(self):
        self.s.submit(self.admin, self.event())
        options={'metadata_fields': [], 'answer_filters': [{'question_id': self.qs[1]['id'], 'op': 'contains', 'value': 'b'}]}
        export=self.export(**options)
        self.assertEqual(export.count, 1)
        self.assertNotIn('location', export.columns)
        self.assertIn('version_id', export.columns)
        self.assertEqual(len(self.parse(export)), 1)
        self.assertEqual(self.export(answer_filters=[{'question_id':self.qs[4]['id'],'op':'state','value':'not_sure'}]).count,1)
        with self.assertRaises(Problem):
            self.export(answer_filters=[{'question_id':self.qs[3]['id'],'op':'equals','value':'Protected person'}])

    def test_correction_retries_are_idempotent_and_order_is_stable(self):
        event=self.event()
        self.s.submit(self.admin,event)
        correction={'id':new_id(),'answers':event['answers'],'reason':'Initial verification'}
        first=self.s.correct(self.admin,event['id'],correction)
        self.assertEqual(first,self.s.correct(self.admin,event['id'],correction))
        for n in range(10):
            correction={'id':new_id(),'answers':{**event['answers'],self.qs[2]['id']:{'state':'answered','value':n}},'reason':f'Verified revision {n}','base_correction_id':first['id']}
            first=self.s.correct(self.admin,event['id'],correction)
        self.assertEqual(self.parse(self.export())[0][self.export().prefix(self.version,self.qs[2])],'9')

    def test_interrupted_stream_is_audited(self):
        self.s.submit(self.admin,self.event())
        export=self.export()
        stream=export.stream()
        next(stream)
        next(stream)
        stream.close()
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT state FROM export_audits WHERE id=?',(export.audit_id,)).fetchone()[0],'interrupted')

    def test_starter_is_editable_and_uses_independent_ids(self):
        a=self.s.apply_template(self.admin,'agal-livelihood-starter')
        b=self.s.apply_template(self.admin,'agal-livelihood-starter')
        fa=self.s.forms(self.admin,a['id'])[0]
        fb=self.s.forms(self.admin,b['id'])[0]
        self.assertNotEqual(fa['draft']['sections'][0]['questions'][0]['id'],fb['draft']['sections'][0]['questions'][0]['id'])
        self.assertEqual(self.s.versions(self.admin,a['id']),[])

    def test_deidentified_metadata_has_per_export_pseudonyms(self):
        event=self.event()
        self.s.submit(self.admin,event)
        first=self.parse(self.export(anonymize=True))[0]
        second=self.parse(self.export(anonymize=True))[0]
        self.assertNotEqual(first['interview_id'],event['id'])
        self.assertNotEqual(first['interview_id'],second['interview_id'])
        for field in ('location','created_at','updated_at','correction_id','respondent_id','researcher_id'):
            self.assertNotIn(field,first)
        with self.assertRaises(Problem):
            self.export(anonymize=True,include_identifiers=True)

    def test_researcher_can_export_own_nonprotected_interviews(self):
        self.s.submit(self.admin,self.event())
        user=self.researcher()
        event=self.event()
        del event['answers'][self.qs[3]['id']]
        self.s.submit(user,event)
        rows=self.parse(Export(self.s,user,{'project_id':self.project['id']}))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['interview_id'],event['id'])
        self.assertFalse(any(self.qs[3]['id'] in key for key in rows[0]))

    def test_retention_removes_expired_responses_with_audit(self):
        self.s.submit(self.admin,self.event(created_at='2000-01-01T00:00:00Z'))
        self.s.submit(self.admin,self.event())
        self.s.save_project(self.admin,{**self.project,'config':{**self.project['config'],'retention_days':1}},self.project['id'])
        result=self.s.retention(self.admin,self.project['id'])
        self.assertEqual(result['deleted_interviews'],1)
        self.assertEqual(self.export().count,1)
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT record_count FROM retention_events').fetchone()[0],1)

    def test_http_auth_sync_csv(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.s))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}/api'
        try:
            with self.assertRaises(HTTPError) as denied:
                urlopen(root + '/projects')
            self.assertEqual(denied.exception.code, 401)
            def post(path, data):
                return urlopen(Request(root + path, json.dumps(data).encode(), {'Authorization': 'Bearer ' + self.login['token'], 'Content-Type': 'application/json'}))
            with post('/sync', {'events': [self.event()]}) as response:
                self.assertTrue(json.load(response)['results'][0]['ok'])
            with post('/exports/csv', {'project_id': self.project['id'], 'format': 'long'}) as response:
                self.assertEqual(response.headers['X-Record-Count'], '1')
                self.assertIn('Filipino text', response.read().decode())
            def delete(path, data):
                return urlopen(Request(root + path, json.dumps(data).encode(), {'Authorization': 'Bearer ' + self.login['token'], 'Content-Type': 'application/json'}, method='DELETE'))
            with self.assertRaises(HTTPError) as denied_delete:
                delete('/projects/' + self.project['id'], {'confirm_name': 'Wrong'})
            self.assertEqual(denied_delete.exception.code, 400)
            with delete('/projects/' + self.project['id'], {'confirm_name': self.project['name']}) as response:
                self.assertTrue(json.load(response)['deleted'])
            with urlopen(Request(root + '/projects', headers={'Authorization': 'Bearer ' + self.login['token']})) as response:
                self.assertEqual(json.load(response), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
