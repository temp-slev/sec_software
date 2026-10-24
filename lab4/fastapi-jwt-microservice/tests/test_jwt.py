import importlib
import os
import subprocess
import sys
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import auth, database
from app.main import app

client = TestClient(app)
CREDS = {"username": "testuser", "email": "test@example.com", "password": "SecurePass123"}


@pytest.fixture(autouse=True)
def clean():
    database.fake_users_db.clear()
    database.refresh_tokens_blacklist.clear()
    auth._failed.clear()


def register(**over):
    return client.post("/register", json={**CREDS, **over})


def login(username="testuser", password="SecurePass123"):
    return client.post("/token/custom", json={"username": username, "password": password})


def bearer(tok):
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_public_endpoints():
    assert client.get("/").status_code == 200
    assert client.get("/public-info").status_code == 200


def test_register_login_protected():
    assert register().status_code == 201
    assert register().status_code == 400
    assert client.get("/protected").status_code == 401
    tok = login().json()
    r = client.get("/protected", headers=bearer(tok))
    assert r.status_code == 200 and r.json()["user_data"]["role"] == "user"
    assert login(password="wrong").status_code == 401


def test_oauth2_form_login():
    register()
    r = client.post("/token", data={"username": "testuser", "password": "SecurePass123"})
    assert r.status_code == 200 and "refresh_token" in r.json()


def test_refresh_rotation_and_logout():
    register()
    tok = login().json()
    new = client.post("/refresh", json={"refresh_token": tok["refresh_token"]})
    assert new.status_code == 200
    # старый refresh отозван при обновлении
    assert client.post("/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401
    r = client.post("/logout", json={"refresh_token": new.json()["refresh_token"]})
    assert r.status_code == 200
    again = client.post("/refresh", json={"refresh_token": new.json()["refresh_token"]})
    assert again.status_code == 401 and again.json()["detail"] == "Token revoked"


def test_token_types_are_not_interchangeable():
    register()
    tok = login().json()
    assert client.get("/protected", headers={"Authorization": f"Bearer {tok['refresh_token']}"}).status_code == 401
    assert client.post("/refresh", json={"refresh_token": tok["access_token"]}).status_code == 401


def test_roles():
    register()
    assert register(username="boss", email="b@example.com", role="admin").status_code == 403
    r = client.post("/register", json={**CREDS, "username": "boss", "email": "b@example.com",
                                       "role": "admin"}, headers={"X-Admin-Code": "admin-code"})
    assert r.status_code == 201
    user_tok, admin_tok = login().json(), login("boss").json()
    assert client.get("/protected/admin", headers=bearer(user_tok)).status_code == 403
    assert client.get("/protected/admin", headers=bearer(admin_tok)).status_code == 200


def test_revoke_all():
    register()
    t1, t2 = login().json(), login().json()
    assert client.post("/token/revoke-all", headers=bearer(t1)).status_code == 200
    assert client.get("/protected", headers=bearer(t2)).status_code == 401
    assert client.post("/refresh", json={"refresh_token": t2["refresh_token"]}).status_code == 401
    assert client.get("/protected", headers=bearer(login().json())).status_code == 200


def test_password_change_invalidates_tokens():
    register()
    tok = login().json()
    r = client.post("/password", json={"old_password": "SecurePass123", "new_password": "NewSecure456"},
                    headers=bearer(tok))
    assert r.status_code == 200
    assert client.get("/protected", headers=bearer(tok)).status_code == 401
    assert login(password="NewSecure456").status_code == 200


def test_expired_access_token():
    register()
    user = database.get_user_by_username("testuser")
    expired = auth.create_access_token(auth._claims(user), timedelta(seconds=-1))
    assert client.get("/protected", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_session_lifetime_limit(monkeypatch):
    register()
    tok = login().json()
    monkeypatch.setattr(auth, "MAX_SESSION_DAYS", -1)
    assert client.post("/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_rate_limit_on_login():
    register()
    for _ in range(5):
        assert login(password="bad").status_code == 401
    assert login().status_code == 429


def test_csrf_origin_check():
    r = client.post("/token/custom", json={"username": "a", "password": "b"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_secret_key_change_invalidates_tokens(monkeypatch):
    register()
    tok = login().json()
    monkeypatch.setattr(auth, "SECRET_KEY", "another-secret-key")
    assert client.get("/protected", headers=bearer(tok)).status_code == 401


def test_app_does_not_start_without_secret_key(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", "import app.auth"], cwd=tmp_path, env={**env, "PYTHONPATH": root},
                       capture_output=True, text=True)
    assert r.returncode != 0 and "SECRET_KEY is not set" in r.stderr
