import base64
import hashlib
import hmac

import httpx
import pytest

from app.config import settings
from app.external import naver_searchad
from app.external.base import Unconnected
from app.keywords import volume
from app.keywords.models import Keyword


def keyword(text):
    return Keyword(id=text, kw=text, axis='physical', sub='test', round=1,
                   origin='llm', badges=['retained', 'low_volume'])


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    for name, value in [('searchad_api_key', 'test-key'), ('searchad_secret', 'test-secret'),
                        ('searchad_customer_id', 'test-customer')]:
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, 'low_volume_threshold', 10)


@pytest.mark.parametrize('missing', ['', 'x'])
@pytest.mark.parametrize('field', ['searchad_api_key', 'searchad_secret', 'searchad_customer_id'])
def test_unconnected_marks_source(monkeypatch, field, missing):
    monkeypatch.setattr(settings, field, missing)
    inputs = [keyword('소음'), keyword('결로')]
    before = [kw.model_dump() for kw in inputs]
    result = volume.attach_volumes(inputs)
    assert all(kw.volume == {'monthly': None, 'source': 'unconnected', 'at': None} for kw in result)
    assert all(kw.badges == ['retained'] for kw in result)
    assert [kw.model_dump() for kw in inputs] == before
    for call in (naver_searchad.monthly_volume, naver_searchad.related_queries):
        with pytest.raises(Unconnected):
            call(['소음'])


def test_batches_of_five():
    batches = []
    def handler(request):
        batch = request.url.params['hintKeywords'].split(',')
        batches.append(batch)
        assert request.url.path == '/keywordstool'
        assert request.url.params['showDetail'] == '1'
        return httpx.Response(200, json={'keywordList': [
            {'relKeyword': kw, 'monthlyPcQcCnt': 3, 'monthlyMobileQcCnt': 7} for kw in batch]})
    words = [f'keyword{i}' for i in range(12)]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert naver_searchad.monthly_volume(words, client=client) == dict.fromkeys(words, 10)
        assert not client.is_closed
    assert list(map(len, batches)) == [5, 5, 2]


def test_signature_header(monkeypatch):
    monkeypatch.setattr(naver_searchad, 'timestamp_ms', lambda: '1234567890000')
    expected = base64.b64encode(hmac.new(b'test-secret', b'1234567890000.GET./keywordstool', hashlib.sha256).digest()).decode()
    def handler(request):
        assert request.headers['X-Timestamp'] == '1234567890000'
        assert request.headers['X-API-KEY'] == 'test-key'
        assert request.headers['X-Customer'] == 'test-customer'
        assert request.headers['X-Signature'] == expected
        return httpx.Response(200, json={'keywordList': []})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        naver_searchad.monthly_volume(['소음'], client=client)


def test_related_and_original_keys_low_counts():
    def handler(request):
        return httpx.Response(200, json={'keywordList': [
            {'relKeyword': 'AB', 'monthlyPcQcCnt': '< 10', 'monthlyMobileQcCnt': 0},
            {'relKeyword': 'related', 'monthlyPcQcCnt': '20', 'monthlyMobileQcCnt': 30}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert naver_searchad.monthly_volume(['a b'], client=client) == {'a b': 5}
        assert naver_searchad.related_queries(['a b'], client=client) == [('AB', 5), ('related', 50)]


def test_connected_attachment_copies_and_refreshes(monkeypatch):
    monkeypatch.setattr(volume, 'today_iso', lambda: '2026-09-29')
    monkeypatch.setattr(naver_searchad, 'client_factory', lambda: httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'keywordList': [
            {'relKeyword': 'low', 'monthlyPcQcCnt': '< 10', 'monthlyMobileQcCnt': 0},
            {'relKeyword': 'boundary', 'monthlyPcQcCnt': 5, 'monthlyMobileQcCnt': 5}]}))))
    inputs = [keyword('low'), keyword('boundary')]
    result = volume.attach_volumes(inputs)
    assert result[0].volume == {'monthly': 5, 'source': 'searchad', 'at': '2026-09-29'}
    assert result[0].badges == ['retained', 'low_volume']
    assert result[1].badges == ['retained']
    assert all(a is not b and b.volume is None for a, b in zip(result, inputs))
    result[0].badges.append('new')
    assert inputs[0].badges == ['retained', 'low_volume']
