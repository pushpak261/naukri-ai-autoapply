"""Dashboard identities and revocable sessions, separate from platform credentials."""
import hashlib
import hmac
import secrets
import sqlite3
import os
from pathlib import Path
import time
import uuid
from contextlib import closing, contextmanager

from api.deps import root_state


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f'pbkdf2_sha256${salt}${digest}'


def matches(password, encoded):
    try:
        return hmac.compare_digest(password_hash(password, encoded.split('$')[1]), encoded)
    except (ValueError, IndexError):
        return False


def workspace_base():
    return Path(os.environ.get('DASHBOARD_DATA_DIR') or root_state.settings.data_dir)


@contextmanager
def database():
    path = workspace_base() / 'dashboard_identities.db'
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password_hash TEXT NOT NULL, is_operator INTEGER NOT NULL DEFAULT 0)')
        conn.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL)')
        yield conn


def seed_operator():
    configured = root_state.settings.naukri
    if not configured.email or not configured.password:
        return
    email = configured.email.strip().casefold()
    with database() as conn:
        if conn.execute('SELECT 1 FROM users WHERE is_operator=1').fetchone() is None:
            conn.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, 1)',
                         ('operator', email, 'Operator', password_hash(configured.password)))


def find_user(email):
    with database() as conn:
        row = conn.execute('SELECT * FROM users WHERE email=?', (email.strip().casefold(),)).fetchone()
        return dict(row) if row else None


def create_user(email, password, name):
    seed_operator()
    identifier = uuid.uuid4().hex
    with database() as conn:
        conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)',
                     (identifier, email.strip().casefold(), name.strip(), password_hash(password)))
    return find_user(email)


def authenticate(email, password):
    seed_operator()
    user = find_user(email)
    if user and matches(password, user['password_hash']):
        return user
    return None


def remember_session(user_id, token):
    with database() as conn:
        conn.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        conn.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                     (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time()+7*24*3600))


def consume_session(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE token_hash=? AND expires>?', (token_hash, time.time())).fetchone()
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))
        return dict(row) if row else None


def revoke_session(token):
    with database() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))


def all_users():
    with database() as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM users')]
