"""Set isolation BEFORE collection imports bind Settings and s3 public functions."""
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
_collection_dir = TemporaryDirectory(prefix="dcx-pytest-")
_guard = pytest.MonkeyPatch()
_guard.setenv("STORAGE", "local")
_guard.setenv("LOCAL_DATA_DIR", _collection_dir.name)
_guard.setenv("AWS_EC2_METADATA_DISABLED", "true")
for _key in ("CLAUDE_API_KEY", "PINECONE_API_KEY", "VOYAGE_API_KEY",
             "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "AWS_ACCESS_KEY_ID",
             "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    _guard.setenv(_key, "offline-test-only")


def _deny_network(*args, **kwargs):
    raise RuntimeError("Network disabled in backend tests; mock the service boundary")


# Includes collection-time SDK calls, DNS, TCP and connectionless UDP.
for _name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, _name):
        _guard.setattr(socket.socket, _name, _deny_network)
_guard.setattr(socket, "create_connection", _deny_network)
_guard.setattr(socket, "getaddrinfo", _deny_network)


def pytest_unconfigure(config):
    _guard.undo()
    _collection_dir.cleanup()


@pytest.fixture(autouse=True)
def local_data_dir(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import s3

    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("STORAGE", "local")
    monkeypatch.setenv("LOCAL_DATA_DIR", str(root))
    monkeypatch.setattr(settings, "storage", "local")
    monkeypatch.setattr(settings, "local_data_dir", str(root))
    monkeypatch.setattr(s3, "_DATA_DIR", root)
    assert s3._USE_LOCAL and s3.s3 is None
    return root


@pytest.fixture
def golden_load():
    """Every call returns fresh mutable JSON; session is 'a' or 'b'."""
    def load(stage, session="a", persona_id=None):
        assert session in {"a", "b"}
        assert stage in {"classified", "clusters", "personas", "evidence", "cam"}
        if stage in {"evidence", "cam"}:
            assert persona_id in {"CL0-P1", "CL1-P1", "CL2-P1"}
            stage = f"{stage}_{persona_id}"
        path = GOLDEN / f"session_{session}" / f"{stage}.json"
        assert path.is_file(), f"Missing golden fixture: {path.relative_to(GOLDEN)}"
        return json.loads(path.read_text(encoding="utf-8"))
    return load


@pytest.fixture
def golden_classified(golden_load):
    return lambda session="a": golden_load("classified", session)


@pytest.fixture
def golden_clusters(golden_load):
    return lambda session="a": golden_load("clusters", session)


@pytest.fixture
def golden_personas(golden_load):
    return lambda session="a": golden_load("personas", session)


@pytest.fixture
def golden_evidence(golden_load):
    return lambda persona_id="CL0-P1", session="a": golden_load("evidence", session, persona_id)


@pytest.fixture
def golden_cam(golden_load):
    return lambda persona_id="CL0-P1", session="a": golden_load("cam", session, persona_id)
