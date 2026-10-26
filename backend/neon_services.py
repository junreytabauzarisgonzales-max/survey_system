"""Neon Auth and Object Storage adapters for the hosted deployment.

These services are optional. Offline SQLite installations keep their existing
local password and database-backed attachment behavior.
"""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model import Problem, require

NEON_PASSWORD_PREFIX = '!neon-auth:'


class NeonAuth:
    """Server-side client for Managed Better Auth.

    The app keeps its existing local session tokens. Neon Auth owns the
    credentials, and the hosted service maps a verified identity to the local
    account row so project authorization remains unchanged.
    """

    def __init__(self, base_url, origin):
        self.base_url = base_url.rstrip('/')
        self.origin = origin.rstrip('/')

    @classmethod
    def from_env(cls, environment=None):
        environment = os.environ if environment is None else environment
        base_url = environment.get('NEON_AUTH_BASE_URL', '')
        if not base_url:
            return None
        origin = environment.get('NEON_AUTH_ORIGIN', '')
        if not origin:
            host = environment.get('VERCEL_PROJECT_PRODUCTION_URL') or environment.get('VERCEL_URL')
            if host:
                origin = host if '://' in host else 'https://' + host
        return cls(base_url, origin or 'http://localhost:8765')

    def _call(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Origin': self.origin},
            method='POST',
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode('utf-8') or '{}')
        except HTTPError as error:
            try:
                body = json.loads(error.read().decode('utf-8') or '{}')
            except (ValueError, UnicodeDecodeError):
                body = {}
            code = str(body.get('code', ''))
            if error.code in (409, 422) or code.startswith('USER_ALREADY_EXISTS'):
                raise Problem('An account with this email already exists', 409)
            if error.code == 401 or code == 'INVALID_EMAIL_OR_PASSWORD':
                raise Problem('Invalid credentials', 401)
            if error.code == 403 or code == 'INVALID_ORIGIN':
                raise Problem('Authentication origin is not trusted. Add this app origin in Neon Auth settings.', 503)
            raise Problem('Authentication service unavailable', 503)
        except (URLError, TimeoutError, OSError):
            raise Problem('Authentication service unavailable', 503)

    def sign_up(self, email, password, name):
        result = self._call('/sign-up/email', {'email': email, 'password': password, 'name': name})
        require(isinstance(result.get('user'), dict), 'Authentication service returned an invalid response', 503)
        return result['user']

    def sign_in(self, email, password):
        result = self._call('/sign-in/email', {'email': email, 'password': password})
        require(isinstance(result.get('user'), dict), 'Authentication service returned an invalid response', 503)
        return result['user']


class ObjectStorage:
    """S3-compatible Neon Object Storage adapter."""

    def __init__(self, bucket, endpoint, region, access_key, secret_key):
        self.bucket = bucket
        self.endpoint = endpoint
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self._client = None

    @classmethod
    def from_env(cls, environment=None):
        environment = os.environ if environment is None else environment
        values = (
            environment.get('AWS_ACCESS_KEY_ID', ''),
            environment.get('AWS_SECRET_ACCESS_KEY', ''),
            environment.get('AWS_ENDPOINT_URL_S3', ''),
            environment.get('AWS_REGION', ''),
        )
        if not all(values):
            return None
        return cls(environment.get('NEON_STORAGE_BUCKET', 'assets'), values[2], values[3], values[0], values[1])

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(s3={'addressing_style': 'path'}, signature_version='s3v4'),
            )
        return self._client

    def key(self, interview, attachment):
        return 'attachments/' + interview + '/' + attachment

    def put(self, key, content, mime):
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=mime)
        except Exception:
            raise Problem('Attachment storage is unavailable', 503)

    def get(self, key):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response['Body'].read()
        except Exception:
            raise Problem('Attachment storage is unavailable', 503)

    def delete(self, keys):
        keys = [key for key in keys if key]
        if not keys:
            return
        try:
            self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': [{'Key': key} for key in keys[:1000]]})
        except Exception:
            # Database deletion already succeeded; a retryable orphan is safer
            # than reporting the confirmed record deletion as a failure.
            return


def row_value(row, key, default=None):
    keys = row.keys() if hasattr(row, 'keys') else ()
    return row[key] if key in keys else default


def insert_attachment(connection, storage, attachment, interview, question, filename, mime, content, created, key):
    """Insert an attachment using local bytes or hosted object storage."""
    if storage:
        connection.execute(
            'INSERT INTO attachments(id,interview_id,question_id,filename,mime,content,created_at,storage_key) '
            'VALUES(?,?,?,?,?,?,?,?)',
            (attachment, interview, question, filename, mime, b'', created, key),
        )
    else:
        connection.execute(
            'INSERT INTO attachments VALUES(?,?,?,?,?,?,?)',
            (attachment, interview, question, filename, mime, content, created),
        )


def attachment_content(row, storage):
    key = row_value(row, 'storage_key')
    if key:
        require(storage is not None, 'Attachment storage is not configured', 503)
        return storage.get(key)
    return row['content']
