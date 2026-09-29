from app.config import Settings


def test_health_ok(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_default_storage_is_local(monkeypatch):
    monkeypatch.delenv("STORAGE", raising=False)
    assert Settings(_env_file=None).storage == "local"
