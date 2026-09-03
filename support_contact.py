"""
Support source contact: one trusted person the patient can choose to
alert, on their own initiative, when they're in crisis.

CONSENT DESIGN (deliberate, please keep): nothing here sends anything on
its own. The contact is added by the patient in a calm moment, and the
alert only fires when the patient presses the button. design_principles.md
lists "never pressure or insist on disclosure to others" and "always
respect the patient's pace and autonomy" as hard rules - an automatic
disclosure at the moment of crisis would break both.

Rate limiting exists so a distressed patient tapping repeatedly doesn't
send their contact fifteen identical emails.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cycle_data.db")

ALERT_COOLDOWN_MINUTES = 10


def _now():
    return datetime.now(timezone.utc)


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_contacts (
            user_id INTEGER PRIMARY KEY,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            relationship TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0
        )
    """)
    return conn


def save_contact(user_id, name, email, relationship=None):
    """Returns (True, None) or (False, error_message). One contact per user."""
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not name:
        return False, "Please enter a name."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "That doesn't look like a valid email address."

    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO support_contacts (user_id, contact_name, contact_email, relationship, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET contact_name=excluded.contact_name, "
            "contact_email=excluded.contact_email, relationship=excluded.relationship",
            (user_id, name, email, (relationship or "").strip() or None, _now().isoformat()),
        )
        conn.commit()
        return True, None
    finally:
        conn.close()


def get_contact(user_id):
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM support_contacts WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_contact(user_id):
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM support_contacts WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def recently_alerted(user_id):
    """True if an alert went out within the cooldown window."""
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT sent_at FROM support_alerts WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            return False
        return datetime.fromisoformat(row["sent_at"]) > _now() - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
    finally:
        conn.close()


def log_alert(user_id, contact_email, delivered):
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO support_alerts (user_id, sent_at, contact_email, delivered) VALUES (?, ?, ?, ?)",
            (user_id, _now().isoformat(), contact_email, 1 if delivered else 0),
        )
        conn.commit()
    finally:
        conn.close()
