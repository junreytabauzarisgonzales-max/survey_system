import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone

from .db import connect, encode, history, new_id, now, password_hash
from .model import Problem, questions, require, text, uid, validate_answers, validate_config, validate_schema
from .public import PublicSurveys


def unpack(row, *fields):
    result = dict(row)
    for flag in ('archived', 'identifiable', 'active', 'admin'):
        if flag in result:
            result[flag] = bool(result[flag])
    for key in fields:
        if key in result:
            result[key] = json.loads(result[key])
    return result


class Service(PublicSurveys):
    def __init__(self, path):
        self.path = path

    @staticmethod
    def _session(c, user):
        token = secrets.token_urlsafe(40)
        expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat().replace('+00:00', 'Z')
        c.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], expires))
        return {'token': token, 'expires_at': expires, 'user': {k: user[k] for k in ('id', 'name', 'email', 'admin')}}

    def login(self, data):
        with connect(self.path) as c:
            user = c.execute('SELECT * FROM users WHERE email=? AND active=1', (str(data.get('email', '')).lower(),)).fetchone()
            # Hash even unknown users to reduce account enumeration timing differences.
            hashed = password_hash(str(data.get('password', '')), user['password'].split(':')[0] if user else '0' * 32)
            require(user and hmac.compare_digest(hashed, user['password']), 'Invalid credentials', 401)
            return self._session(c, user)

    def register(self, data):
        """Create a self-service account that can immediately own surveys."""
        email = text(data.get('email'), 'email', 300).lower()
        require('@' in email, 'Enter a valid email address')
        name = text(data.get('name'), 'name', 300)
        password = text(data.get('password'), 'password', 1000)
        require(len(password) >= 8, 'Password must contain at least 8 characters')
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            require(not c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone(), 'An account with this email already exists', 409)
            identifier = new_id()
            c.execute('INSERT INTO users(id,email,name,password,admin,active) VALUES(?,?,?,?,0,1)', (identifier, email, name, password_hash(password)))
            history(c, 'user', identifier, identifier, {'email': email, 'name': name})
            user = c.execute('SELECT * FROM users WHERE id=?', (identifier,)).fetchone()
            return self._session(c, user)

    def authenticate(self, token):
        with connect(self.path) as c:
            row = c.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.active=1', (hashlib.sha256(token.encode()).hexdigest(), now())).fetchone()
            require(row is not None, 'Sign in required', 401)
            return dict(row)

    def access(self, c, actor, project, permission='read'):
        row = c.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone()
        require(row is not None, 'Project not found', 404)
        member = c.execute('SELECT * FROM memberships WHERE project_id=? AND user_id=?', (project, actor['id'])).fetchone()
        require(actor['admin'] or member, 'Project access denied', 403)
        role = 'manager' if actor['admin'] else member['role']
        if permission == 'manage':
            require(role == 'manager', 'Project manager permission required', 403)
        if permission == 'collect':
            require(role in ('manager', 'researcher') and not row['archived'], 'Collection is unavailable', 403)
        return {'role': role, 'identifiable': bool(actor['admin'] or member['identifiable']), 'project': unpack(row, 'config')}

    def project_list(self, actor):
        with connect(self.path) as c:
            rows = c.execute('SELECT DISTINCT p.* FROM projects p LEFT JOIN memberships m ON m.project_id=p.id WHERE ?=1 OR m.user_id=? ORDER BY p.created_at', (actor['admin'], actor['id']))
            return [{**unpack(r, 'config'), 'access': {k: v for k, v in self.access(c, actor, r['id']).items() if k != 'project'}} for r in rows]

    def save_project(self, actor, data, project=None):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            if project:
                access = self.access(c, actor, project, 'manage')
                old = access['project']
                require(data.get('revision') == old['revision'], 'Project changed; reload before saving', 409)
            else:
                project = new_id()
                old = None
            name = text(data.get('name'), 'project name', 300)
            description = text(data.get('description', ''), 'description', empty=True)
            config = validate_config(data.get('config', {}))
            require(isinstance(data.get('archived', False), bool), 'Archived must be boolean')
            if old:
                # Keep field definitions used by existing respondents; changes are versioned through project history.
                c.execute('UPDATE projects SET name=?,description=?,config=?,archived=?,revision=revision+1 WHERE id=?', (name, description, encode(config), int(data.get('archived', False)), project))
            else:
                c.execute('INSERT INTO projects VALUES(?,?,?,?,0,1,?)', (project, name, description, encode(config), now()))
                c.execute('INSERT INTO memberships VALUES(?,?,?,1)', (project, actor['id'], 'manager'))
            result = unpack(c.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone(), 'config')
            history(c, 'project', project, actor['id'], result)
            return result

    def duplicate_project(self, actor, project):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            original = self.access(c, actor, project, 'manage')['project']
            target = new_id()
            c.execute('INSERT INTO projects VALUES(?,?,?,?,0,1,?)', (target, original['name'] + ' (copy)', original['description'], encode(original['config']), now()))
            c.execute('INSERT INTO memberships VALUES(?,?,?,1)', (target, actor['id'], 'manager'))
            for form in c.execute('SELECT * FROM forms WHERE project_id=?', (project,)).fetchall():
                fid = new_id()
                c.execute('INSERT INTO forms VALUES(?,?,?,?,1,0)', (fid, target, form['name'], form['draft']))
                history(c, 'form', fid, actor['id'], {'name': form['name'], 'draft': json.loads(form['draft'])})
            copied = unpack(c.execute('SELECT * FROM projects WHERE id=?', (target,)).fetchone(), 'config')
            history(c, 'project', target, actor['id'], {'source_id': project, **copied})
            return {'id': target}

    def delete_project(self, actor, project, data):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            target = self.access(c, actor, project, 'manage')['project']
            require(data.get('confirm_name') == target['name'], 'Type the survey title exactly to confirm deletion')
            forms = [r['id'] for r in c.execute('SELECT id FROM forms WHERE project_id=?', (project,))]
            versions = [r['id'] for r in c.execute('SELECT v.id FROM versions v JOIN forms f ON f.id=v.form_id WHERE f.project_id=?', (project,))]
            links = [r['id'] for r in c.execute('SELECT id FROM public_links WHERE project_id=?', (project,))]
            interviews = [r['id'] for r in c.execute('SELECT id FROM interviews WHERE project_id=?', (project,))]
            respondents = [r['id'] for r in c.execute('SELECT id FROM respondents WHERE project_id=?', (project,))]
            attachments = [r['id'] for r in c.execute('SELECT a.id FROM attachments a JOIN interviews i ON i.id=a.interview_id WHERE i.project_id=?', (project,))]

            def delete_in(table, column, ids):
                if ids:
                    c.execute(f'DELETE FROM {table} WHERE {column} IN ({",".join("?" for _ in ids)})', ids)

            c.execute('INSERT INTO project_deletions(project_id) VALUES(?)', (project,))
            delete_in('public_receipts', 'link_id', links)
            delete_in('attachments', 'interview_id', interviews)
            delete_in('corrections', 'interview_id', interviews)
            c.execute('DELETE FROM interviews WHERE project_id=?', (project,))
            c.execute('DELETE FROM respondents WHERE project_id=?', (project,))
            c.execute('DELETE FROM public_links WHERE project_id=?', (project,))
            delete_in('versions', 'form_id', forms)
            c.execute('DELETE FROM forms WHERE project_id=?', (project,))
            c.execute('DELETE FROM export_audits WHERE project_id=?', (project,))
            c.execute('DELETE FROM retention_events WHERE project_id=?', (project,))
            c.execute('DELETE FROM memberships WHERE project_id=?', (project,))
            c.execute("DELETE FROM sync_events WHERE json_extract(result, '$.project_id')=?", (project,))
            resources = [project, *forms, *versions, *links, *interviews, *respondents, *attachments]
            c.execute("DELETE FROM history WHERE resource_type IN ('project','form','version','membership','respondent','public_link','attachment') AND resource_id IN (" + ",".join("?" for _ in resources) + ")", resources)
            c.execute('DELETE FROM projects WHERE id=?', (project,))
            return {'deleted': True, 'id': project, 'forms': len(forms), 'versions': len(versions), 'links': len(links), 'responses': len(interviews)}

    def templates(self):
        return json.loads((Path(__file__).parent / 'templates.json').read_text(encoding='utf-8'))

    def apply_template(self, actor, template_id):
        template = next((t for t in self.templates() if t['id'] == template_id), None)
        require(template is not None, 'Template not found', 404)
        config = validate_config(template['config'])
        schemas = []
        for form in template['forms']:
            schema = json.loads(encode(form['schema']))
            mapping = {q['id']: new_id() for q in questions(schema)}
            for section in schema['sections']:
                section['id'] = new_id()
                for q in section['questions']:
                    old = q['id']
                    q['id'] = mapping[old]
                    if q.get('condition'):
                        q['condition']['question_id'] = mapping[q['condition']['question_id']]
            schemas.append((form['name'], validate_schema(schema)))
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            project = new_id()
            c.execute('INSERT INTO projects VALUES(?,?,?,?,0,1,?)', (project, template['name'], template['description'], encode(config), now()))
            c.execute('INSERT INTO memberships VALUES(?,?,?,1)', (project, actor['id'], 'manager'))
            history(c, 'project', project, actor['id'], {'id': project, 'name': template['name'], 'config': config, 'template_id': template_id, 'revision': 1})
            for name, schema in schemas:
                form = new_id()
                c.execute('INSERT INTO forms VALUES(?,?,?,?,1,0)', (form, project, name, encode(schema)))
                history(c, 'form', form, actor['id'], {'id': form, 'name': name, 'draft': schema, 'revision': 1})
            return {'id': project}

    def forms(self, actor, project):
        with connect(self.path) as c:
            self.access(c, actor, project)
            return [unpack(r, 'draft') for r in c.execute('SELECT * FROM forms WHERE project_id=? ORDER BY name', (project,))]

    def save_form(self, actor, project, data, form=None):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            self.access(c, actor, project, 'manage')
            name = text(data.get('name'), 'form name', 300)
            schema = validate_schema(data.get('draft'))
            require(isinstance(data.get('archived', False), bool), 'Archived must be boolean')
            if form:
                old = c.execute('SELECT * FROM forms WHERE id=? AND project_id=?', (form, project)).fetchone()
                require(old is not None, 'Form not found', 404)
                require(old['revision'] == data.get('revision'), 'Form changed; reload before saving', 409)
                c.execute('UPDATE forms SET name=?,draft=?,revision=revision+1,archived=? WHERE id=?', (name, encode(schema), int(bool(data.get('archived', False))), form))
            else:
                form = new_id()
                c.execute('INSERT INTO forms VALUES(?,?,?,?,1,0)', (form, project, name, encode(schema)))
            result = unpack(c.execute('SELECT * FROM forms WHERE id=?', (form,)).fetchone(), 'draft')
            history(c, 'form', form, actor['id'], result)
            return result

    def publish(self, actor, form, revision):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            f = c.execute('SELECT * FROM forms WHERE id=?', (form,)).fetchone()
            require(f is not None, 'Form not found', 404)
            self.access(c, actor, f['project_id'], 'manage')
            require(not f['archived'] and f['revision'] == revision, 'Form changed or archived', 409)
            schema = validate_schema(json.loads(f['draft']))
            require(questions(schema), 'Add a question before publishing')
            # An ID may keep its meaning across versions; incompatible types require a new UUID.
            prior = c.execute('SELECT schema FROM versions WHERE form_id=?', (form,)).fetchall()
            current = {q['id']: q for q in questions(schema)}
            for version in prior:
                for q in questions(json.loads(version['schema'])):
                    if q['id'] in current:
                        require(q['type'] == current[q['id']]['type'], 'Changing question type requires a new question ID')
            vid = new_id()
            number = c.execute('SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE form_id=?', (form,)).fetchone()[0]
            schema = {**schema, 'engine_version': 1, 'form_name': f['name'], 'consent': self.access(c, actor, f['project_id'])['project']['config'].get('consent', '')}
            c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)', (vid, form, number, encode(schema), now(), actor['id']))
            history(c, 'version', vid, actor['id'], schema)
            return {'id': vid, 'number': number}

    def versions(self, actor, project):
        with connect(self.path) as c:
            self.access(c, actor, project)
            return [unpack(r, 'schema') for r in c.execute('SELECT v.*,f.project_id,f.name FROM versions v JOIN forms f ON f.id=v.form_id WHERE f.project_id=? ORDER BY v.published_at', (project,))]

    def save_respondent(self, actor, project, data):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            access = self.access(c, actor, project, 'collect')
            require(access['identifiable'], 'Identifiable data permission required', 403)
            schema = access['project']['config'].get('fields')
            require(schema, 'Configure project respondent fields first')
            answers = validate_answers(schema, data.get('data', {}), complete=True)
            rid = uid(data.get('id', new_id()))
            require(not c.execute('SELECT 1 FROM respondents WHERE id=?', (rid,)).fetchone(), 'Respondent already exists', 409)
            c.execute('INSERT INTO respondents VALUES(?,?,?,?,1,?)', (rid, project, actor['id'], encode({'schema': schema, 'answers': answers}), now()))
            history(c, 'respondent', rid, actor['id'], {'schema': schema, 'answers': answers})
            return {'id': rid}

    def respondents(self, actor, project):
        with connect(self.path) as c:
            access = self.access(c, actor, project)
            require(access['identifiable'], 'Identifiable data permission required', 403)
            return [unpack(r, 'data') for r in c.execute('SELECT * FROM respondents WHERE project_id=? AND (?!=\'researcher\' OR researcher_id=?)', (project, access['role'], actor['id']))]

    def submit(self, actor, data):
        event = uid(data.get('event_id'))
        fingerprint = hashlib.sha256(json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()).hexdigest()
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT * FROM sync_events WHERE id=?', (event,)).fetchone()
            if prior:
                require(prior['user_id'] == actor['id'] and prior['fingerprint'] == fingerprint, 'Idempotency key reused with different payload', 409)
                stored = json.loads(prior['result'])
                self.access(c, actor, stored['project_id'])
                return stored
            version = c.execute('SELECT v.*,f.project_id FROM versions v JOIN forms f ON f.id=v.form_id WHERE v.id=?', (uid(data.get('version_id')),)).fetchone()
            require(version is not None, 'Published version not found', 404)
            access = self.access(c, actor, version['project_id'], 'collect')
            iid = uid(data.get('id'))
            existing = c.execute('SELECT * FROM interviews WHERE id=?', (iid,)).fetchone()
            if existing:
                require(existing['researcher_id'] == actor['id'] and existing['project_id'] == version['project_id'], 'Interview access denied', 403)
                require(existing['status'] == 'draft' and existing['revision'] == data.get('revision'), 'Interview completed or changed; use corrections', 409)
                require(existing['version_id'] == version['id'], 'Draft version cannot change')
            status = data.get('status', 'draft')
            require(status in ('draft', 'completed'), 'Invalid response status')
            consent = data.get('consent') is True
            loc_consent = data.get('location_consent') is True
            require(status != 'completed' or consent, 'Consent is required to complete an interview')
            answers = validate_answers(json.loads(version['schema']), data.get('answers', {}), status == 'completed', loc_consent)
            if not access['identifiable']:
                sensitive = {q['id'] for q in questions(json.loads(version['schema'])) if q.get('sensitive') or q['type'] in ('location', 'media')}
                require(not any(answers[q]['state'] == 'answered' for q in sensitive), 'Identifiable data permission required', 403)
            rid = data.get('respondent_id') or None
            if rid:
                respondent = c.execute('SELECT * FROM respondents WHERE id=? AND project_id=?', (uid(rid), version['project_id'])).fetchone()
                require(access['identifiable'] and respondent is not None and (access['role'] != 'researcher' or respondent['researcher_id'] == actor['id']), 'Respondent access denied', 403)
            location = data.get('location') or None
            require(location is None or location in {v['id'] for v in access['project']['config'].get('locations', [])}, 'Unknown project location')
            timestamp = now()
            if existing:
                c.execute('UPDATE interviews SET answers=?,status=?,consent=?,location_consent=?,location=?,respondent_id=?,updated_at=?,revision=revision+1 WHERE id=?', (encode(answers), status, consent, loc_consent, location, rid, timestamp, iid))
            else:
                created = data.get('created_at', timestamp)
                try:
                    require(isinstance(created, str) and datetime.fromisoformat(created.replace('Z', '+00:00')).tzinfo is not None, 'created_at must include timezone')
                    created = datetime.fromisoformat(created.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                except ValueError:
                    raise Problem('Invalid created_at')
                c.execute('INSERT INTO interviews(id,project_id,version_id,researcher_id,respondent_id,location,status,answers,consent,location_consent,created_at,updated_at,revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)', (iid, version['project_id'], version['id'], actor['id'], rid, location, status, encode(answers), consent, loc_consent, created, timestamp))
            result = {'id': iid, 'project_id': version['project_id'], 'revision': existing['revision'] + 1 if existing else 1, 'status': status}
            c.execute('INSERT INTO sync_events VALUES(?,?,?,?,?)', (event, actor['id'], fingerprint, encode(result), timestamp))
            return result

    def correct(self, actor, interview, data):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT i.*,v.schema FROM interviews i JOIN versions v ON v.id=i.version_id WHERE i.id=?', (interview,)).fetchone()
            require(row is not None, 'Interview not found', 404)
            access = self.access(c, actor, row['project_id'], 'collect')
            require(access['role'] == 'manager' or row['researcher_id'] == actor['id'], 'Interview access denied', 403)
            require(access['identifiable'] or not any(q.get('sensitive') or q['type'] in ('location', 'media') for q in questions(json.loads(row['schema']))), 'Identifiable data permission required for corrections to this form', 403)
            require(row['status'] == 'completed', 'Only completed interviews have corrections')
            if data.get('id'):
                prior = c.execute('SELECT * FROM corrections WHERE id=?', (uid(data['id']),)).fetchone()
                if prior:
                    checked = validate_answers(json.loads(row['schema']), data.get('answers'), True, bool(row['location_consent']))
                    require(prior['interview_id'] == interview and prior['actor_id'] == actor['id'] and json.loads(prior['answers']) == checked and prior['reason'] == data.get('reason'), 'Correction ID conflict', 409)
                    return {'id': prior['id']}
            latest = c.execute('SELECT id FROM corrections WHERE interview_id=? ORDER BY rowid DESC LIMIT 1', (interview,)).fetchone()
            require(data.get('base_correction_id') == (latest['id'] if latest else None), 'Correction history changed; reload', 409)
            answers = validate_answers(json.loads(row['schema']), data.get('answers'), True, bool(row['location_consent']))
            reason = text(data.get('reason'), 'correction reason', 2000)
            cid = uid(data['id']) if data.get('id') else new_id()
            c.execute('INSERT INTO corrections VALUES(?,?,?,?,?,?)', (cid, interview, encode(answers), reason, actor['id'], now()))
            return {'id': cid}

    def interviews(self, actor, project, limit=200, after='', interview_id=None):
        require(1 <= limit <= 500, 'Limit must be 1–500')
        with connect(self.path) as c:
            access = self.access(c, actor, project)
            rows = c.execute('SELECT i.*,v.schema FROM interviews i JOIN versions v ON v.id=i.version_id WHERE i.project_id=? AND i.id>? AND (?!=\'researcher\' OR i.researcher_id=?) AND (? IS NULL OR i.id=?) ORDER BY i.id LIMIT ?', (project, after, access['role'], actor['id'], interview_id, interview_id, limit))
            result = []
            for row in rows:
                item = unpack(row, 'answers', 'schema')
                sensitive = {q['id'] for q in questions(item['schema']) if q.get('sensitive') or q['type'] in ('location', 'media')}
                corrections = [unpack(r, 'answers') for r in c.execute('SELECT * FROM corrections WHERE interview_id=? ORDER BY rowid', (row['id'],))]
                if not access['identifiable']:
                    item.pop('respondent_id', None)
                    item['answers'] = {k: v for k, v in item['answers'].items() if k not in sensitive}
                    for correction in corrections:
                        correction['answers'] = {k: v for k, v in correction['answers'].items() if k not in sensitive}
                item['corrections'] = corrections
                result.append(item)
            return result

    def users(self, actor):
        with connect(self.path) as c:
            require(actor['admin'], 'Administrator permission required', 403)
            return [dict(r) for r in c.execute('SELECT id,email,name,admin,active FROM users ORDER BY name')]

    def create_user(self, actor, data):
        require(actor['admin'], 'Administrator permission required', 403)
        email = text(data.get('email'), 'email', 300).lower()
        require('@' in email, 'Invalid email')
        password = text(data.get('password'), 'password', 1000)
        require(len(password) >= 8, 'Password must contain at least 8 characters')
        with connect(self.path) as c:
            identifier = new_id()
            c.execute('INSERT INTO users VALUES(?,?,?,?,0,1)', (identifier, email, text(data.get('name'), 'name', 300), password_hash(password)))
            history(c, 'user', identifier, actor['id'], {'email': email, 'name': data['name']})
            return {'id': identifier}

    def members(self, actor, project, data=None):
        with connect(self.path) as c:
            self.access(c, actor, project, 'manage')
            if data is not None:
                require(data.get('role') in ('manager', 'researcher', 'viewer'), 'Invalid role')
                require(isinstance(data.get('identifiable'), bool), 'Identifiable must be boolean')
                user = data.get('user_id')
                if user:
                    user = uid(user)
                    require(c.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user,)).fetchone(), 'User not found')
                else:
                    email = text(data.get('email'), 'email', 300).lower()
                    found = c.execute('SELECT id FROM users WHERE email=? AND active=1', (email,)).fetchone()
                    require(found is not None, 'No account found with that email', 404)
                    user = found['id']
                c.execute('INSERT INTO memberships VALUES(?,?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role,identifiable=excluded.identifiable', (project, user, data['role'], data['identifiable']))
                history(c, 'membership', project, actor['id'], data)
            return [dict(r) for r in c.execute('SELECT m.*,u.name,u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE project_id=?', (project,))]

    def resource_history(self, actor, project, kind, resource):
        with connect(self.path) as c:
            self.access(c, actor, project, 'manage')
            table = {'project': 'projects', 'form': 'forms', 'version': 'versions', 'respondent': 'respondents', 'membership': 'projects', 'public_link': 'public_links'}.get(kind)
            require(table, 'Unsupported history resource')
            if kind == 'version':
                belongs = c.execute('SELECT 1 FROM versions v JOIN forms f ON f.id=v.form_id WHERE v.id=? AND f.project_id=?', (resource, project)).fetchone()
            elif table == 'projects':
                belongs = resource == project
            else:
                belongs = c.execute(f'SELECT 1 FROM {table} WHERE id=? AND project_id=?', (resource, project)).fetchone()
            require(belongs, 'Resource not found', 404)
            if kind == 'respondent':
                require(self.access(c, actor, project)['identifiable'], 'Identifiable data permission required', 403)
            return [unpack(r, 'snapshot') for r in c.execute('SELECT * FROM history WHERE resource_type=? AND resource_id=? ORDER BY created_at,id', (kind, resource))]

    def retention(self, actor, project):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            config = self.access(c, actor, project, 'manage')['project']['config']
            cutoff = (datetime.now(timezone.utc) - timedelta(days=config.get('retention_days', 3650))).isoformat().replace('+00:00', 'Z')
            targets = 'SELECT id FROM interviews WHERE project_id=? AND created_at<?'
            args = (project, cutoff)
            count = c.execute(f'SELECT COUNT(*) FROM interviews WHERE id IN ({targets})', args).fetchone()[0]
            c.execute(f'DELETE FROM attachments WHERE interview_id IN ({targets})', args)
            c.execute(f'DELETE FROM corrections WHERE interview_id IN ({targets})', args)
            c.execute(f'DELETE FROM interviews WHERE id IN ({targets})', args)
            c.execute('DELETE FROM history WHERE resource_type=\'respondent\' AND resource_id IN (SELECT id FROM respondents WHERE project_id=? AND created_at<? AND id NOT IN (SELECT respondent_id FROM interviews WHERE respondent_id IS NOT NULL))', args)
            c.execute('DELETE FROM respondents WHERE project_id=? AND created_at<? AND id NOT IN (SELECT respondent_id FROM interviews WHERE respondent_id IS NOT NULL)', args)
            c.execute('INSERT INTO retention_events VALUES(?,?,?,?,?,?)', (new_id(), project, actor['id'], count, cutoff, now()))
            return {'deleted_interviews': count, 'cutoff': cutoff}

    def attachment(self, actor, interview, data):
        with connect(self.path) as c:
            row = c.execute('SELECT i.*,v.schema FROM interviews i JOIN versions v ON v.id=i.version_id WHERE i.id=?', (interview,)).fetchone()
            require(row, 'Interview not found', 404)
            access = self.access(c, actor, row['project_id'], 'collect')
            require(access['identifiable'] and (access['role'] == 'manager' or row['researcher_id'] == actor['id']), 'Attachment access denied', 403)
            qid = uid(data.get('question_id'))
            require(any(q['id'] == qid and q['type'] == 'media' for q in questions(json.loads(row['schema']))), 'Not a media question')
            aid = uid(data.get('id'))
            try:
                content = base64.b64decode(data.get('content', ''), validate=True)
            except (ValueError, TypeError):
                raise Problem('Invalid base64 attachment')
            require(0 < len(content) <= 10 * 1024 * 1024, 'Attachment must be 1 byte–10 MiB')
            filename = text(data.get('filename'), 'filename', 255)
            mime = data.get('mime')
            require(mime in ('image/jpeg', 'image/png', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'application/pdf'), 'Unsupported media type')
            prior = c.execute('SELECT * FROM attachments WHERE id=?', (aid,)).fetchone()
            if prior:
                require(prior['interview_id'] == interview and prior['content'] == content and prior['question_id'] == qid and prior['filename'] == filename and prior['mime'] == mime, 'Attachment ID conflict', 409)
            else:
                c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)', (aid, interview, qid, filename, mime, content, now()))
                history(c, 'attachment', aid, actor['id'], {'interview_id': interview, 'filename': filename})
            return {'id': aid}
