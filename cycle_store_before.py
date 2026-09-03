"""
Part 13: Period tracking database.

Stores a HISTORY of logged period start dates (not just one date), keyed by
an anonymous device ID (a random ID stored in a cookie - NOT tied to any
real identity or account). This is a placeholder until real login exists;
when it does, device_id just gets replaced with a real account ID, nothing
else about this file needs to change.

Automatically computes average cycle length from the person's own logged
history once there are at least 2 entries, instead of relying on a guess.
"""

import sqlite3
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cycle_data.db")


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS period_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            period_start_date TEXT NOT NULL,
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


def log_period_start(device_id, period_start_date_str):
    conn = _get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM period_logs WHERE device_id = ? AND period_start_date = ?",
            (device_id, period_start_date_str),
        ).fetchone()
        if existing:
            return  # already logged this exact date - don't create a duplicate
        conn.execute(
            "INSERT INTO period_logs (device_id, period_start_date) VALUES (?, ?)",
            (device_id, period_start_date_str),
        )
        conn.commit()
    finally:
        conn.close()


def get_period_history(device_id, limit=12):
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT period_start_date FROM period_logs WHERE device_id = ? ORDER BY period_start_date DESC LIMIT ?",
            (device_id, limit),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def compute_avg_cycle_length(device_id, fallback=28):
    history = get_period_history(device_id, limit=12)
    if len(history) < 2:
        return fallback
    dates = sorted([date.fromisoformat(d) for d in history])
    diffs = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    diffs = [d for d in diffs if 15 <= d <= 90]  # filter out obvious logging errors
    if not diffs:
        return fallback
    avg = round(sum(diffs) / len(diffs))
    return max(21, min(avg, 60))


def get_latest_period_start(device_id):
    history = get_period_history(device_id, limit=1)
    return history[0] if history else None


def delete_history(device_id):
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM period_logs WHERE device_id = ?", (device_id,))
        conn.commit()
    finally:
        conn.close()