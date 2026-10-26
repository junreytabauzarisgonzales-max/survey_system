"""Public, version-pinned surveys. Capabilities can submit but never read responses."""
import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone

from .db import connect, encode, history, new_id, now
from .model import Problem, questions, require, text, uid, validate_answers
from .neon_services import insert_attachment

MEDIA_TYPES = {'image/jpeg', 'image/png', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'application/pdf'}


def protected(schema):
    return any(q.get('sensitive') or q['type'] in ('location', 'media') for q in questions(schema))


def expiry(value):
    if value in (None, ''):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(stamp.tzinfo is not None, 'Expiration must include a timezone')
        return stamp.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    except (AttributeError, TypeError, ValueError):
        raise Problem('Expiration must be an ISO 8601 timestamp with timezone')


def link_record(row):
    return {key: bool(row[key]) if key == 'enabled' else row[key]
            for key in ('id', 'project_id', 'version_id', 'token', 'name', 'created_by', 'created_at', 'expires_at', 'enabled', 'revision')}


class PublicSurveys:
    def public_links(self, actor, project):
        with connect(self.path) as c:
            self.access(c, actor, project, 'manage')
            return [link_record(row) for row in c.execute('SELECT * FROM public_links WHERE project_id=? ORDER BY created_at,id', (project,))]

    def save_public_link(self, actor, project, data, link_id=None):
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            access = self.access(c, actor, project, 'manage')
            old = None
            if link_id:
                old = c.execute('SELECT * FROM public_links WHERE id=? AND project_id=?', (link_id, project)).fetchone()
                require(old, 'Public link not found', 404)
                require(data.get('revision') == old['revision'], 'Public link changed; reload before saving', 409)
                for key in ('version_id', 'project_id', 'token', 'created_by'):
                    require(key not in data or data[key] == old[key], 'Create a new link to share a different questionnaire version')
                version_id = old['version_id']
            else:
                version_id = uid(data.get('version_id'))
            version = c.execute('SELECT v.*,f.archived FROM versions v JOIN forms f ON f.id=v.form_id WHERE v.id=? AND f.project_id=?', (version_id, project)).fetchone()
            require(version, 'Published questionnaire version not found in this project', 404)
            enabled = data.get('enabled', True)
            require(isinstance(enabled, bool), 'Enabled must be boolean')
            if enabled:
                require(not access['project']['archived'] and not version['archived'], 'Reactivate the project and questionnaire before sharing')
                require(access['identifiable'] or not protected(json.loads(version['schema'])), 'Identifiable-data permission required to share this questionnaire', 403)
            name = text(data.get('name'), 'link name', 300)
            expires_at = expiry(data.get('expires_at'))
            if not old:
                require(expires_at is None or expires_at > now(), 'Expiration must be in the future')
                link_id = new_id()
                c.execute('INSERT INTO public_links VALUES(?,?,?,?,?,?,?,?,?,1,?)',
                          (link_id, project, version_id, secrets.token_urlsafe(32), name, actor['id'], now(), expires_at, enabled, encode(access['project']['config'].get('locations', []))))
            else:
                c.execute('UPDATE public_links SET name=?,expires_at=?,enabled=?,revision=revision+1 WHERE id=?', (name, expires_at, enabled, link_id))
            result = link_record(c.execute('SELECT * FROM public_links WHERE id=?', (link_id,)).fetchone())
            history(c, 'public_link', link_id, actor['id'], result)
            return result

    def _public_link(self, c, token, live=True):
        require(isinstance(token, str) and len(token) <= 100, 'Survey not found', 404)
        row = c.execute('SELECT l.*,v.schema,v.number,p.name AS project_name,p.archived AS project_archived,f.archived AS form_archived '
                        'FROM public_links l JOIN versions v ON v.id=l.version_id JOIN forms f ON f.id=v.form_id AND f.project_id=l.project_id '
                        'JOIN projects p ON p.id=l.project_id WHERE l.token=?', (token,)).fetchone()
        require(row, 'Survey not found', 404)
        if live:
            message = 'This survey link is no longer accepting responses.'
            require(row['enabled'] and not row['project_archived'] and not row['form_archived'] and (not row['expires_at'] or row['expires_at'] > now()), message, 410)
            creator = c.execute('SELECT * FROM users WHERE id=? AND active=1', (row['created_by'],)).fetchone()
            require(creator, message, 410)
            try:
                access = self.access(c, dict(creator), row['project_id'], 'manage')
            except Problem:
                raise Problem(message, 410)
            require(access['identifiable'] or not protected(json.loads(row['schema'])), message, 410)
        return row

    def public_survey(self, token):
        with connect(self.path) as c:
            row = self._public_link(c, token)
            # Deliberately do not serialize link records, staff, profile fields,
            # project configuration, other forms, or existing interview values.
            return {'title': json.loads(row['schema'])['form_name'], 'project_name': row['project_name'],
                    'version_number': row['number'], 'schema': json.loads(row['schema']), 'locations': json.loads(row['locations']),
                    'attachment_limit': self.attachment_limit}

    def submit_public(self, token, data):
        require(set(data) <= {'submission_id', 'answers', 'consent', 'location_consent', 'location', 'attachments'}, 'Unknown public submission fields')
        submission_id = uid(data.get('submission_id'))
        fingerprint = hashlib.sha256(json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()).hexdigest()
        uploaded = []
        try:
            with connect(self.path) as c:
                c.execute('BEGIN IMMEDIATE')
                row = self._public_link(c, token, live=False)
                prior = c.execute('SELECT * FROM public_receipts WHERE submission_id=?', (submission_id,)).fetchone()
                if prior:
                    require(prior['link_id'] == row['id'] and prior['fingerprint'] == fingerprint, 'Submission key was already used for different answers', 409)
                    # Acknowledging an existing receipt remains safe after closure/retention.
                    return {'submitted': True, 'receipt': prior['receipt']}
                self._public_link(c, token)
                require(data.get('consent') is True, 'Consent is required to submit this survey')
                require(isinstance(data.get('location_consent', False), bool), 'Location consent must be boolean')
                schema = json.loads(row['schema'])
                answers = validate_answers(schema, data.get('answers', {}), complete=True, location_consent=data.get('location_consent', False))
                location = data.get('location') or None
                require(location is None or location in {loc['id'] for loc in json.loads(row['locations'])}, 'Unknown survey location')
                files = data.get('attachments', [])
                require(isinstance(files, list) and len(files) <= 20, 'Use up to 20 attachments per response')
                referenced = {q['id']: answers[q['id']].get('value', []) for q in questions(schema) if q['type'] == 'media'}
                expected = {(qid, aid) for qid, aids in referenced.items() for aid in aids}
                require(len({aid for _, aid in expected}) == sum(len(aids) for aids in referenced.values()), 'Duplicate attachment reference')
                stored, found, total = [], set(), 0
                for file in files:
                    require(isinstance(file, dict), 'Invalid attachment')
                    aid, qid = uid(file.get('id')), uid(file.get('question_id'))
                    require((qid, aid) in expected and aid not in found, 'Attachment does not match a recorded media answer')
                    found.add(aid)
                    require(file.get('mime') in MEDIA_TYPES, 'Unsupported media type')
                    name = text(file.get('filename'), 'filename', 255)
                    try:
                        content = base64.b64decode(file.get('content', ''), validate=True)
                    except (ValueError, TypeError):
                        raise Problem('Invalid base64 attachment')
                    total += len(content)
                    require(0 < len(content) <= self.attachment_limit and total <= self.attachment_limit, f'Total attachments must be at most {self.attachment_limit // (1024 * 1024)} MiB')
                    require(not c.execute('SELECT 1 FROM attachments WHERE id=?', (aid,)).fetchone(), 'Attachment identifier already used', 409)
                    stored.append((aid, qid, name, file['mime'], content))
                require(found == {aid for _, aid in expected}, 'Every attachment reference requires its own file')
                iid, receipt, stamp = new_id(), new_id(), now()
                c.execute("INSERT INTO interviews(id,project_id,version_id,researcher_id,respondent_id,location,status,answers,consent,location_consent,created_at,updated_at,revision,source,public_link_id) VALUES(?,?,?,NULL,NULL,?,'completed',?,1,?,?,?,1,'public_link',?)",
                          (iid, row['project_id'], row['version_id'], location, encode(answers), data.get('location_consent', False), stamp, stamp, row['id']))
                for aid, qid, name, mime, content in stored:
                    key = self.storage.key(iid, aid) if self.storage else None
                    if self.storage:
                        self.storage.put(key, content, mime)
                        uploaded.append(key)
                    insert_attachment(c, self.storage, aid, iid, qid, name, mime, content, stamp, key)
                c.execute('INSERT INTO public_receipts VALUES(?,?,?,?,?,?)', (submission_id, row['id'], fingerprint, iid, receipt, stamp))
                return {'submitted': True, 'receipt': receipt}
        except Exception:
            if self.storage and uploaded:
                self.storage.delete(uploaded)
            raise
