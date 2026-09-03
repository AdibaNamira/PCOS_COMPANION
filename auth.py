"""
Auth routes + the login_required decorator.

Flow:
  POST /signup        -> create account, then straight into the 2FA step
  POST /login         -> check password, issue + email a code, await step 2
  POST /verify        -> check the code, promote to a full logged-in session
  POST /resend        -> issue a fresh code
  POST /logout        -> clear the session

The session carries pending_user_id between step 1 and step 2. Until the
code is verified, only pending_user_id is set - user_id is what actually
grants access, and it's only ever written after a correct code. That's
what makes this real 2FA rather than a password check with a code-shaped
decoration on top.
"""

from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session

from auth_store import (
    create_user,
    get_user,
    issue_login_code,
    mark_logged_in,
    verify_credentials,
    verify_login_code,
)
from mailer import send_login_code

auth_bp = Blueprint("auth", __name__)


def current_user_id():
    return session.get("user_id")


def login_required(view):
    """
    Protects a route. Redirects browsers to the login page, but returns
    401 JSON to fetch() calls so the frontend can react instead of
    rendering a login page inside a chat bubble.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user_id():
            wants_json = (
                request.path.startswith(("/chat", "/cycle", "/feedback", "/history",
                                          "/support_contact", "/alert_support",
                                          "/delete_my_data", "/me"))
                or request.accept_mimetypes.best == "application/json"
            )
            if wants_json:
                return jsonify({"status": "error", "auth": "required",
                                "message": "Please log in to continue."}), 401
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapped


def _start_two_factor(user):
    """Issue a code, email it, and park the user in the pending state."""
    code = issue_login_code(user["id"])
    sent, _error = send_login_code(user["email"], code)
    session.clear()
    session["pending_user_id"] = user["id"]
    session["pending_email"] = user["email"]
    return {
        "status": "ok",
        "step": "verify",
        "emailed": sent,
        "message": (
            f"We sent a 6-digit code to {user['email']}."
            if sent else
            "SMTP isn't configured, so the code was printed in the server console."
        ),
    }


@auth_bp.route("/login", methods=["GET"])
def login_page():
    if current_user_id():
        return redirect("/")
    return render_template("login.html")


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    user_id, error = create_user(data.get("email"), data.get("password"))
    if error:
        return jsonify({"status": "error", "message": error}), 400
    return jsonify(_start_two_factor(get_user(user_id)))


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    user = verify_credentials(data.get("email"), data.get("password"))
    if not user:
        # Same message either way - don't reveal which emails exist.
        return jsonify({"status": "error", "message": "Email or password is incorrect."}), 401
    return jsonify(_start_two_factor(user))


@auth_bp.route("/verify", methods=["POST"])
def verify():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        return jsonify({"status": "error", "message": "Your session expired. Please log in again."}), 400

    data = request.get_json(silent=True) or {}
    ok, reason = verify_login_code(pending_id, data.get("code"))
    if not ok:
        return jsonify({"status": "error", "message": reason}), 401

    user = get_user(pending_id)
    session.clear()
    session["user_id"] = pending_id
    session["email"] = user["email"]
    session.permanent = True
    mark_logged_in(pending_id)
    return jsonify({"status": "ok", "step": "done", "email": user["email"]})


@auth_bp.route("/resend", methods=["POST"])
def resend():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        return jsonify({"status": "error", "message": "Your session expired. Please log in again."}), 400
    return jsonify(_start_two_factor(get_user(pending_id)))


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    if request.method == "GET":
        return redirect("/login")
    return jsonify({"status": "ok"})


@auth_bp.route("/me")
def me():
    user_id = current_user_id()
    if not user_id:
        return jsonify({"authenticated": False})
    from research_store import is_admin
    return jsonify({"authenticated": True, "email": session.get("email"),
                    "is_admin": is_admin(session.get("email"))})


