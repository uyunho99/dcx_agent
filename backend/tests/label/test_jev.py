import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.label import jev
from app.crawl.ratelimit import ChannelLimiter
from app.label.jev import JevClient, JevError, build_state
from app.label.questions import QVER, jev_questions, load_questions
from app.label.schema import Label, Tags
from app.label.rule import GRADE_FIELDS
from tests.fakes.fake_jev import FakeJev

FIXTURE = Path(__file__).parents[1] / 'fixtures/jev/success.json'
DOC = {'doc_id': 'nc_1', 'title': '제목', 'body': '본문', 'comments': ['댓글']}
REAL_WAIT_START = ChannelLimiter.wait_start
NAMES = {'anchor', 'sense', 'feel', 'think', 'act', 'situation', 'relate_outcome', 'reason_code'}


@pytest.fixture
def answer():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    jev.reset_limiter_pool()
    monkeypatch.setattr('app.label.jev.time.sleep', lambda _: None)
    monkeypatch.setattr('app.label.jev.ChannelLimiter.wait_start', lambda _: None)
    yield
    jev.reset_limiter_pool()


def client_for(answer):
    return JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(lambda _: httpx.Response(200, json=answer)))


def test_request_shape(answer):
    def handle(request):
        assert request.method == 'POST'
        assert str(request.url) == 'https://jevmodel.org/v1/systemone'
        assert request.headers['Authorization'] == 'Bearer secret'
        assert request.headers['Idempotency-Key'] == 'nc_1:q1'
        body = json.loads(request.content)
        assert body['model'] == 'jev-latest'
        assert set(body['questions']) == NAMES
        assert body['state'].splitlines()[0] == '[맥락] 대상 경험'
        assert len(json.dumps(body['state'], ensure_ascii=False)) <= 8000
        assert body['questions']['relate_outcome']['type'] == 'choice'
        assert isinstance(body['questions']['relate_outcome']['criteria'], dict)
        return httpx.Response(200, json=answer)
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(handle)) as client:
        vote = client.judge(DOC, '대상 경험')
    assert vote.model == 'jev-1.13.0'
    assert set(vote.probs) == set(GRADE_FIELDS)
    assert vote.truncated is False


def test_relate_outcome_recovered(answer):
    with client_for(answer) as client:
        vote = client.judge(DOC, '맥락')
    assert vote.probs['relate'] == pytest.approx(.3)
    assert vote.probs['outcome'] == pytest.approx(.7)


def test_jev_normalizes_choice_probs(answer):
    for name in ('relate_outcome', 'reason_code'):
        answer['answers'][name]['probabilities'] = {k: v * .97 for k, v in answer['answers'][name]['probabilities'].items()}
    with client_for(answer) as client:
        vote = client.judge(DOC, '맥락')
    assert vote.probs['outcome'] == pytest.approx(.7)
    assert sum(vote.reason_probs.values()) == pytest.approx(1)
    assert vote.reason_probs['not_non'] == pytest.approx(.95)


@pytest.mark.parametrize('name', sorted(NAMES))
def test_jev_missing_answer_is_bad(answer, name):
    del answer['answers'][name]
    with client_for(answer) as client, pytest.raises(JevError) as error:
        client.judge(DOC, '맥락')
    assert error.value.code == 'bad'


@pytest.mark.parametrize('invalid', [-.1, 1.1, '0.5', None, True, float('nan')])
def test_invalid_noul_is_bad(answer, invalid):
    answer['answers']['anchor']['noul'] = invalid
    # Nonstandard NaN simulates an upstream malformed JSON numeric value.
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps(answer)))) as client:
        with pytest.raises(JevError) as error:
            client.judge(DOC, '맥락')
    assert error.value.code == 'bad'


@pytest.mark.parametrize('invalid', [{}, {'none': 1}, {'none': 0, 'relate': 0, 'outcome': 0, 'both': 0}, {'none': -.1, 'relate': .2, 'outcome': .8, 'both': .1}])
def test_invalid_choice_is_bad(answer, invalid):
    answer['answers']['relate_outcome']['probabilities'] = invalid
    with client_for(answer) as client, pytest.raises(JevError) as error:
        client.judge(DOC, '맥락')
    assert error.value.code == 'bad'


def test_state_truncation():
    state, truncated = build_state({**DOC, 'body': '가' * 12000, 'comments': ['나' * 300]}, '대상 경험')
    assert len(json.dumps(state, ensure_ascii=False)) <= 8000
    assert truncated
    assert state.startswith('[맥락] 대상 경험\n[제목] 제목\n[본문] 가')
    assert state.endswith('\n[댓글] ')


