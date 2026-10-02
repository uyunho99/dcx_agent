def test_health_release_from_environment(client, monkeypatch):
    monkeypatch.setenv("DCX_RELEASE_SHA", "abc123")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": "abc123"}


def test_health_release_defaults_to_dev(client, monkeypatch):
    monkeypatch.delenv("DCX_RELEASE_SHA", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": "dev"}
