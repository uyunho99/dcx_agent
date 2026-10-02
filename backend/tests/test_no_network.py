"""Regression contracts for the test suite's offline defaults."""

import socket

import pytest

from app.config import settings
from app.context import store
from app.keywords import rounds


@pytest.mark.parametrize("locked_rounds", [[], [2]], ids=["r2-commit-unlocked", "r1-commit-default"])
def test_round_two_commit_makes_zero_external_connects(client, monkeypatch, locked_rounds):
    monkeypatch.setattr(settings, "keyword_locked_rounds", locked_rounds)
    monkeypatch.setattr(settings, "llm_backend", "fake")
    monkeypatch.setattr(settings, "searchad_api_key", "")
    monkeypatch.setattr(rounds, "execute", lambda fn: fn())
    external_connects = []
    original_connect = socket.socket.connect

    # Resolve locally so even the RED run cannot send DNS or HTTPS traffic.
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("203.0.113.1", port))
    ])

    def record_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            external_connects.append(address)
            raise OSError("External connection intercepted by regression test")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", record_connect)
    store.update_session("offline", {"schemaVersion": 2, "keywords": []})
    (store.session_dir("offline") / "project_context.md").write_text("에어컨 사용 경험")

    for number in (1, 2):
        if rounds.locked(number):
            continue
        response = client.post(f"/keywords/offline/rounds/{number}")
        assert response.status_code == 200, response.text
        state = client.get(f"/keywords/offline/rounds/{number}").json()
        assert state["status"] == "done", state
        response = client.post(f"/keywords/offline/rounds/{number}/commit", json={
            "gen": state["gen"],
            "decisions": [{"id": keyword["id"], "status": "approved"}
                          for keyword in state["keywords"]],
        })
        assert response.status_code == 200, response.text

    assert external_connects == [], f"External connects attempted: {external_connects}"
    coverage = store.load_session("offline")["coverage"]
    assert coverage["source"] == "autocomplete"
    assert coverage["status"] == "connected"


@pytest.mark.parametrize("family,address", [
    (socket.AF_INET, ("223.130.200.116", 443)),
    (socket.AF_INET, ("192.168.1.1", 443)),
    (socket.AF_INET, ("ac.search.naver.com", 443)),
    (socket.AF_INET6, ("2001:db8::1", 443, 0, 0)),
])
def test_external_connect_fails_loudly(family, address):
    with socket.socket(family) as sock:
        with pytest.raises(pytest.fail.Exception, match="External network connection forbidden"):
            sock.connect(address)


@pytest.mark.parametrize("family,address", [
    (socket.AF_INET, ("127.0.0.1", 443)),
    (socket.AF_INET, ("localhost", 443)),
    (socket.AF_INET6, ("::1", 443, 0, 0)),
    (socket.AF_UNIX, "/tmp/dcx-offline-test.sock"),
])
def test_local_connect_reaches_original_socket(family, address):
    sock = socket.socket(family)
    sock.close()
    # A closed socket reaches the original method without opening a listener.
    # The guard's pytest failure is deliberately not an OSError.
    with pytest.raises(OSError):
        sock.connect(address)