def test_comments_truncated_before_body():
    state, truncated = build_state({**DOC, 'body': '본문 유지', 'comments': ['나' * 12000]}, '맥락')
    assert truncated and '[본문] 본문 유지\n' in state
    assert '나' in state


def test_state_serialized_escaping_and_desc():
    state, truncated = build_state({'doc_id': 'x', 'desc': '\\"\n' * 5000}, '맥락')
    assert truncated
    assert len(json.dumps(state, ensure_ascii=False)) <= 8000
    assert '[본문] \\"\n' in state


def test_oversized_context_is_bad():
    with pytest.raises(JevError) as error:
        build_state(DOC, '가' * 8000)
    assert error.value.code == 'bad'


@pytest.mark.parametrize('status,code', [(401, 'unconnected'), (402, 'insufficient'), (422, 'bad')])
def test_error_mapping(status, code):
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(lambda _: httpx.Response(status, json={'error': {'type': 'error', 'message': 'secret'}}))) as client:
        with pytest.raises(JevError) as error:
            client.judge(DOC, '맥락')
    assert error.value.code == code
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('status', [429, 502])
def test_error_mapping_retry_success(answer, status, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr('app.label.jev.time.sleep', sleeps.append)
    def handle(request):
        calls.append((request.headers['Authorization'], request.headers['Idempotency-Key']))
        return httpx.Response(status if len(calls) <= 5 else 200, json=answer)
    with JevClient(['first', 'second'], 'jev-latest', transport=httpx.MockTransport(handle)) as client:
        assert client.judge(DOC, '맥락').model == answer['model']
    assert len(calls) == 6 and len(set(calls)) == 1
    assert sleeps == [1, 2, 4, 8, 16]


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_retry_exhaustion(status):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status)
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(handle)) as client, pytest.raises(JevError) as error:
        client.judge(DOC, '맥락')
    assert error.value.code == 'bad' and len(calls) == 6
    assert error.value.transient is True


def test_key_rotation_and_per_key_limit(answer, monkeypatch):
    limits, keys = [], []
    class Limiter:
        def __init__(self, concurrency, min_interval_s):
            self.starts = 0
            limits.append(self)
            assert min_interval_s == .5
        def __enter__(self):
            self.starts += 1
        def __exit__(self, *args):
            pass
    monkeypatch.setattr('app.label.jev.ChannelLimiter', Limiter)
    def handle(request):
        keys.append(request.headers['Authorization'])
        return httpx.Response(200, json=answer)
    with JevClient(['a', 'a', 'b'], 'jev-latest', transport=httpx.MockTransport(handle)) as client:
        for _ in range(3):
            client.judge(DOC, '맥락')
    assert keys == ['Bearer a', 'Bearer b', 'Bearer a']
    assert [limit.starts for limit in limits] == [2, 1]


def test_no_keys():
    with JevClient([], 'jev-latest') as client, pytest.raises(JevError) as error:
        client.judge(DOC, '맥락')
    assert error.value.code == 'unconnected'


@pytest.mark.parametrize('doc_id', ['', 'x' * 98, '한글', 'x\ny'])
def test_invalid_idempotency_key(doc_id):
    with client_for({}) as client, pytest.raises(JevError) as error:
        client.judge({**DOC, 'doc_id': doc_id}, '맥락')
    assert error.value.code == 'bad'


def test_questions():
    definitions = load_questions()
    assert QVER == 'q1'
    assert set(GRADE_FIELDS) | {'reason_code', 'signal'} <= set(definitions)
    assert '감정어 단독은 0' in definitions['feel']['instructions']
    assert '대상과 무관한 행동은 0' in definitions['act']['instructions']
    assert not any(word in json.dumps(definitions, ensure_ascii=False) for word in ['에어컨', '보험', '청소기', '분유'])
    for question in jev_questions('대상 경험').values():
        assert 0 < len(question['instructions']) <= 1800
        if question['type'] == 'choice':
            assert 2 <= len(question['criteria']) <= 20
            assert len(json.dumps(question['criteria'], ensure_ascii=False)) <= 2000
    definitions['anchor']['instructions'] = 'changed'
    assert load_questions()['anchor']['instructions'] != 'changed'


def test_schema_roundtrip():
    tags = Tags(anchor=True, sem=dict.fromkeys(('sense', 'feel', 'think', 'act', 'relate', 'outcome'), 0), situation=False)
    label = Label(doc_id='nc_1', **tags.model_dump(), evidence_level='non', confidence=.8, source='agreed', votes={}, route='accepted')
    assert label.rule_version == 'r1' and label.questions_version == 'q1'
    assert Label.model_validate_json(label.model_dump_json()) == label
    with pytest.raises(ValidationError):
        Tags(anchor=True, sem={'sense': 2}, situation=False)
    with pytest.raises(ValidationError):
        Label(**{**label.model_dump(), 'confidence': 1.2})


