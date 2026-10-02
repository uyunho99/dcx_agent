import json

from app.evidence.queries import PersonaQueryOut, _input_body, validate_queries
from app.evidence.tagging import TagOut, _input
from app.evidence.novelty import NoveltyOut
from app.llm.base import Attachment, LLMTask
from app.llm.fake import FakeBackend


def task(name, schema, attachments, instructions='offline QA'):
    return LLMTask(task='evidence.' + name, sid='echo', instructions=instructions,
                   attachments=attachments, output_schema=schema)


def test_queries_anchor_actual_ids_and_clean_forbidden_words():
    contexts = [dict(context_id=i, action='사용자는 예약', keywords=['고객은', '냉방']) for i in ['arbitrary-A', 'session-B']]
    body = _input_body({}, contexts, '제품', {c['context_id']: c['keywords'] for c in contexts}, None)
    result = FakeBackend().run(task('queries', PersonaQueryOut, [Attachment(title='input', body=body)]))
    assert result.ok
    assert validate_queries(result.data, ['arbitrary-A', 'session-B']) == []
    assert all(text.startswith('나는 ') for row in result.data.context_queries.values() for text in row.values())


def test_tag_exact_ids_quotes_variation_known_and_batch_independence():
    docs = {f'actual-{i}': dict(body='  냉방을 예약했어요.  다음 문장입니다.', title='제목', comments=[]) for i in range(60)}
    docs['comments-only'] = dict(comments=[dict(text='정확한  댓글!')])
    attachments = [Attachment(title=i, body=json.dumps(_input(doc, None))) for i, doc in docs.items()]
    request = task('tag', TagOut, attachments, 'Known Insight:\n#1 냉방을 예약했어요.\n#2 겹치지 않는 문장')
    result = FakeBackend().run(request)
    assert result.ok
    items = result.data.items
    assert [r.doc_id for r in items] == list(docs)
    assert any(not r.relevant and r.reason_code for r in items)
    assert any(r.pain_point for r in items) and any(r.unmet_need for r in items)
    assert min(r.polarity for r in items) < 0 < max(r.polarity for r in items)
    for row in items:
        q = row.quotes[0]
        source = docs[row.doc_id]['comments'][q.idx]['text'] if q.field == 'comment' else docs[row.doc_id][q.field]
        assert q.text in source
        assert row.known_match == ('none' if row.doc_id == 'comments-only' else '#1')
    assert FakeBackend().run(request.model_copy(update={'attachments': attachments[:1]})).data.items[0] == items[0]
    assert all(r.known_match == 'none' for r in FakeBackend().run(request.model_copy(update={'instructions':'Known Insight:\n#1 unrelated'})).data.items)


def test_novelty_only_requested_rows_and_full_spread():
    ids = [f'actual-{i}' for i in range(60)]
    result = FakeBackend().run(task('novelty', NoveltyOut, [Attachment(title='input', body=json.dumps(dict(new_rows=[dict(doc_id=i) for i in ids], core_reps=[dict(doc_id='excluded')])))]))
    assert result.ok
    assert [r.doc_id for r in result.data.items] == ids
    assert {r.novelty for r in result.data.items} == {'none','low','medium','high','very_high'}


def test_explicit_static_response_and_fixture_without_marker_remain_static(tmp_path):
    raw = '{"items": []}'
    request = task('tag', TagOut, [])
    assert FakeBackend({'evidence.tag': raw}).run(request).data.items == []
    (tmp_path / 'evidence.tag.json').write_text(raw)
    backend = FakeBackend()
    backend.fixture_dir = tmp_path
    assert backend.run(request).data.items == []


def test_default_no_attachment_examples_keep_static_fixtures():
    for name, schema in [('queries', PersonaQueryOut), ('tag', TagOut), ('novelty', NoveltyOut)]:
        result = FakeBackend().run(task(name, schema, []))
        expected = json.loads((FakeBackend.fixture_dir / f'evidence.{name}.json').read_text())
        assert result.ok
        assert json.loads(result.raw) == expected
