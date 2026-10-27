import os
import tempfile

import pytest

from vanstock import create_app
from vanstock.db import init_db

PASSWORD = "spanner-cloud-tulip"


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp()
    app = create_app({"TESTING": True, "DATABASE": path,
                      "TESTING_NO_CSRF": True, "SECRET_KEY": "test"})
    with app.app_context():
        init_db()
    yield app
    os.close(fd)
    os.unlink(path)


@pytest.fixture
def client(app):
    return app.test_client()


class AuthActions:
    def __init__(self, client):
        self.client = client

    def register(self, username="emilian", password=PASSWORD):
        return self.client.post("/auth/register", data={
            "username": username, "password": password, "confirm": password})

    def login(self, username="emilian", password=PASSWORD):
        return self.client.post("/auth/login",
                                data={"username": username, "password": password})

    def setup_and_login(self):
        self.register()
        self.login()
        # skip the first-login briefing
        self.client.post("/briefing", data={"ack": "yes"})


@pytest.fixture
def auth(client):
    return AuthActions(client)
