import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils import calculate

client = TestClient(app)


def test_basic_endpoints():
    assert client.get("/").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert "cpu_percent" in client.get("/cpu").json()
    assert "memory_percent" in client.get("/metrics").json()


def test_calc_ok_and_injection_rejected():
    assert client.get("/calc", params={"expr": "2 + 3 * 4"}).json() == {"result": 14}
    r = client.get("/calc", params={"expr": "__import__('os').system('id')"})
    assert r.status_code == 400


def test_calculate_limits():
    assert calculate("-(2 ** 3)") == -8
    with pytest.raises(ValueError):
        calculate("9 ** 9999")


def test_ping_rejects_injection():
    assert client.get("/ping", params={"host": "127.0.0.1; ls"}).status_code == 400


def test_fetch_allowlist():
    assert client.get("/fetch", params={"url": "http://evil.example"}).status_code == 400


def test_config_safe_load():
    assert client.post("/config", content="a: 1").json() == {"a": 1}
    bad = client.post("/config", content="!!python/object/apply:os.system ['id']")
    assert bad.status_code == 400


def test_state_json_roundtrip():
    r = client.post("/state", content='{"k": [1, 2]}')
    assert r.json() == {"state": {"k": [1, 2]}}
