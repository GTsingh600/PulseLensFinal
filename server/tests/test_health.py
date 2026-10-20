from fastapi.testclient import TestClient

from pulselens.api.main import app


def test_health_returns_200() -> None:
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["config_hash"]) == 12
