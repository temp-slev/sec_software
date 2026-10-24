import httpx
import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
RealAsyncClient = httpx.AsyncClient


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    main.users_db.clear()
    main.accounts_db.clear()
    main.next_user_id = 1
    # Notification Service недоступен: создание пользователя не должно падать
    monkeypatch.setattr(main, "NOTIFY_URL", "http://127.0.0.1:9/notify/")


def token():
    client.post("/signup", json={"username": "u", "password": "p"})
    return client.post("/login", json={"username": "u", "password": "p"}).json()[
        "access_token"
    ]


def auth():
    return {"Authorization": f"Bearer {token()}"}


def new_user(name="John", email="john@example.com", age=25):
    return client.post("/users/", json={"name": name, "email": email, "age": age})


def test_create_and_get():
    r = new_user()
    assert r.status_code == 201
    assert client.get("/users/1").json()["email"] == "john@example.com"
    assert len(client.get("/users/").json()) == 1


def test_duplicate_email():
    new_user()
    assert new_user().status_code == 400


def test_min_age_filter():
    new_user("A", "a@x.com", 20)
    new_user("B", "b@x.com", 40)
    r = client.get("/users/", params={"min_age": 30}).json()
    assert [u["name"] for u in r] == ["B"]


def test_update_delete_require_token():
    new_user()
    assert client.put("/users/1", json={"name": "x", "email": "x@x.com"}).status_code == 401
    assert client.delete("/users/1").status_code == 401
    h = auth()
    r = client.put("/users/1", json={"name": "New", "email": "n@x.com", "age": 30}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "New"
    assert client.delete("/users/1", headers=h).status_code == 200
    assert client.delete("/users/1", headers=h).status_code == 404


def test_bad_token_and_bad_login():
    assert client.put(
        "/users/1", json={"name": "x", "email": "x@x.com"},
        headers={"Authorization": "Bearer garbage"},
    ).status_code == 401
    assert client.post("/login", json={"username": "no", "password": "no"}).status_code == 401


def test_notification_sent(monkeypatch):
    sent = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, timeout):
            sent.append(json)
            return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    new_user()
    assert sent == [{"user_id": 1, "email": "john@example.com", "message": "Welcome, John!"}]


def test_posts_errors(monkeypatch):
    def mock_client(handler):
        monkeypatch.setattr(
            main.httpx, "AsyncClient",
            lambda: RealAsyncClient(transport=httpx.MockTransport(handler)),
        )

    mock_client(lambda req: httpx.Response(200, json=[{"id": 1, "userId": 1}]))
    assert client.get("/users/1/posts").json() == [{"id": 1, "userId": 1}]
    mock_client(lambda req: httpx.Response(500))
    assert client.get("/users/1/posts").status_code == 502

    def boom(req):
        raise httpx.ConnectError("down", request=req)

    mock_client(boom)
    assert client.get("/users/1/posts").status_code == 503
