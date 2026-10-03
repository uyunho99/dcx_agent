"""Synchronous Jev HTTP client with process-wide per-key rate limiting."""
import hashlib
import json
import math
import threading
import time

import httpx

from app.config import settings
from app.crawl.ratelimit import ChannelLimiter
from app.label.questions import QVER, jev_questions
from app.label.schema import JevVote

URL = 'https://jevmodel.org/v1/systemone'
MAX_RETRIES = 5
GPT_ONLY_MESSAGE = 'Jev가 연결되지 않아 GPT 단독으로 판정합니다.'


def jev_available() -> bool:
    if settings.jev_backend == 'http':
        return bool(settings.jev_api_keys)
    if settings.jev_backend == 'fake':
        return settings.label_fake_jev_cross
    return False


def labeler_mode(data: dict) -> str:
    labeling = data.get('labeling', {})
    if 'labelerMode' in labeling:
        return labeling['labelerMode']
    # Preserve the rules of sessions started before modes were persisted.
    if labeling.get('started'):
        return 'cross'
    return 'cross' if jev_available() else 'gpt_only'


_limiter_pool: dict[str, ChannelLimiter] = {}
_limiter_pool_lock = threading.Lock()


def reset_limiter_pool():
    """Clear process-wide rate state for tests; call only with no active clients."""
    with _limiter_pool_lock:
        _limiter_pool.clear()


def _limiter_for(key: str, rate: float) -> ChannelLimiter:
    fingerprint = hashlib.sha256(key.encode('utf-8')).hexdigest()
    with _limiter_pool_lock:
        if fingerprint not in _limiter_pool:
            _limiter_pool[fingerprint] = ChannelLimiter(concurrency=1, min_interval_s=60 / rate, jitter=0)
        return _limiter_pool[fingerprint]


class JevError(RuntimeError):
    """Safe worker-facing failure; provider bodies and credentials are never copied."""
    def __init__(self, code: str, message: str, *, transient: bool = False):
        self.code = code
        self.transient = transient
        super().__init__(message)


def _bad():
    return JevError('bad', 'Jev 요청 또는 응답을 확인해 주세요')


def _text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_state(doc: dict, one_liner: str) -> tuple[str, bool]:
    """Budget JSON-serialized state, removing comments then the end of the body.

    Context/title are preserved; an oversized immutable prefix is a bad document.
    JSON is measured with ensure_ascii=False, as used by httpx on the wire.
    """
    if not isinstance(one_liner, str) or '\n' in one_liner or '\r' in one_liner:
        raise _bad()
    prefix = f'[맥락] {one_liner}\n[제목] {_text(doc.get("title"))}\n[본문] '
    body = _text(doc.get('body', doc.get('desc', '')))
    comments = doc.get('comments', '')
    if isinstance(comments, list):
        comments = '\n'.join(_text(item) for item in comments)
    else:
        comments = _text(comments)

    def render():
        return f'{prefix}{body}\n[댓글] {comments}'

    def fits():
        return len(json.dumps(render(), ensure_ascii=False)) <= 8000

    if fits():
        return render(), False
    # Binary search by characters also accounts for escaped quotes/control chars.
    for field in ('comments', 'body'):
        original = comments if field == 'comments' else body
        low, high = 0, len(original)
        while low < high:
            mid = (low + high + 1) // 2
            if field == 'comments':
                comments = original[:mid]
            else:
                body = original[:mid]
            if fits():
                low = mid
            else:
                high = mid - 1
        if field == 'comments':
            comments = original[:low]
        else:
            body = original[:low]
        if fits():
            return render(), True
    raise _bad()


