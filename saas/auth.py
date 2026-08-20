"""
Password hashing + session management. Stdlib-only (PBKDF2-HMAC-SHA256) so
the project doesn't need bcrypt/passlib installed to run.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from db import get_db, now_iso

PBKDF2_ITERATIONS = 210_000
SESSION_TTL_DAYS = 30


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password, salt, expected_hash):
    computed, _ = hash_password(password, salt)
    return hmac.compare_digest(computed, expected_hash)


def create_user(email, password):
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            return None, "An account with that email already exists."
        pw_hash, salt = hash_password(password)
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, password_salt, created_at) VALUES (?,?,?,?) RETURNING id",
            (email, pw_hash, salt, now_iso())
        )
        new_id = cur.fetchone()['id']
        conn.commit()
        return new_id, None
    finally:
        conn.close()


def authenticate(email, password):
    conn = get_db()
    try:
        row = conn.execute("SELECT id, password_hash, password_salt FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            return None
        if not verify_password(password, row['password_salt'], row['password_hash']):
            return None
        return row['id']
    finally:
        conn.close()


def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_session(user_id):
    """Enforces one active session per account: logging in anywhere new
    invalidates every other session for this user, so sharing an email +
    password only ever gives one person access at a time -- the most
    recent login wins, and whoever got logged out has to sign back in
    (and, in doing so, would kick the other person out again)."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    conn = get_db()
    try:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (_hash_token(token), user_id, now_iso(), expires_at)
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_user_from_session(token):
    if not token:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT s.user_id, s.expires_at, u.email, u.stripe_customer_id FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash=?",
            (_hash_token(token),)
        ).fetchone()
        if not row:
            return None
        if row['expires_at'] < now_iso():
            return None
        return {'id': row['user_id'], 'email': row['email'], 'stripe_customer_id': row['stripe_customer_id']}
    finally:
        conn.close()


def destroy_session(token):
    if not token:
        return
    conn = get_db()
    try:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
        conn.commit()
    finally:
        conn.close()
