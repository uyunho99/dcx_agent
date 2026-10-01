import ipaddress
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep the application singleton independent of a developer's real .env.
with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}):
    from app.config import settings


@pytest.fixture(autouse=True)
def fake_autocomplete(monkeypatch):
    monkeypatch.setattr(settings, "autocomplete_backend", "fake")


@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch):
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            loopback = host == "localhost"
            if not loopback:
                try:
                    loopback = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    loopback = False
            if not loopback:
                # Unlike OSError/AssertionError, this escapes application catch-all
                # handlers that could otherwise turn network use into a pass.
                pytest.fail(f"External network connection forbidden: {address!r}")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "storage", "local")

    from app.services import s3

    monkeypatch.setattr(s3, "_USE_LOCAL", True)
    monkeypatch.setattr(s3, "_DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir):
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
