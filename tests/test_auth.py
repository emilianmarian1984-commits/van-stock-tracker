from vanstock import create_app
from vanstock.auth import password_problems
from vanstock.db import get_db


def test_password_rules():
    assert password_problems("emilian", "short")
    assert password_problems("emilian", "password123")
    assert password_problems("emilian", "emilian-is-great")
    assert password_problems("emilian", "spanner-cloud-tulip") == []


def test_register_stores_hash_not_plain_text(app, auth):
    auth.register()
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM users").fetchone()
    assert "spanner" not in row["password_hash"]
    assert row["password_hash"].startswith(("scrypt:", "pbkdf2:"))


def test_registration_closes_after_owner_created(client, auth):
    auth.register()
    r = auth.register(username="intruder")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_login_and_first_login_briefing(client, auth):
    auth.register()
    r = auth.login()
    assert r.headers["Location"].endswith("/briefing")
    client.post("/briefing", data={"ack": "yes"})
    r = auth.login()
    assert r.headers["Location"].endswith("/")


def test_wrong_password_same_message_as_unknown_user(client, auth):
    auth.register()
    r1 = auth.login(password="wrong-password-here")
    r2 = auth.login(username="nobody", password="wrong-password-here")
    assert r1.status_code == r2.status_code == 401
    assert b"Incorrect username or password" in r1.data
    assert b"Incorrect username or password" in r2.data


def test_lockout_after_five_failures(client, auth):
    auth.register()
    for _ in range(5):
        auth.login(password="wrong-password-here")
    # correct password is now refused because the account is locked
    r = auth.login()
    assert r.status_code == 429


def test_pages_need_login(client):
    for url in ("/", "/parts", "/history", "/export.csv", "/security"):
        r = client.get(url)
        assert r.status_code == 302
        assert "/auth/login" in r.headers["Location"]


def test_csrf_blocks_post_without_token(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db"),
                      "SECRET_KEY": "test"})
    with app.app_context():
        from vanstock.db import init_db
        init_db()
    r = app.test_client().post("/auth/login", data={"username": "a", "password": "b"})
    assert r.status_code == 400


def test_security_headers(client):
    r = client.get("/auth/login")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
