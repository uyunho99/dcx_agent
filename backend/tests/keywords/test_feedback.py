import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.context.store import StoreError, assert_writable, root_dir, session_dir, update_session
from app.context.versions import create_version
from app.keywords.events import KeywordEvent, REJECT_TAGS, append_event, load_events
from app.keywords.feedback import _inline, render_feedback_md, write_feedback_md


def event(kind, **fields):
    return KeywordEvent(ts='2026-09-28T12:00:00Z', round=1, type=kind, **fields)


@pytest.fixture
def sid(data_dir):
    update_session('feedback', {'schemaVersion': 2})
    return 'feedback'


def section(text, name):
    return text.split(f'## {name}\n', 1)[1].split('\n## ', 1)[0]


def test_sections_order():
    text = render_feedback_md([])
    assert [line for line in text.splitlines() if line.startswith('## ')] == [
        '## 방향 지시', '## 거절 사유', '## 원하는 방향', '## 오분류 이동']
    assert text.count('- 없음') == 4


def test_reject_examples_capped_8():
    text = render_feedback_md([event('reject', kw=f'예시{i:02}', tags=['common']) for i in range(12)])
    assert '12건' in text and '외 4건' in text
    for i in range(12):
        assert (f'예시{i:02}' in text) == (i < 8)


@pytest.mark.parametrize('kind', ['unreject', 'approve', 'add'])
@pytest.mark.parametrize('identity', [
    {'kwId': 'original'},
    {'kwId': 'different', 'kw': '저 소음'},
    {'kw': '저 소음'},
])
def test_later_restoration_removes_reject(kind, identity):
    events = [event('direction', text='방향 유지'),
              event('reject', kwId='original', kw='저소음', tags=['common']),
              KeywordEvent(ts='2026-09-27T12:00:00Z', round=1, type=kind, **identity)]
    text = render_feedback_md(events)
    assert section(text, '거절 사유').strip() == '- 없음'
    assert '방향 유지' in section(text, '방향 지시')


def test_reject_after_unreject_counts_again():
    events = [event('reject', kw='저소음', tags=['common'], note='이전 의견'),
              event('unreject', kw='저소음'),
              event('reject', kw='저소음', tags=['common'], note='새 의견')]
    text = section(render_feedback_md(events), '거절 사유')
    assert 'common (흔함) · 1건' in text
    assert '- 저소음 — 새 의견' in text
    assert '이전 의견' not in text


def test_reject_counts_and_overflow_exclude_restored_keywords():
    events = [event('reject', kw=f'예시{i:02}', tags=['common'], note=f'의견{i:02}')
              for i in range(12)]
    events.extend(event('unreject', kw=f'예시{i:02}') for i in (0, 10))
    text = section(render_feedback_md(events), '거절 사유')
    assert 'common (흔함) · 10건' in text
    assert '외 2건' in text
    assert '예시00' not in text and '의견00' not in text
    assert '예시10' not in text and '의견10' not in text
    assert '예시08' in text and '의견11' in text


@pytest.mark.parametrize('value', ['A_B', '에어컨*소음', r'A\B `C` [D] <E> #태그', 'A > B - C 1. D'])
def test_inline_preserves_content(value):
    assert _inline(value) == value
    assert f'- {value} (추가, 라운드 1)' in render_feedback_md([event('add', kw=value)])


@pytest.mark.parametrize(('value', 'expected'), [
    ('  #태그\n내용', r'\#태그 내용'),
    ('- 항목', r'\- 항목'),
    ('> 인용', r'\> 인용'),
    ('12. 항목', r'12\. 항목'),
])
def test_inline_escapes_only_leading_structure(value, expected):
    assert _inline(value) == expected


def test_misclassified_records_move():
    text = render_feedback_md([event('move', kw='저소음', **{
        'from': {'axis': 'physical', 'sub': '소음'},
        'to': {'axis': 'psychological', 'sub': '안심'}})])
    assert '저소음: physical/소음 → psychological/안심' in section(text, '오분류 이동')


