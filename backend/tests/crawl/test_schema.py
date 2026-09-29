import hashlib
import json
import stat

import pytest
from pydantic import ValidationError

from app.config import settings
from app.crawl.hashing import author_hash
from app.crawl.schema import Doc


def test_author_hash_stable_and_no_raw(tmp_path, monkeypatch):
    salt_path = tmp_path / "nested" / ".author_salt"
    monkeypatch.setattr(settings, "author_salt_path", str(salt_path))
    raw_id = "private-author-identifier"
    result = author_hash("naver_cafe", raw_id)
    assert result == author_hash("naver_cafe", raw_id)
    assert raw_id not in result
    assert len(result) == 16
    salt = salt_path.read_text()
    assert len(salt) == 64
    assert result == hashlib.sha256((salt + "naver_cafe" + raw_id).encode()).hexdigest()[:16]
    assert stat.S_IMODE(salt_path.stat().st_mode) == 0o600
    assert author_hash("naver_blog", raw_id) != result
    salt_path.write_text("changed")
    assert author_hash("naver_cafe", raw_id) == result
    other_path = tmp_path / "other_salt"
    other_path.write_text("existing-salt")
    monkeypatch.setattr(settings, "author_salt_path", str(other_path))
    assert author_hash("naver_cafe", raw_id) == hashlib.sha256(
        ("existing-salt" + "naver_cafe" + raw_id).encode()
    ).hexdigest()[:16]


@pytest.fixture
def document():
    return {
        "doc_id": "yt_0123456789abcdef", "source": "youtube",
        "src_meta": {"title": "Video title", "description": "Video description"},
        "kw": "소음", "kw_axis": "physical", "kw_sub": "sense", "kw_hits": ["소음"],
        "title": "", "body": "Thread body",
        "comments": [{"text": "Reply", "depth": 1, "date": "2026-07-12", "author_hash": "a1b2"}],
        "date": "2026-07-12", "url": "https://www.youtube.com/watch?v=abc",
        "fetch_level": "full", "access": "public", "snippet": "Original snippet",
        "author_hash": "a1b2", "crawled_at": "2026-09-28T12:00:00Z",
    }


def test_doc_has_exact_design_fields_and_json_dump(document):
    doc = Doc(**document)
    assert set(Doc.model_fields) == set(document)
    assert doc.model_dump() == document
    assert json.loads(json.dumps(doc.model_dump(), ensure_ascii=False)) == document


@pytest.mark.parametrize("field,value", [
    ("source", "unknown"), ("fetch_level", "unknown"), ("access", "unknown"),
    ("raw_id", "private-author"),
])
def test_doc_rejects_invalid_fields(document, field, value):
    document[field] = value
    with pytest.raises(ValidationError):
        Doc(**document)