def _probability(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise _bad()
    return float(value)


def _parse_vote(payload, questions, truncated):
    try:
        answers = payload['answers']
        model = payload['model']
        if not isinstance(model, str) or not model:
            raise _bad()
        probs, choices = {}, {}
        for name, question in questions.items():
            answer = answers[name]
            if answer['type'] != question['type']:
                raise _bad()
            if question['type'] == 'noul':
                probs[name] = _probability(answer['noul'])
            else:
                values = answer['probabilities']
                if not isinstance(values, dict) or set(values) != set(question['criteria']):
                    raise _bad()
                values = {key: _probability(value) for key, value in values.items()}
                total = sum(values.values())
                if total <= 0:
                    raise _bad()
                choices[name] = {key: value / total for key, value in values.items()}
        combined = choices['relate_outcome']
        probs['relate'] = combined['relate'] + combined['both']
        probs['outcome'] = combined['outcome'] + combined['both']
        return JevVote(probs=probs, reason_probs=choices['reason_code'], model=model, truncated=truncated)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _bad() from None


class JevClient:
    def __init__(self, keys, model, transport=None):
        self._keys = tuple(dict.fromkeys(key.strip() for key in keys if key.strip()))
        self.model = model
        rate = settings.jev_rate_per_min
        if not 0 < rate <= 120:
            raise ValueError('jev_rate_per_min must be between 1 and 120')
        self._limiters = [_limiter_for(key, rate) for key in self._keys]
        self._lock = threading.Lock()
        self._next_key = 0
        self._http = httpx.Client(transport=transport, timeout=60)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def judge(self, doc: dict, one_liner: str, *, idempotency_key: str | None = None) -> JevVote:
        if not self._keys:
            raise JevError('unconnected', 'Jev 연결 키가 없습니다')
        doc_id = doc.get('doc_id')
        if not isinstance(doc_id, str) or not doc_id:
            raise _bad()
        if idempotency_key is None:
            idempotency_key = f'{doc_id}:{QVER}'
        if (not isinstance(idempotency_key, str) or not idempotency_key
                or len(idempotency_key) > 100
                or any(not 33 <= ord(char) <= 126 for char in idempotency_key)):
            raise _bad()
        state, truncated = build_state(doc, one_liner)
        questions = jev_questions(one_liner)
        with self._lock:
            index = self._next_key
            self._next_key = (index + 1) % len(self._keys)
        headers = {'Authorization': f'Bearer {self._keys[index]}', 'Idempotency-Key': idempotency_key}
        for attempt in range(MAX_RETRIES + 1):
            try:
                with self._limiters[index]:
                    response = self._http.post(URL, headers=headers, json={'model': self.model, 'state': state, 'questions': questions})
            except httpx.RequestError:
                # The worker can requeue with the same idempotency key.
                raise JevError('bad', 'Jev 요청을 완료하지 못했습니다', transient=True) from None
            status = response.status_code
            if status == 401:
                raise JevError('unconnected', 'Jev 연결 키를 확인해 주세요')
            if status == 402:
                raise JevError('insufficient', 'Jev 잔액이 부족합니다')
            if status == 429 or 500 <= status < 600:
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)
                    continue
                raise JevError('bad', 'Jev 요청 또는 응답을 확인해 주세요', transient=True)
            if status != 200:
                raise _bad()
            try:
                payload = response.json()
            except ValueError:
                raise _bad() from None
            return _parse_vote(payload, questions, truncated)
        raise _bad()


class FakeJevClient:
    """Deterministic offline adapter; constructs no HTTP client and needs no key."""
    def __init__(self, model):
        self.model = 'fake-' + model

    def judge(self, doc, one_liner, *, idempotency_key=None):
        import hashlib
        import random
        if not isinstance(doc.get('doc_id'), str) or not doc['doc_id']:
            raise _bad()
        state, truncated = build_state(doc, one_liner)
        rng = random.Random(hashlib.sha256(state.encode()).digest())
        answers = {}
        questions = jev_questions(one_liner)
        for name, question in questions.items():
            if question['type'] == 'noul':
                answers[name] = {'type': 'noul', 'noul': rng.random()}
            else:
                weights = {key: rng.random() for key in question['criteria']}
                total = sum(weights.values())
                probabilities = {key: value / total for key, value in weights.items()}
                choice = max(probabilities, key=probabilities.get)
                answers[name] = dict(type='choice', choice=choice,
                    probabilities=probabilities, confidence=probabilities[choice])
        return _parse_vote(dict(model=self.model, answers=answers), questions, truncated)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def get_jev_client(keys=None, model=None, transport=None):
    model = model or settings.jev_model
    if settings.jev_backend == 'fake':
        return FakeJevClient(model)
    return JevClient(settings.jev_api_keys if keys is None else keys, model, transport=transport)