def test_deterministic():
    events = [event('direction', text='첫 지시'), event('direction', text='다음 지시')]
    before = [ev.model_dump() for ev in events]
    text = render_feedback_md(events)
    assert text == render_feedback_md(events)
    assert text.index('첫 지시') < text.index('다음 지시')
    assert '2026' not in text
    assert [ev.model_dump() for ev in events] == before


def test_directions_latest_first():
    events = [event('direction', text='이전') , KeywordEvent(
        ts='2026-09-29T12:00:00Z', round=2, type='direction', text='최근')]
    text = render_feedback_md(events)
    assert text.index('최근') < text.index('이전')
    assert '라운드 2' in text


def test_reject_tag_order_and_notes():
    assert REJECT_TAGS == ('irrelevant', 'common', 'sentence', 'misclassified')
    text = render_feedback_md([event('reject', kw=tag, tags=[tag], note='자유 의견')
                               for tag in reversed(REJECT_TAGS)])
    assert [text.index(tag) for tag in REJECT_TAGS] == sorted(text.index(tag) for tag in REJECT_TAGS)
    assert '자유 의견' in text
    assert '태그 없는 의견' in render_feedback_md([event('reject', kw='냉방', note='태그 없는 의견')])


def test_desired_additions_and_moved_approvals():
    events = [event('add', kw='직접 추가'), event('add', kw='제안 추가'),
              event('move', kwId='m', kw='이동어'), event('approve', kwId='m'),
              event('approve', kw='일반 승인')]
    text = section(render_feedback_md(events), '원하는 방향')
    assert all(word in text for word in ['직접 추가', '제안 추가', '이동어'])
    assert '일반 승인' not in text


def test_append_roundtrip_single_write_and_fsync(sid, monkeypatch):
    import app.keywords.events as module
    writes, syncs, flags = [], [], []
    real_write, real_sync, real_open = os.write, os.fsync, os.open
    def write(fd, payload):
        writes.append(payload)
        return real_write(fd, payload)
    def sync(fd):
        syncs.append(fd)
        return real_sync(fd)
    def opening(path, flag, *args, **kwargs):
        flags.append(flag)
        return real_open(path, flag, *args, **kwargs)
    monkeypatch.setattr(module.os, 'write', write)
    monkeypatch.setattr(module.os, 'fsync', sync)
    monkeypatch.setattr(module.os, 'open', opening)
    ev = event('move', kw='한글\n키워드', **{'from': {'axis': 'physical', 'sub': '소음'}})
    append_event(sid, ev)
    assert len(writes) == len(syncs) == 1
    assert flags[0] & os.O_APPEND
    assert load_events(sid) == [ev]
    raw = (session_dir(sid) / 'keyword_events.jsonl').read_bytes()
    assert raw.count(b'\n') == 1
    assert 'from' in json.loads(raw)
    append_event(sid, event('unreject', kwId='m'))
    assert (session_dir(sid) / 'keyword_events.jsonl').read_bytes().startswith(raw)


@pytest.mark.parametrize('tail', [b'{"ts":', b'not json\n', b'{}\n', b'\xff'])
def test_load_events_skips_truncated_last_line(sid, caplog, tail):
    ev = event('add', kw='정상')
    append_event(sid, ev)
    with (session_dir(sid) / 'keyword_events.jsonl').open('ab') as stream:
        stream.write(tail)
    assert load_events(sid) == [ev]
    assert 'WARNING' in caplog.text


def test_missing_log(sid):
    assert load_events(sid) == []


def test_concurrent_appends(sid):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: append_event(sid, event('add', kw=str(i))), range(24)))
    assert sorted(ev.kw for ev in load_events(sid)) == sorted(map(str, range(24)))


def test_write_feedback_md_file_written_atomically(sid, monkeypatch):
    import app.keywords.feedback as module
    append_event(sid, event('add', kw='냉방'))
    target = session_dir(sid) / 'keyword_feedback.md'
    target.write_text('old', encoding='utf-8')
    real_replace = os.replace
    calls = []
    def replace(source, destination):
        assert target.read_text() == 'old'
        assert source.parent == target.parent
        calls.append((source, destination))
        return real_replace(source, destination)
    monkeypatch.setattr(module.os, 'replace', replace)
    text = write_feedback_md(sid)
    assert target.read_text() == text == render_feedback_md(load_events(sid))
    assert len(calls) == 1
    assert not calls[0][0].exists()


