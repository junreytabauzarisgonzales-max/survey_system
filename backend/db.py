import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def new_id():
    return str(uuid.uuid4())


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path):
    conn = sqlite3.connect(path, timeout=30, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


def migrate(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for script in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
            if not conn.execute('SELECT 1 FROM migrations WHERE name=?', (script.name,)).fetchone():
                sql = script.read_text(encoding='utf-8')
                rebuild = '-- rebuild-with-foreign-keys-off' in sql
                if rebuild:
                    conn.execute('PRAGMA foreign_keys=OFF')
                try:
                    # Leave the transaction open so integrity and the migration marker
                    # are verified/committed atomically with any table rebuild.
                    conn.executescript('BEGIN IMMEDIATE;\n' + sql)
                    if conn.execute('PRAGMA foreign_key_check').fetchone():
                        raise sqlite3.IntegrityError('Migration failed foreign-key validation')
                    conn.execute('INSERT INTO migrations VALUES(?,?)', (script.name, now()))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    if rebuild:
                        conn.execute('PRAGMA foreign_keys=ON')


def history(conn, kind, resource, actor, snapshot):
    conn.execute('INSERT INTO history VALUES(?,?,?,?,?,?)', (new_id(), kind, resource, actor, encode(snapshot), now()))


def bootstrap(path, email, password):
    if len(password) < 8:
        raise ValueError('Administrator password must contain at least 8 characters')
    with connect(path) as conn:
        conn.execute('INSERT INTO users(id,email,name,password,admin) VALUES(?,?,?,?,1)', (new_id(), email.lower(), 'Administrator', password_hash(password)))


def backup(path, destination):
    """SQLite backup API includes committed WAL content; never copy a live db file."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as source, connect(target) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
