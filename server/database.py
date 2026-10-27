"""Single-host pilot database; password hashes and hashed account/device tokens."""

import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT);
CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS cameras(id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, armed INTEGER DEFAULT 0, notify INTEGER DEFAULT 1,
 device_hash TEXT UNIQUE, pair_hash TEXT UNIQUE, pair_expires REAL, last_seen REAL, capture TEXT DEFAULT 'offline');
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, camera_id TEXT REFERENCES cameras(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL, kind TEXT NOT NULL, observed_at REAL NOT NULL, created REAL NOT NULL,
 origin TEXT NOT NULL, review TEXT DEFAULT 'unreviewed', snapshot BLOB, UNIQUE(camera_id,source_id));
CREATE TABLE IF NOT EXISTS installs(token TEXT PRIMARY KEY, session_hash TEXT REFERENCES sessions(hash) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS pushes(id TEXT PRIMARY KEY, token TEXT REFERENCES installs(token) ON DELETE CASCADE,
 event_id TEXT REFERENCES events(id) ON DELETE CASCADE, created REAL NOT NULL, next_at REAL NOT NULL,
 state TEXT DEFAULT 'queued', attempts INTEGER DEFAULT 0, ticket TEXT, detail TEXT);
"""


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def uid():
    return secrets.token_hex(16)


def initialize(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    with connection(path) as db:
        db.executescript(SCHEMA)
    path.chmod(0o600)


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def invite(path, hours=24):
    initialize(path)
    code = secrets.token_urlsafe(24)
    with connection(path) as db:
        db.execute("INSERT INTO invites VALUES (?,?)", (digest(code), time.time() + hours * 3600))
    return code