def test_version_isolation_and_readonly(sid):
    original, added = event('add', kw='원본'), event('add', kw='새 버전')
    append_event(sid, original)
    write_feedback_md(sid)
    first = root_dir(sid) / 'versions' / 'v1'
    filenames = ('keyword_events.jsonl', 'keyword_feedback.md')
    before = {name: (first / name).read_bytes() for name in filenames}

    assert create_version(sid, 'v1', 'stage1', '') == 'v2'
    second = root_dir(sid) / 'versions' / 'v2'
    assert session_dir(sid) == second
    append_event(sid, added)
    text = write_feedback_md(sid)
    assert [KeywordEvent.model_validate_json(line) for line in
            (second / 'keyword_events.jsonl').read_bytes().splitlines()] == [original, added]
    assert (second / 'keyword_feedback.md').read_text(encoding='utf-8') == text
    assert text == render_feedback_md([original, added])

    # Keyword writers target only the active version; check past-version refusal
    # through the store's explicit version guard without activating readonly v1.
    assert_writable(sid, version='v2')
    with pytest.raises(StoreError, match='읽기 전용'):
        assert_writable(sid, version='v1')
    assert {name: (first / name).read_bytes() for name in filenames} == before
    assert session_dir(sid) == second


def test_legacy_writes_rejected(data_dir):
    update_session('legacy', {'keywords': []})
    with pytest.raises(StoreError):
        append_event('legacy', event('add', kw='금지'))
    with pytest.raises(StoreError):
        write_feedback_md('legacy')


def test_append_after_truncated_tail(sid, caplog):
    first, last = event('add', kw='처음'), event('add', kw='나중')
    append_event(sid, first)
    path = session_dir(sid) / 'keyword_events.jsonl'
    with path.open('ab') as stream:
        stream.write(b'{"type":')
    original = path.read_bytes()
    append_event(sid, last)
    assert path.read_bytes().startswith(original)
    assert load_events(sid) == [first, last]
    assert 'WARNING' in caplog.text


def test_atomic_replace_failure_preserves_previous_file(sid, monkeypatch):
    import app.keywords.feedback as module
    path = session_dir(sid) / 'keyword_feedback.md'
    path.write_text('previous', encoding='utf-8')
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        write_feedback_md(sid)
    assert path.read_text() == 'previous'
    assert not list(path.parent.glob('.keyword-feedback-*.tmp'))


def test_inline_content_cannot_create_extra_sections():
    text = render_feedback_md([event('direction', text='냉방\n## 가짜 헤더')])
    assert len([line for line in text.splitlines() if line.startswith('## ')]) == 4


@pytest.mark.parametrize('kw_id', ['k_r1g1_0001', None])
def test_screen_and_commit_reject_count_once(kw_id):
    events = [event('reject', kwId=kw_id, kw=kw, tags=['common'])
              for kw in ['저 소음', '저소음']]
    text = section(render_feedback_md(events), '거절 사유')
    assert 'common (흔함) · 1건' in text
    assert text.count('- 저소음') == 1


def test_latest_reject_supplies_tags_and_note():
    events = [event('reject', kwId='same', kw='저소음', tags=['common'], note='이전 의견'),
              event('reject', kwId='same', kw='저소음', tags=['sentence'], note='최신 의견')]
    text = section(render_feedback_md(events), '거절 사유')
    assert 'common' not in text and '이전 의견' not in text
    assert 'sentence (문장형) · 1건' in text
    assert '최신 의견' in text


@pytest.mark.parametrize('count', [2, 10])
def test_reject_counts_distinct_keyword_ids(count):
    events = [event('reject', kwId=f'keyword-{i}', kw='같은 표기', tags=['common'])
              for i in range(count) for _ in range(2)]
    text = section(render_feedback_md(events), '거절 사유')
    assert f'common (흔함) · {count}건' in text
    assert text.count('- 같은 표기') == min(count, 8)
    if count > 8:
        assert f'외 {count - 8}건' in text
