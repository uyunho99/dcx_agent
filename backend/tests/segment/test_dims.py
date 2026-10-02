import hashlib
import json
import sqlite3

import numpy as np
import pytest
from pydantic import ValidationError

from app.config import settings
from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.fake import FakeBackend
from app.segment import dims
from app.segment.store import SegmentStore
from tests.fixtures.segment_synth import fake_dims_backend


def item(doc_id, **values):
    return dict(doc_id=doc_id, **{dim: values.get(dim) for dim in dims.DIMENSIONS})


@pytest.fixture
def setup(data_dir, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    def build(n=12, contexts=1):
        rows = [dict(doc_id=f'd{c}-{i:03}', context_id=f'C{c}', theta=i / n,
                     evidence_level='core' if i < n - 1 else 'supporting', band='edge')
                for c in range(contexts) for i in range(n)]
        prepared = data_dir / 'derived/s/c1/p_aaaaaaaaaaaa/docs'
        prepared.mkdir(parents=True, exist_ok=True)
        docs = [dict(doc_id=r['doc_id'], title='제목', body='본문', comments=[{'text': '댓글'}],
                     evidence_level_pred=r['evidence_level'], tagProbs={'act': 0.5}) for r in rows]
        (prepared / 'part.jsonl').write_text(''.join(json.dumps(d) + '\n' for d in docs))
        export = data_dir / 'classified/s/v1/relevant.jsonl'
        export.parent.mkdir(parents=True, exist_ok=True)
        export.write_text(''.join(json.dumps(d) + '\n' for d in docs))
        session = dict(prep={'status': 'done', 'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_aaaaaaaaaaaa'}},
                       training={'exportRef': 'classified/s/v1/relevant.jsonl'})
        for version in ('v1', 'v2'):
            sessions.write_json(version_dir('s', version) / 'session.json', session)
        store = SegmentStore.open('s', 'v1')
        store.write_layers(contexts=[{'context_id': f'C{c}', 'flags': ['existing']} for c in range(contexts)], docs=rows)
        return store, rows
    return build


@pytest.fixture
def calls(monkeypatch):
    seen = []
    class Backend:
        def run(self, task):
            ids = [a.title for a in task.attachments]
            seen.append(ids)
            assert all('본문' in a.body and '댓글' in a.body for a in task.attachments)
            return fake_dims_backend(ids).run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    return seen


def cache_rows(data_dir):
    files = list((data_dir / 'llmcache/s/p_aaaaaaaaaaaa').glob('dims-*.sqlite'))
    with sqlite3.connect(files[0]) as db:
        return db.execute('SELECT doc_id FROM dims').fetchall()


def test_fixture_schema():
    raw = (FakeBackend.fixture_dir / 'segment.dims.json').read_text()
    assert dims.DimsOut.model_validate_json(raw).items
    missing = item('a'); del missing['task_goal']
    with pytest.raises(ValidationError):
        dims.DimsOut.model_validate({'items': [missing]})


def test_sample_cap_per_context(setup, calls):
    store, rows = setup(114, 2)
    result = dims.extract_sample('s', 'v1', store)
    assert result['sampled'] == 200
    assert len(calls) == 20 and all(len(batch) == 10 for batch in calls)
    assert {i for batch in calls for i in batch} == {r['doc_id'] for r in rows if 13 <= int(r['doc_id'][-3:]) <= 112}


def test_cache_hit_no_llm(setup, calls, data_dir):
    store, _ = setup()
    first = dims.extract_sample('s', 'v1', store)
    calls.clear()
    second = dims.extract_sample('s', 'v2', store)
    assert calls == [] and first == second
    pver = hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()
    assert (data_dir / f'llmcache/s/p_aaaaaaaaaaaa/dims-{pver}.sqlite').exists()
    assert len(cache_rows(data_dir)) == 11


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'outside'])
@pytest.mark.parametrize('recover', [False, True])
def test_batch_id_integrity(setup, monkeypatch, data_dir, bad, recover):
    store, _ = setup(4)
    calls = []
    class Backend:
        def run(self, task):
            ids = [a.title for a in task.attachments]
            calls.append(ids)
            if len(calls) == 1 or not recover:
                ids = ids[:-1] if bad == 'missing' else ids[:-1] + [ids[0] if bad == 'duplicate' else 'alien']
            return fake_dims_backend(ids).run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    result = dims.extract_sample('s', 'v1', store)
    assert len(calls) == 2
    assert result['dims_failed'] == ([] if recover else calls[0])
    assert len(cache_rows(data_dir)) == (3 if recover else 0)
    assert result['extracted'] == (3 if recover else 0)


def test_phrase_rules(setup, monkeypatch, data_dir):
    store, _ = setup(2)
    raw = {'items': [item('d0-000', task_goal='가' * 13, environment='나' * 12)]}
    monkeypatch.setattr(registry, 'get_backend', lambda name: FakeBackend(responses={'segment.dims': json.dumps(raw)}))
    result = dims.extract_sample('s', 'v1', store)
    assert result['phrase_too_long'] == 1
    assert result['coverage']['d0-000'] == dict(filled=1, has_goal=False, has_constraint=False)
    assert dims.extract_sample('s', 'v1', store)['phrase_too_long'] == 1
    with sqlite3.connect(next((data_dir / 'llmcache/s/p_aaaaaaaaaaaa').glob('dims-*.sqlite'))) as db:
        cached = json.loads(db.execute('SELECT context_dims FROM dims').fetchone()[0])
    assert cached['task_goal'] is None and cached['environment'] == '나' * 12


