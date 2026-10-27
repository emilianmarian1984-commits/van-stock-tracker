import functools
from datetime import datetime, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")

# Short list on purpose - the point is to stop the obvious ones that a
# mechanic might actually pick, not to be a full breached-password check.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789", "12345678",
    "qwerty123", "letmein", "welcome1", "iloveyou", "van12345",
    "mechanic1", "garage123", "admin123", "changeme",
}


def password_problems(username, password):
    """Return a list of reasons the password is rejected (empty = ok)."""
    problems = []
    if len(password) < 12:
        problems.append("Use at least 12 characters - three random words works well.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("That password is on the common-passwords list.")
    if username and username.lower() in password.lower():
        problems.append("Don't put your username inside your password.")
    return problems


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def _user_count():
    return get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


@bp.route("/register", methods=("GET", "POST"))
def register():
    # Single-user app: registration is only open until the owner account
    # exists. After that the page is closed, so nobody else can sign up.
    if _user_count() > 0:
        flash("The owner account already exists. Log in instead.")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        errors = []
        if not username:
            errors.append("Username is required.")
        if password != confirm:
            errors.append("Passwords don't match.")
        errors += password_problems(username, password)

        if not errors:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except db.IntegrityError:
                errors.append(f"User {username} already exists.")
            else:
                flash("Account created. Log in to continue.")
                return redirect(url_for("auth.login"))
        for e in errors:
            flash(e)
    return render_template("auth/register.html", first=_user_count() == 0)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        now = datetime.now()

        if user and user["locked_until"]:
            if datetime.fromisoformat(user["locked_until"]) > now:
                flash("Too many failed attempts. Try again in a few minutes.")
                return render_template("auth/login.html"), 429

        if user is None or not check_password_hash(user["password_hash"], password):
            if user is not None:
                attempts = user["failed_attempts"] + 1
                locked = None
                if attempts >= current_app.config["MAX_LOGIN_ATTEMPTS"]:
                    locked = (now + timedelta(
                        minutes=current_app.config["LOCKOUT_MINUTES"])).isoformat()
                    attempts = 0
                db.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                    (attempts, locked, user["id"]),
                )
                db.commit()
            # Same message whether the username exists or not.
            flash("Incorrect username or password.")
            return render_template("auth/login.html"), 401

        db.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (user["id"],),
        )
        db.commit()
        csrf = session.get("_csrf")
        session.clear()  # new session on login, stops session fixation
        session.permanent = True
        session["user_id"] = user["id"]
        if csrf:
            session["_csrf"] = csrf
        if not user["briefing_done"]:
            return redirect(url_for("stock.briefing"))
        return redirect(url_for("stock.index"))

    return render_template("auth/login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("auth.login"))
