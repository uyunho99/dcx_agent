"""T4 storage, shared cache and stage 7 -> 8 wire contract."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import sqlite3

import pytest
from pydantic import ValidationError

from app.evidence import params
from app.evidence.cache import TagCache, prompt_version
from app.evidence.package import EvidencePackage
from app.evidence.store import EvidenceStore

PREP = 'p_0123456789ab'
TABLES = {'meta', 'queries', 'candidates', 'selected', 'contexts', 'persona_support'}


@pytest.fixture
def store(data_dir):
    return EvidenceStore.open('test-session', 'v1')


def populate(store, run='r1'):
    store.reset(run, {'select_n': 10, 'label': '근거'})
    store.write_queries('context:c1', [dict(dim='Sense', text=run, origin='llm')])
    store.write_candidates('c1', [dict(doc_id=run, relevance=.8, dims_hit=['Sense'], band='core', round='cov')])
    store.write_selected('c1', 'all', [dict(rank=1, doc_id=run, role='support', quality=.9)])
    store.set_context('c1', 'p1', 'done', coverage=4, counts={'all': 1})
    store.write_persona_support('p1', [dict(rank=1, doc_id=run, kind='desire')])


def test_schema_wal_version_isolation_and_reset(store, data_dir):
    assert store.path == data_dir / 'sessions/test-session/versions/v1/evidence/evidence.sqlite'
    assert store.get_run() is None
    with store._db() as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == TABLES
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
    populate(store)
    assert EvidenceStore.open('test-session', 'v1').get_run() == 'r1'
    assert EvidenceStore.open('test-session', 'v2').get_run() is None
    store.reset('r2', {'n': 2})
    snap = store.snapshot()
    assert snap.run == 'r2' and snap.params == {'n': 2} and snap.started_at
    with store._db() as db:
        for table in TABLES - {'meta'}:
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM meta').fetchone()[0] == 1


def test_rows_json_replacement_and_context_updates(store):
    populate(store)
    store.write_queries('persona:p1', [dict(dim='artifact', text='물건', origin='fallback')])
    store.write_queries('context:c1', [dict(dim='Act', text='행동', origin='regen')])
    assert len(store.queries()) == 2
    assert store.queries('context:c1')[0]['dim'] == 'Act'
    assert store.candidates('c1')[0]['dims_hit'] == ['Sense']
    assert store.candidates('c1')[0]['round'] == 'cov'
    store.write_candidates('c1', [dict(doc_id='d2', relevance=.4, dims_hit_json='["Feel"]', band='edge')])
    assert [r['doc_id'] for r in store.candidates('c1')] == ['d2']
    assert store.candidates('c1')[0]['round'] == 0
    store.set_context('c1', 'p1', 'running', error=None)
    assert store.contexts()[0]['counts'] == {'all': 1}
    assert store.contexts()[0]['coverage'] == 4
    store.write_persona_support('p1', [dict(rank=2, doc_id='a', kind='artifact')])
    assert [r['doc_id'] for r in store.snapshot().persona_support] == ['a']
    assert store.snapshot().params['label'] == '근거'


def test_selected_replaces_only_one_tab_and_context(store):
    populate(store)
    row = dict(rank=1, doc_id='new', role='rare', quality=.7, novelty='high', novelty_reason='새로움')
    store.write_selected('c1', 'new', [row])
    store.write_selected('c2', 'all', [row])
    store.write_selected('c1', 'all', [row])
    assert [r['doc_id'] for r in store.selected('c1', 'all')] == ['new']
    store.write_selected('c1', 'all', [])
    assert len(store.selected('c1')) == 1
    assert store.selected('c1', 'new')[0]['novelty_reason'] == '새로움'
    assert len(store.selected('c2', 'all')) == 1


def test_invalid_replace_rolls_back(store):
    populate(store)
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        store.write_selected('c1', 'all', [dict(rank=2, doc_id='bad', role='support', unexpected=1)])
    assert store.selected('c1', 'all')[0]['doc_id'] == 'r1'
    with pytest.raises(sqlite3.IntegrityError):
        store.write_selected('c1', 'all', [
            dict(rank=1, doc_id='valid', role='support'),
            dict(rank=2, doc_id='invalid', role='unsupported'),
        ])
    assert store.selected('c1', 'all')[0]['doc_id'] == 'r1'


def test_schema_ddl_only_on_first_open(store, data_dir, monkeypatch):
    TagCache.open('test-session', PREP, '0123456789ab')
    original_connect = sqlite3.connect
    statements = []

    def traced_connect(*args, **kwargs):
        db = original_connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(sqlite3, 'connect', traced_connect)
    EvidenceStore.open('test-session', 'v1')
    TagCache.open('test-session', PREP, '0123456789ab')
    assert not any(sql.lstrip().upper().startswith(('CREATE', 'ALTER', 'DROP')) for sql in statements)


def test_snapshot_reads_during_uncommitted_write(store):
    populate(store)
    with store._db(write=True) as db:
        db.execute("UPDATE meta SET run='r2'")
        db.execute("DELETE FROM selected")
        with ThreadPoolExecutor(max_workers=1) as pool:
            snap = pool.submit(store.snapshot).result(timeout=5)
        assert snap.run == 'r1' and snap.selected[0]['doc_id'] == 'r1'
    assert store.snapshot().run == 'r2'
    assert store.snapshot().selected == []


def test_snapshot_never_mixes_generations(store, monkeypatch):
    populate(store)
    original_db = store._db
    writer = EvidenceStore.open('test-session', 'v1')
    committed = []

    @contextmanager
    def interleaved_db(*, write=False):
        with original_db(write=write) as db:
            def trace(sql):
                # The run has been read; commit a whole new generation before rows are read.
                if sql.lstrip().upper().startswith('SELECT') and 'queries' in sql.lower() and not committed:
                    committed.append(True)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(populate, writer, 'r2').result(timeout=5)
            db.set_trace_callback(trace)
            yield db
    monkeypatch.setattr(store, '_db', interleaved_db)
    snap = store.snapshot()
    assert committed
    assert snap.run == 'r1'
    assert snap.queries[0]['text'] == 'r1'
    assert snap.candidates[0]['doc_id'] == snap.selected[0]['doc_id'] == 'r1'
    assert snap.persona_support[0]['doc_id'] == 'r1'
    assert writer.get_run() == 'r2'


def test_cache_path_prompt_hash_reopen_and_prep_isolation(data_dir, tmp_path):
    prompt = tmp_path / 'tag.v1.md'
    prompt.write_text('태깅 v1', encoding='utf-8')
    pver = prompt_version('tag', prompt_dir=tmp_path)
    assert pver == hashlib.sha256(prompt.read_bytes()).hexdigest()[:12]
    cache = TagCache.open('test-session', PREP, pver)
    assert cache.path == data_dir / 'llmcache' / 'test-session' / PREP / f'tag-{pver}.sqlite'
    tags = dict(relevant=True, reason_code=None, polarity=None, pain_point={'text': '소음', 'quote': None},
                unmet_need=None, situation={'state': None, 'emotion': '불편', 'barrier': None},
                artifacts=['선풍기'], quotes=[{'text': '시끄러워요'}])
    cache.put_tags({'d1': tags}, model='fake')
    assert TagCache.open('test-session', PREP, pver).get_tags(iter(['d1', 'missing'])) == {'d1': {**tags, 'model': 'fake'}}
    assert cache.get_tags([]) == {}
    cache.put_tags({'d1': {**tags, 'polarity': -.5}}, model='fake2')
    assert cache.get_tags(['d1'])['d1']['model'] == 'fake2'
    prompt.write_text('태깅 v2', encoding='utf-8')
    changed = TagCache.open('test-session', PREP, prompt_version('tag', prompt_dir=tmp_path))
    assert changed.path != cache.path and changed.get_tags(['d1']) == {}
    assert TagCache.open('test-session', 'p_abcdef012345', pver).get_tags(['d1']) == {}
    with cache._db() as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'tags', 'known'}
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def test_known_incremental_add_delete_preserves_other_ki_and_tags(data_dir):
    cache = TagCache.open('test-session', PREP, '0123456789ab')
    cache.put_tags({'d1': {'relevant': True}}, 'fake')
    cache.put_known({('d1', 'ki1'): True, ('d2', 'ki1'): False}, 'fake')
    assert cache.get_known(iter(['d1', 'd2']), iter(['ki1', 'ki2'])) == {('d1', 'ki1'): True, ('d2', 'ki1'): False}
    cache.put_known({('d1', 'ki2'): False, ('d2', 'ki2'): True}, 'fake')
    cache.drop_known('ki1')
    cache.drop_known('missing')
    assert cache.get_known(['d1', 'd2'], ['ki1', 'ki2']) == {('d1', 'ki2'): False, ('d2', 'ki2'): True}
    assert cache.get_known([], ['ki2']) == cache.get_known(['d1'], []) == {}
    assert cache.get_tags(['d1'])['d1']['relevant'] is True


def package_payload():
    quote = dict(field='comment', idx=0, start=0, end=3, text='불편해', verified=True)
    item = dict(doc_id='d1', source='forum', quote=quote, tags=['Feel'], polarity=-.5,
                novelty='high', known_match=None, tab=['all', 'new'], role='support',
                dist_centroid=None, combo_rarity=None)
    metrics = dict(importance=.5, satisfaction=.2, odi=.8, doc_count=10, author_count=8,
                   provisional=['odi', 'importance', 'satisfaction'])
    context = dict(context_id='c1', context_name='밤', action='취침',
                   situation={'state': '밤', 'emotion': None, 'barrier': '소음'}, situation_origin='dims',
                   dominant_constraint=None, keywords=['취침'],
                   metrics={**metrics, 'quality': dict(cohesion=.8, boundary=None, stability=.7, npmi=.6)},
                   evidence=[item], counter_evidence=[{**item, 'role': 'counter', 'quote': None}],
                   rare_evidence=[{**item, 'role': 'rare', 'dist_centroid': .9, 'combo_rarity': .8}], flags=['few_docs'])
    persona = dict(cluster_id='cl1', persona_id='p1', persona_name='이름', desire='편안함', goal=['숙면'],
                   desire_support=[item], artifacts=[dict(name='선풍기', mention_count=2)], metrics=metrics,
                   quality=dict(cohesion=.8, boundary=.4, stability_ari=None))
    return dict(schema='evidence-package/1', version='v2', params={'SELECT_N': 10},
                personas=[dict(persona_evidence=persona, context_evidence=[context])])


def test_package_json_roundtrip_exact_keys_and_schema_alias():
    payload = package_payload()
    model = EvidencePackage.model_validate_json(json.dumps(payload))
    assert model.schema_ == 'evidence-package/1'
    assert json.loads(model.model_dump_json(by_alias=True)) == payload
    assert EvidencePackage.model_validate(model.model_dump()).schema_ == model.schema_


@pytest.mark.parametrize('field,value', [('role', 'invalid'), ('tab', ['old'])])
def test_package_rejects_invalid_item_literals(field, value):
    payload = package_payload()
    payload['personas'][0]['context_evidence'][0]['evidence'][0][field] = value
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(payload)


def test_parameter_contract():
    assert params.QUERY_DIMS == ('Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome', 'Counter', 'Residual')
    assert params.FORBIDDEN == r'페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은'
    expected = dict(TOP_PER_QUERY=15, CANDIDATES_M=50, CORE_BONUS=.05, TAG_BATCH=8,
                    TAG_BODY_CHARS=1500, TAG_COMMENTS=10, TAG_COMMENT_CHARS=300, KI_SUMMARY_CHARS=200,
                    SELECT_N=10, W_RARITY=.3, DPP_SIGMA=.3, COVERAGE_MIN=4, COVERAGE_EXTRA=15,
                    TAG_PROB_ON=.5, RARE_MIN=2, DUP_COSINE=.95, NEW_EXPAND=50, NEW_EXPAND_MAX=3,
                    NOVELTY_SHOW=('high', 'very_high'), NOVELTY_CORE_REPS=5, COUNTER_POLARITY_GAP=.3,
                    COUNTER_TOP=5, RARE_TOP=5, DESIRE_TOP=5, UNDIFF_COSINE=.8, UNDIFF_MIN=3, CONCURRENCY=4,
                    PROVISIONAL=('W_RARITY', 'DPP_SIGMA', 'NOVELTY_SHOW', 'odi', 'persona_metrics'))
    assert {key: getattr(params, key) for key in expected} == expected
