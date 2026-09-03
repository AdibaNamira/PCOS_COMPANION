"""
Per-user chat history.

Replaces the in-memory LAST_SOURCE_BY_DEVICE dict in app.py, which lost
everything on server restart and never persisted a conversation.

Stores the patient message and the bot's final (post-verifier) response,
plus the source note needed to answer "where did that come from?"
follow-ups. Note this is the SAFE response text - what the patient
actually saw - not the raw model output, so a blocked hallucination is
never persisted as if it were a real answer.

This table holds sensitive health conversation content tied to a real
account. Treat cycle_data.db accordingly: keep it out of git, and delete
it rather than share it when passing the project around.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cycle_data.db")


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            patient_message TEXT NOT NULL,
            bot_response TEXT NOT NULL,
            interaction_id TEXT,
            source_note TEXT,
            flagged INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages (user_id, id)")
    return conn


def save_turn(user_id, patient_message, bot_response, interaction_id=None,
              source_note=None, flagged=False):
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO chat_messages (user_id, created_at, patient_message, "
            "bot_response, interaction_id, source_note, flagged) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                datetime.now(timezone.utc).isoformat(),
                patient_message,
                bot_response,
                interaction_id,
                json.dumps(source_note) if source_note else None,
                1 if flagged else 0,
            ),
        )
        conn.commit()
    except Exception as e:
        # A history write must never break the conversation itself.
        print(f"[warning] could not save chat turn: {e}")
    finally:
        conn.close()


def get_history(user_id, limit=100):
    """Oldest-first, so the UI can replay it straight into the transcript."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_last_source(user_id):
    """Most recent stored source note, for 'where did that come from?' follow-ups."""
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT source_note FROM chat_messages WHERE user_id = ? AND source_note IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row or not row["source_note"]:
            return None
        try:
            return json.loads(row["source_note"])
        except (ValueError, TypeError):
            return None
    finally:
        conn.close()


def delete_history(user_id):
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
