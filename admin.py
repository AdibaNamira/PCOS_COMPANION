"""
Researcher-only routes.

Gated on ADMIN_EMAILS from the environment, checked on every request via
the admin_required decorator. A logged-in participant who guesses /admin
gets a 404, not a 403 - a 403 confirms the page exists and is worth
attacking, and there's no reason to tell them.
"""

import csv
import io
from functools import wraps

from flask import Blueprint, Response, abort, jsonify, render_template, session

import research_store
from research_store import is_admin, study_id

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id") or not is_admin(session.get("email")):
            abort(404)
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/")
@admin_required
def dashboard():
    return render_template("admin.html")


@admin_bp.route("/data")
@admin_required
def data():
    return jsonify({
        "overview": research_store.overview(),
        "participants": research_store.participants(),
        "message_lengths": research_store.message_length_stats(),
        "first_words": research_store.common_first_words(),
    })


@admin_bp.route("/transcript/<int:user_id>")
@admin_required
def transcript(user_id):
    return jsonify({
        "study_id": study_id(user_id),
        "messages": research_store.transcript(user_id),
    })


@admin_bp.route("/export.csv")
@admin_required
def export_csv():
    """
    Pseudonymised export. Emails are deliberately NOT included - a CSV is
    the artifact most likely to end up in a shared folder, an email
    attachment, or a supervisor's laptop, so it should be the least
    identifying version of the data.
    """
    rows = research_store.all_messages()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["study_id", "timestamp", "patient_message",
                     "bot_response", "interaction_id", "flagged"])
    for r in rows:
        writer.writerow([
            study_id(r["user_id"]), r["created_at"], r["patient_message"],
            r["bot_response"], r["interaction_id"], r["flagged"],
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=pcos_transcripts.csv"},
    )
