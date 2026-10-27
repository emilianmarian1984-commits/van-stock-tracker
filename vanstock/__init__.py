import os
import secrets
from datetime import timedelta

from flask import Flask, abort, request, session


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # In real use set VANSTOCK_SECRET_KEY as an environment variable.
        # The random fallback means sessions reset on every restart, which is
        # annoying but safer than a hard-coded key sitting on GitHub.
        SECRET_KEY=os.environ.get("VANSTOCK_SECRET_KEY", secrets.token_hex(32)),
        DATABASE=os.path.join(app.instance_path, "vanstock.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("VANSTOCK_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        MAX_LOGIN_ATTEMPTS=5,
        LOCKOUT_MINUTES=15,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db
    db.init_app(app)

    from . import auth, stock
    app.register_blueprint(auth.bp)
    app.register_blueprint(stock.bp)
    app.add_url_rule("/", endpoint="index")

    @app.before_request
    def csrf_protect():
        # Simple synchroniser-token CSRF check for every form POST.
        if request.method == "POST" and not app.config.get("TESTING_NO_CSRF"):
            token = session.get("_csrf")
            if not token or token != request.form.get("_csrf"):
                abort(400, "Missing or invalid CSRF token")

    @app.context_processor
    def inject_csrf():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return {"csrf_token": session["_csrf"]}

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'"
        )
        return resp

    return app
