"""
Research access to participant data.

PSEUDONYMISATION BY DEFAULT (deliberate): participants are shown as study
IDs (P001, P002...) rather than email addresses. Behavioural analysis
almost never needs to know *who* said something - only that the same
person said several things. Emails are available behind an explicit
reveal, so identifying someone is a conscious act you'd have to justify,
not the default state of the screen you leave open on your desk.

The study ID is derived from the account's row id, so it stays stable
across sessions and exports without storing anything extra.

ACCESS: restricted to the addresses in the ADMIN_EMAILS environment
variable. There is no admin flag in the database on purpose - an
attacker who gets write access to the DB still cannot promote themselves
to researcher without also editing the server's environment.
"""

import os
import sqlite3
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cycle_data.db")

ADMIN_EMAILS = {
    e.strip().lower()
    for e in (os.getenv("ADMIN_EMAILS") or "").split(",")
    if e.strip()
}


def is_admin(email):
    return bool(email) and email.strip().lower() in ADMIN_EMAILS


def study_id(user_id):
    return f"P{int(user_id):03d}"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def overview():
    """Aggregate figures - the numbers you'd actually report in a paper."""
    conn = _conn()
    try:
        def scalar(sql, args=()):
            row = conn.execute(sql, args).fetchone()
            return row[0] if row else 0

        total_users = scalar("SELECT COUNT(*) FROM users")
        total_messages = scalar("SELECT COUNT(*) FROM chat_messages")
        flagged = scalar("SELECT COUNT(*) FROM chat_messages WHERE flagged = 1")

        active = scalar(
            "SELECT COUNT(DISTINCT user_id) FROM chat_messages"
        )

        try:
            periods = scalar("SELECT COUNT(*) FROM period_logs")
            tracking_users = scalar("SELECT COUNT(DISTINCT device_id) FROM period_logs")
        except sqlite3.OperationalError:
            periods, tracking_users = 0, 0

        try:
            contacts = scalar("SELECT COUNT(*) FROM support_contacts")
            alerts = scalar("SELECT COUNT(*) FROM support_alerts")
        except sqlite3.OperationalError:
            contacts, alerts = 0, 0

        return {
            "total_users": total_users,
            "active_users": active,
            "total_messages": total_messages,
            "flagged_messages": flagged,
            "flagged_pct": round(100 * flagged / total_messages, 1) if total_messages else 0,
            "avg_messages_per_active_user": round(total_messages / active, 1) if active else 0,
            "period_logs": periods,
            "tracking_users": tracking_users,
            "support_contacts": contacts,
            "support_alerts": alerts,
        }
    finally:
        conn.close()


def participants():
    """One row per account, pseudonymised, with engagement counts."""
    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT u.id, u.email, u.created_at, u.last_login_at,
                   (SELECT COUNT(*) FROM chat_messages c WHERE c.user_id = u.id) AS messages,
                   (SELECT COUNT(*) FROM chat_messages c WHERE c.user_id = u.id AND c.flagged = 1) AS flagged,
                   (SELECT MAX(created_at) FROM chat_messages c WHERE c.user_id = u.id) AS last_message
            FROM users u ORDER BY u.id
        """).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["study_id"] = study_id(r["id"])
            out.append(d)
        return out
    finally:
        conn.close()


def transcript(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def all_messages():
    """Flat list across every participant, for CSV export."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT user_id, created_at, patient_message, bot_response, "
            "interaction_id, flagged FROM chat_messages ORDER BY user_id, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def message_length_stats():
    """Cheap behavioural signal: how much are people actually writing?"""
    conn = _conn()
    try:
        rows = conn.execute("SELECT patient_message FROM chat_messages").fetchall()
        if not rows:
            return {"count": 0, "avg_words": 0, "median_words": 0}
        lengths = sorted(len(r[0].split()) for r in rows)
        n = len(lengths)
        median = lengths[n // 2] if n % 2 else (lengths[n // 2 - 1] + lengths[n // 2]) / 2
        return {
            "count": n,
            "avg_words": round(sum(lengths) / n, 1),
            "median_words": round(median, 1),
        }
    finally:
        conn.close()


def common_first_words(limit=10):
    """What do people open with? Useful for framing the qualitative section."""
    conn = _conn()
    try:
        rows = conn.execute("SELECT patient_message FROM chat_messages").fetchall()
        counter = Counter()
        for (msg,) in rows:
            words = msg.lower().split()
            if words:
                counter[words[0]] += 1
        return counter.most_common(limit)
    finally:
        conn.close()