def test_code_normalization(monkeypatch):
    class Embedder:
        def embed(self, texts):
            return np.asarray([{'휴식': [1, 0], '휴 식': [0.9, 0.1], '휴식을': [1, 0.1],
                                '업무': [0.84, np.sqrt(1 - .84**2)]}[t] for t in texts]) * 3
    monkeypatch.setattr(dims, 'get_embedder', lambda: Embedder())
    raw = {str(i): item(str(i), task_goal=t) for i, t in enumerate(['휴식', '휴식', '휴 식', '휴식을', '업무'])}
    coded, codes = dims.normalize_dims(raw)
    assert len(codes) == 2
    assert coded['0']['task_goal'] == coded['2']['task_goal'] == coded['3']['task_goal']
    assert coded['4']['task_goal'] != coded['0']['task_goal']
    assert next(c for c in codes if c['count'] == 4)['label'] == '휴식'


def test_combo_rarity_monotonic(monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    raw = {str(i): item(str(i), task_goal='휴식', resource_constraint='비용' if i < 4 else '시간') for i in range(5)}
    coded, codes = dims.normalize_dims(raw)
    combos = dims.count_combos(coded)
    assert sorted(c['count'] for c in combos) == [1, 4]
    scores = dims.combo_rarity(raw, codes, combos)
    assert 0 <= scores['0'] < scores['4'] <= 1
    lazy = dims.combo_rarity({'outside': raw['0'], 'new': item('new', task_goal='새목적', resource_constraint='새제약')}, codes, combos)
    assert lazy['outside'] == scores['0'] and lazy['new'] == 1
    assert dims.combo_rarity({'empty': item('empty')}, codes, combos) == {'empty': 0}


def test_summary(setup, monkeypatch):
    store, _ = setup(5)
    rows = [item('d0-000', task_goal='휴식', resource_constraint='비용'),
            item('d0-001', task_goal='휴식', resource_constraint='비용', activity_response='예약'),
            item('d0-002', task_goal='휴식', resource_constraint='시간'), item('d0-003')]
    monkeypatch.setattr(registry, 'get_backend', lambda name: FakeBackend(responses={'segment.dims': json.dumps({'items': rows})}))
    result = dims.extract_sample('s', 'v1', store)
    assert result['empty_goal_or_constraint'] == .25 and result['act_mismatch'] == 3
    context = store.contexts()[0]
    assert context['dominant_constraint'] == '비용'
    assert context['dims_summary']['resource_constraint'][0]['count'] == 2
    assert context['flags'] == ['existing']
    assert result['contexts']['C0']['act_mismatch'] == 3
    with store._db() as db:
        assert db.execute('SELECT SUM(count) FROM combos').fetchone()[0] == 3
        assert db.execute('SELECT COUNT(*) FROM docs WHERE combo_rarity IS NOT NULL').fetchone()[0] == 4


def test_empty_context(setup, calls):
    store, _ = setup(1)
    result = dims.extract_sample('s', 'v1', store)
    assert result['sampled'] == 0 and result['empty_goal_or_constraint'] == 0
    assert calls == [] and store.contexts()[0]['dominant_constraint'] is None


def test_prompt_change_invalidates_cache(setup, calls, monkeypatch, tmp_path):
    store, _ = setup(2)
    dims.extract_sample('s', 'v1', store)
    prompt = tmp_path / 'changed.md'
    prompt.write_bytes(dims.PROMPT_PATH.read_bytes() + b'\n')
    monkeypatch.setattr(dims, 'PROMPT_PATH', prompt)
    dims.extract_sample('s', 'v1', store)
    assert len(calls) == 2


def test_act_reverse_mismatch(setup, monkeypatch, data_dir):
    store, _ = setup(3)
    path = data_dir / 'classified/s/v1/relevant.jsonl'
    docs = [json.loads(line) for line in path.read_text().splitlines()]
    for doc in docs:
        doc['tagProbs']['act'] = .49
    path.write_text(''.join(json.dumps(doc) + '\n' for doc in docs))
    raw = {'items': [item('d0-000', activity_response='예약'), item('d0-001')]}
    monkeypatch.setattr(registry, 'get_backend', lambda name: FakeBackend(responses={'segment.dims': json.dumps(raw)}))
    result = dims.extract_sample('s', 'v1', store)
    assert result['act_mismatch'] == 1 and result['extracted'] == 2
    assert result['dims_failed'] == []


def test_two_pairs_use_max_and_frozen_scale(monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    raw = {str(i): item(str(i), task_goal='휴식', resource_constraint='비용',
                       environment='집', activity_response='예약' if i < 3 else '정지') for i in range(4)}
    coded, codes = dims.normalize_dims(raw)
    combos = dims.count_combos(coded)
    scores = dims.combo_rarity(raw, codes, combos)
    assert scores == {'0': 0., '1': 0., '2': 0., '3': 1.}
    assert dims.combo_rarity({'lazy': raw['3']}, codes, combos) == {'lazy': 1.}


@pytest.mark.parametrize('sem', [None, {'act': 0}])
def test_nullable_export_probabilities_resume(setup, calls, data_dir, sem):
    store, _ = setup(4)
    path = data_dir / 'classified/s/v1/relevant.jsonl'
    docs = [json.loads(line) for line in path.read_text().splitlines()]
    docs[0].update(tagProbs=None, pred_entropy=None, sem=sem)
    docs[1].update(tagProbs={'sem': None}, pred_entropy=None, sem=None)
    path.write_text(''.join(json.dumps(doc) + '\n' for doc in docs))
    first = dims.extract_sample('s', 'v1', store)
    assert first['act_unknown'] == 2
    assert first['act_mismatch'] == 0
    assert first['contexts']['C0']['act_unknown'] == 2
    assert dims.extract_sample('s', 'v1', store) == first
