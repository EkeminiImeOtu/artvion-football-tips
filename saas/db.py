"""
Database layer for the subscription product -- PostgreSQL (e.g. Render's
free Postgres tier). Migrated from an earlier SQLite version.

The call sites in auth.py and app.py are untouched by this migration: this
module wraps psycopg2 in a thin shim that keeps the same
conn.execute(sql, params).fetchone()/.fetchall() shape sqlite3 gave them,
translating '?' placeholders to psycopg2's '%s' automatically and returning
dict-like rows (row['column']) the same way sqlite3.Row did.
"""
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _Conn:
    """sqlite3-shaped wrapper over a psycopg2 connection."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace('?', '%s'), params)
        return _Cursor(cur)

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. On Render, attach a free Postgres database and it's "
            "provided automatically; locally, put it in saas/.env -- see .env.example."
        )
    pg_conn = psycopg2.connect(DATABASE_URL)
    return _Conn(pg_conn)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            stripe_customer_id TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'inactive',
            current_period_end TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            scan_date TEXT NOT NULL,
            match_date TEXT NOT NULL,
            league TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            market TEXT NOT NULL,
            display TEXT NOT NULL,
            confidence TEXT,
            odds REAL,
            reasons TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            actual_home INTEGER,
            actual_away INTEGER,
            resolved_at TEXT,
            published_at TEXT NOT NULL,
            UNIQUE(match_date, home_team, away_team, market, display)
        );

        CREATE INDEX IF NOT EXISTS idx_predictions_scan_date ON predictions(scan_date);
    ''')
    conn.commit()
    conn.close()


def is_active_subscriber(conn, user_id):
    row = conn.execute(
        "SELECT status, current_period_end FROM subscriptions WHERE user_id=?", (user_id,)
    ).fetchone()
    if not row:
        return False
    if row['status'] not in ('active', 'trialing'):
        return False
    if row['current_period_end'] and row['current_period_end'] < now_iso():
        return False
    return True