def test_fake_deterministic_and_fixed(answer):
    fake = FakeJev()
    with JevClient(['fake'], 'jev-latest', transport=httpx.MockTransport(fake)) as client:
        first = client.judge(DOC, '맥락')
        assert first == client.judge(DOC, '맥락')
        assert first != client.judge({**DOC, 'body': '다른 본문'}, '맥락')
    with JevClient(['fake'], 'jev-latest', transport=httpx.MockTransport(FakeJev(answer))) as client:
        assert client.judge(DOC, '맥락').probs['anchor'] == .96


@pytest.mark.parametrize('payload', [None, [], {}, {'model': 'jev', 'answers': []}, {'model': '', 'answers': {}}])
def test_malformed_payload_is_bad(payload):
    with client_for(payload) as client, pytest.raises(JevError) as error:
        client.judge(DOC, '맥락')
    assert error.value.code == 'bad'


def test_invalid_json_is_bad():
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'not json'))) as client:
        with pytest.raises(JevError) as error:
            client.judge(DOC, '맥락')
    assert error.value.code == 'bad'


def test_transport_failure_is_safe():
    def fail(request):
        raise httpx.ReadTimeout('secret', request=request)
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(JevError) as error:
            client.judge(DOC, '맥락')
    assert error.value.code == 'bad' and 'secret' not in str(error.value)
    assert error.value.transient is True


def test_state_without_truncation():
    assert build_state(DOC, '맥락') == ('[맥락] 맥락\n[제목] 제목\n[본문] 본문\n[댓글] 댓글', False)


def test_configured_rate(answer, monkeypatch):
    intervals = []
    class Limiter:
        def __init__(self, concurrency, min_interval_s):
            intervals.append(min_interval_s)
        def __enter__(self):
            pass
        def __exit__(self, *args):
            pass
    monkeypatch.setattr('app.label.jev.ChannelLimiter', Limiter)
    monkeypatch.setattr('app.label.jev.settings.jev_rate_per_min', 60)
    with client_for(answer) as client:
        client.judge(DOC, '맥락')
    assert intervals == [1.0]


@pytest.mark.parametrize('status', [429, 502])
@pytest.mark.parametrize('key', ['nc_1:q1-context123', 'x' * 100])
def test_caller_idempotency_key_on_every_retry(answer, status, key):
    sent = []
    def handle(request):
        sent.append(request.headers['Idempotency-Key'])
        return httpx.Response(status if len(sent) <= 5 else 200, json=answer)
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(handle)) as client:
        client.judge(DOC, '맥락', idempotency_key=key)
    assert sent == [key] * 6


@pytest.mark.parametrize('key', ['x' * 101, '한글', 'x\ny', 'x y', 'x\x7fy', '', 123])
def test_invalid_caller_idempotency_key_is_bad(key):
    sent = []
    with JevClient(['secret'], 'jev-latest', transport=httpx.MockTransport(sent.append)) as client:
        with pytest.raises(JevError) as error:
            client.judge(DOC, '맥락', idempotency_key=key)
    assert error.value.code == 'bad'
    assert sent == []


@pytest.mark.parametrize('rate', [60, 120])
def test_clients_share_per_key_rate_with_fake_clock(answer, monkeypatch, rate):
    now = [1000.0]
    starts = []
    def sleep(delay):
        now[0] += delay
    def limiter(concurrency, min_interval_s):
        return ChannelLimiter(concurrency, min_interval_s, clock=lambda: now[0], sleep=sleep)
    monkeypatch.setattr(ChannelLimiter, 'wait_start', REAL_WAIT_START)
    monkeypatch.setattr(jev, 'ChannelLimiter', limiter)
    monkeypatch.setattr(jev.settings, 'jev_rate_per_min', rate)
    def handle(request):
        starts.append(now[0])
        return httpx.Response(200, json=answer)
    with JevClient(['shared-secret'], 'jev-latest', transport=httpx.MockTransport(handle)) as first:
        with JevClient(['shared-secret'], 'jev-latest', transport=httpx.MockTransport(handle)) as second:
            for i in range(rate + 2):
                (first if i % 2 == 0 else second).judge(DOC, '맥락')
    assert all(b - a >= 60 / rate for a, b in zip(starts, starts[1:]))
    assert all(sum(start <= other < start + 60 for other in starts) <= rate for start in starts)
    assert set(jev._limiter_pool) == {hashlib.sha256(b'shared-secret').hexdigest()}
