import pytest
from app.llm.compose import CONTEXT_HEADER, compose, extract_json

def test_compose_attaches_context_verbatim(task):
    system, user = compose(task)
    assert system.startswith(CONTEXT_HEADER)
    assert task.attachments[0].body.encode() in system.encode()
    assert user == task.instructions

def test_extract_json_tolerates_fence_and_prose():
    assert extract_json('설명\n```json\n[{"kw":"소음",}]\n```') == [{"kw": "소음"}]
    assert extract_json('before {"text":"a,} and \\\"quote\\\"",} after') == {"text": 'a,} and "quote"'}
    with pytest.raises(ValueError, match="JSON"):
        extract_json("no JSON here")
