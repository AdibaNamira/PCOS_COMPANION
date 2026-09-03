"""
Authentication storage layer.

Holds the users table and the short-lived email 2FA codes. Kept separate
from cycle_store.py so the auth concern stays in one place, but uses the
same SQLite file so there's only one database to back up or delete.

SECURITY NOTES (deliberate, please don't "simplify" these away):
- Passwords are never stored, only scrypt hashes via werkzeug.
- The 2FA code is ALSO hashed before storage. A leaked DB should not let
  someone walk in with a live code.
- Codes expire (10 min) and have a hard attempt limit (5) to stop brute
  forcing a 6-digit number.
- Email lookups are case-insensitive and stored lowercase, so
  Sam@x.com and sam@x.com can't become two accounts.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cycle_data.db")

CODE_TTL_MINUTES = 10
MAX_CODE_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8


def _now():
    return datetime.now(timezone.utc)


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            consumed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_user ON login_codes (user_id)")
    return conn


# --- Accounts ---------------------------------------------------------

def create_user(email, password):
    """
    Returns (user_id, None) on success, or (None, error_message).
    """
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return None, "That doesn't look like a valid email address."
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return None, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."

    conn = _get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), _now().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid, None
    except sqlite3.IntegrityError:
        return None, "An account with that email already exists."
    finally:
        conn.close()


def verify_credentials(email, password):
    """
    Returns the user row on success, None on any failure.
    Deliberately does NOT distinguish "no such user" from "wrong password"
    to callers - that difference leaks which emails are registered.
    """
    email = (email or "").strip().lower()
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            # Still spend the time hashing so a missing account isn't
            # detectably faster than a wrong password.
            check_password_hash(generate_password_hash("dummy"), password or "")
            return None
        if not check_password_hash(row["password_hash"], password or ""):
            return None
        return dict(row)
    finally:
        conn.close()


def get_user(user_id):
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def mark_logged_in(user_id):
    conn = _get_connection()
    try:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now().isoformat(), user_id))
        conn.commit()
    finally:
        conn.close()


# --- Email 2FA codes --------------------------------------------------

def issue_login_code(user_id):
    """
    Generates a fresh 6-digit code, invalidates any earlier unused ones,
    stores only its hash, and returns the plaintext code so the caller can
    email it. The plaintext is never persisted.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = (_now() + timedelta(minutes=CODE_TTL_MINUTES)).isoformat()

    conn = _get_connection()
    try:
        conn.execute("UPDATE login_codes SET consumed = 1 WHERE user_id = ? AND consumed = 0", (user_id,))
        conn.execute(
            "INSERT INTO login_codes (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, generate_password_hash(code), expires_at),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def verify_login_code(user_id, submitted_code):
    """
    Returns (True, None) if the code is valid, else (False, reason).
    Consumes the code on success so it can't be replayed.
    """
    submitted_code = (submitted_code or "").strip()
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM login_codes WHERE user_id = ? AND consumed = 0 "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        if row is None:
            return False, "That code has already been used. Please request a new one."

        if datetime.fromisoformat(row["expires_at"]) < _now():
            conn.execute("UPDATE login_codes SET consumed = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return False, "That code has expired. Please request a new one."

        if row["attempts"] >= MAX_CODE_ATTEMPTS:
            conn.execute("UPDATE login_codes SET consumed = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return False, "Too many incorrect attempts. Please request a new code."

        conn.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        conn.commit()

        if not check_password_hash(row["code_hash"], submitted_code):
            remaining = MAX_CODE_ATTEMPTS - (row["attempts"] + 1)
            if remaining <= 0:
                return False, "Too many incorrect attempts. Please request a new code."
            return False, f"That code isn't right. {remaining} attempt(s) left."

        conn.execute("UPDATE login_codes SET consumed = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return True, None
    finally:
        conn.close()
