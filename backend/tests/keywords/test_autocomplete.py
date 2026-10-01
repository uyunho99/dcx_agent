import json
import socket
from pathlib import Path

import httpx
import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Network access is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setenv('AUTOCOMPLETE_BACKEND', 'fake')


@pytest.fixture
def adapter(monkeypatch):
    from app.external import naver_autocomplete
    monkeypatch.setattr(settings, 'autocomplete_backend', 'http')
    return naver_autocomplete


@pytest.fixture
def payload():
    path = Path(__file__).resolve().parents[1] / 'fixtures/autocomplete/suggestions.json'
    return json.loads(path.read_text())


def test_parses_suggestions_in_rank_order(adapter, payload):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        result = adapter.suggestions(['에어컨 소음'], client=client)
        assert result.queries == [('에어컨 소음', 1), ('시스템에어컨 소음', 2), ('에어컨 소음 원인', 3)]
        assert (result.failed, result.total) == (0, 1)
        assert not client.is_closed


@pytest.mark.parametrize('reverse', [False, True])
def test_dedupes_keeping_best_rank(adapter, reverse):
    responses = {
        'first': {'items': [[['one'], ['Ａ B'], ['three'], ['four'], ['에어컨 소음']]]},
        'second': {'items': [[['ONE'], ['에어컨소음'], ['Ａb']]]},
    }
    seeds = list(responses)
    if reverse:
        seeds.reverse()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=responses[request.url.params['q']])
    )) as client:
        result = adapter.suggestions(seeds, client=client, sleep=lambda _: None)
    from app.keywords.normalize import norm_key
    normalized = [(norm_key(query), rank) for query, rank in result.queries]
    assert len(normalized) == 5
    assert dict(normalized) == {'one': 1, 'ａb': 2, 'three': 3, 'four': 4, '에어컨소음': 2}


def test_partial_failure_returns_received_and_counts_failed(adapter, payload):
    calls = []
    def handler(request):
        calls.append(request.url.params['q'])
        if calls[-1] == 'bad':
            raise httpx.ConnectError('offline', request=request)
        return httpx.Response(200, json=payload)
    pauses = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = adapter.suggestions(['first', 'bad', 'last'], client=client, sleep=pauses.append)
    assert (result.failed, result.total) == (1, 3)
    assert result.queries == [('에어컨 소음', 1), ('시스템에어컨 소음', 2), ('에어컨 소음 원인', 3)]
    assert calls == ['first', 'bad', 'last']
    assert pauses == [1, 1]


@pytest.mark.parametrize('body', [None, {}, {'items': []},
    {'items': 'bad'}, {'items': [[[]]]}, {'items': [[['ok'], [3]]]},
    {'items': [[['   ']]]}, {'items': [['text']]}])
def test_all_failed_raises_unavailable(adapter, body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        with pytest.raises(adapter.AutocompleteUnavailable):
            adapter.suggestions(['seed'], client=client)


@pytest.mark.parametrize('response', [httpx.Response(503), httpx.Response(200, content=b'not json')])
def test_http_and_json_errors_raise_unavailable(adapter, response):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(adapter.AutocompleteUnavailable):
            adapter.suggestions(['seed'], client=client)


def test_empty_seeds_raise_unavailable(adapter):
    with pytest.raises(adapter.AutocompleteUnavailable):
        adapter.suggestions([])


def test_http_backend_builds_expected_request(adapter, payload):
    events = []
    def handler(request):
        events.append(request.url.params['q'])
        assert str(request.url).split('?')[0] == 'https://ac.search.naver.com/nx/ac'
        assert dict(request.url.params) == dict(q=events[-1], con='1', frm='nv', ans='2',
            r_format='json', r_enc='UTF-8', r_unicode='0', t_koreng='1', run='2',
            rev='4', q_enc='UTF-8', st='100')
        assert request.headers['User-Agent']
        assert not request.headers['User-Agent'].startswith('python-httpx')
        assert set(request.extensions['timeout'].values()) == {10}
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter.suggestions(['에어컨', '소음', '냉방'], client=client,
                            sleep=lambda seconds: events.append(('sleep', seconds)))
    assert events == ['에어컨', ('sleep', 1), '소음', ('sleep', 1), '냉방']


def test_fake_backend_makes_no_http(adapter, monkeypatch):
    monkeypatch.setattr(settings, 'autocomplete_backend', 'fake')
    def forbidden(*args, **kwargs):
        pytest.fail('fake backend must not construct or use an HTTP client')
    monkeypatch.setattr(httpx, 'Client', forbidden)
    class NoHTTP:
        get = forbidden
    for client in (None, NoHTTP()):
        result = adapter.suggestions(['anything', '../anything'], client=client, sleep=forbidden)
        assert result.queries == [('에어컨 소음', 1), ('시스템에어컨 소음', 2), ('에어컨 소음 원인', 3)]
        assert (result.failed, result.total) == (0, 2)


def test_limits_ranks_to_ten(adapter):
    body = {'items': [[[str(i)] for i in range(15)]]}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        result = adapter.suggestions(['seed'], client=client)
    assert result.queries == [(str(i), i + 1) for i in range(10)]


def test_review_progress_after_success_and_failure(adapter, payload):
    progress = []
    def handler(request):
        return httpx.Response(200, json=payload if request.url.params['q'] == 'good' else {})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = adapter.suggestions(['bad', 'good', 'bad'], client=client,
            sleep=lambda _: None, on_progress=lambda: progress.append(True))
    assert len(progress) == 3
    assert result.failed == 2


def test_review_progress_can_stop_superseded_fetch(adapter, payload, monkeypatch):
    requested = []
    def handler(request):
        requested.append(request.url.params['q'])
        return httpx.Response(200, json=payload)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(adapter, 'client_factory', lambda: client)
    def superseded():
        raise RuntimeError('superseded')
    with pytest.raises(RuntimeError, match='superseded'):
        adapter.suggestions(['first', 'never'], sleep=lambda _: None, on_progress=superseded)
    assert requested == ['first']
    assert client.is_closed


@pytest.mark.parametrize('bodies,failed', [
    ([{'items': [[]]}, {'items': [[]]}], 0),
    ([{}, {'items': [[]]}], 1),
    ([{'items': [[]]}, {'items': [[['소음']]]}, {}], 1),
])
def test_empty_results_are_successful_seeds(adapter, bodies, failed):
    responses = iter(bodies)
    progress = []
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=next(responses))
    )) as client:
        result = adapter.suggestions(['seed'] * len(bodies), client=client,
            sleep=lambda _: None, on_progress=lambda: progress.append(True))
    assert (result.failed, result.total) == (failed, len(bodies))
    assert result.queries == ([('소음', 1)] if len(bodies) == 3 else [])
    assert len(progress) == len(bodies)
