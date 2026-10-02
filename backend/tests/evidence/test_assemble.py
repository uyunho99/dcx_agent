"""T10 assembly rules and on-disk stage 7 -> 8 contract (offline)."""
import json

import numpy as np
import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.evidence import assemble as assembly
from app.evidence.cache import TagCache, prompt_version
from app.evidence.package import EvidencePackage
from app.evidence.store import EvidenceStore
from app.model.infer import prepared_root
from app.segment.store import SegmentStore
from app.vectors.store import VectorStore


def pool(n=9):
    rows = [dict(doc_id=f'd{i}', relevance=1-i/100, band='edge', dims_hit=['Counter']) for i in range(n)]
    tags = {r['doc_id']: dict(relevant=True, polarity=-.6, pain_point={'text': '불편'},
                            unmet_need=None, known_match='ki_1', artifacts=[]) for r in rows}
    docs = {r['doc_id']: dict(combo_rarity=0, polarity=1) for r in rows}
    return rows, tags, docs


def test_counter_evidence_rule():
    rows, tags, _ = pool()
    tags['d0']['relevant'] = False
    rows[1]['dims_hit'] = ['Act']
    tags['d2']['polarity'] = -.599  # just outside the inclusive boundary
    tags['d8']['polarity'] = None
    result = assembly.counter_evidence(rows, tags, context_mean=-.3)
    assert [r['doc_id'] for r in result] == ['d3', 'd4', 'd5', 'd6', 'd7']
    assert assembly.counter_evidence(rows, tags, context_mean=None) == []


def test_rare_evidence_top5():
    rows, tags, docs = pool()
    rows[0]['band'] = 'core'
    tags['d1']['relevant'] = False
    tags['d2']['pain_point'] = None
    docs['d8']['combo_rarity'] = 1  # rank by the shared quality formula
    assert [r['doc_id'] for r in assembly.rare_evidence(rows, tags, docs)] == ['d8', 'd3', 'd4', 'd5', 'd6']


def test_undifferentiated_candidate(tmp_path):
    rows, _, _ = pool(4)
    vectors = {'d0': [1, 0, 0], 'd1': [.8, .6, 0], 'd2': [.8, 0, .6], 'd3': [0, 0, 0]}
    assert assembly.undifferentiated_candidate(rows, vectors) == []  # connected chain is not a clique
    vectors['d2'] = [1, 0, 0]
    assert assembly.undifferentiated_candidate(rows, vectors) == ['d0', 'd1', 'd2']
    store = SegmentStore(tmp_path)
    store.write_layers(contexts=[dict(context_id='c1', persona_id='p1', flags=['few_docs'])])
    assembly.append_context_flag(store, 'c1', 'undifferentiated_candidate')
    assembly.append_context_flag(store, 'c1', 'undifferentiated_candidate')
    assert store.contexts()[0]['flags'] == ['few_docs', 'undifferentiated_candidate']


def test_desire_support_top5():
    rows, tags, _ = pool()
    ranked = [dict(doc_id=r['doc_id'], rank=i, kind='desire') for i, r in enumerate(rows)]
    tags['d0']['relevant'] = False
    ranked[1]['kind'] = 'artifact'
    assert [r['doc_id'] for r in assembly.desire_support(ranked, tags)] == ['d2', 'd3', 'd4', 'd5', 'd6']


def test_artifacts_normalized_and_filtered():
    tags = {'a': {'artifacts': [' Remote Control ', 'REMOTE\tCONTROL', '제품', 'Air Con', 'AIRCON필터', '1']},
            'b': {'artifacts': ['remote control', '충전 기']}, 'outsider': {'artifacts': ['가방']}}
    assert assembly.artifacts(['a', 'b'], tags, 'Air Con') == [
        {'name': 'remotecontrol', 'mention_count': 3}, {'name': '충전기', 'mention_count': 1}]


@pytest.fixture
def persisted(data_dir):
    sid, version = 'test-session', 'v1'
    base = version_dir(sid, version)
    session = dict(bk='Air Con', prep=dict(status='done', derivedRef=dict(collectionId='c1', prepKey='p_0123456789ab')),
                   knownInsights=[dict(id='ki_1', type='statement', text='기존 내용')])
    sessions.write_json(base / 'session.json', session)
    root = prepared_root(sid, session)
    (root / 'docs').mkdir(parents=True)
    original = [dict(doc_id=f'd{i}', title='제목', body='정말 불편해요.', source='cafe',
                     author_hash='same', comments=[{'text': '댓글', 'author_hash': f'comment{i}'}]) for i in range(8)]
    sessions.atomic_write(root / 'docs/part-00001.jsonl', ''.join(json.dumps(d, ensure_ascii=False)+'\n' for d in original))
    seg = SegmentStore.open(sid, version)
    seg.write_layers(clusters=[dict(cluster_id='cl1', quality={'cohesion': .8})],
        personas=[dict(persona_id='p1', cluster_id='cl1', name='페르소나', desire='편안함', goals=['휴식'])],
        contexts=[dict(context_id='c1', persona_id='p1', name='상황1', action='조절', flags=['few_docs'],
                       dims_summary={'environment': [{'label': '실내', 'count': 3}], 'task_goal': [{'label': '휴식', 'count': 2}]}),
                  dict(context_id='c2', persona_id='p1', name='상황2', action='이동', flags=[])],
        docs=[dict(doc_id=f'd{i}', persona_id='p1', context_id='c1' if i < 6 else 'c2',
                   theta=.5 if i < 6 else 1., sentiment=-1 if i < 6 else 1.,
                   author_hash='same', band='edge', source='cafe', combo_rarity=.5, dist_centroid=.7) for i in range(8)])
    ev = EvidenceStore.open(sid, version)
    ev.reset('r1', {'SELECT_N': 10})
    ev.write_candidates('c1', [dict(doc_id=f'd{i}', relevance=1-i/10, dims_hit=['Counter'], band='edge') for i in range(6)])
    ev.write_selected('c1', 'all', [dict(doc_id='d0', rank=1, role='support')])
    ev.write_selected('c1', 'new', [dict(doc_id='d0', rank=1, role='support', novelty='high')])
    ev.set_context('c1', 'p1', 'done', coverage=4, counts={'coverage_supplements': 1, 'new_expansions': 2,
        'rare_fallback': 1, 'dpp_fill': 2, 'lazy_dims': 3, 'llm_calls': 4, 'cache_hits': 5, 'query_gen_fail': 1})
    ev.set_context('c2', 'p1', 'done', coverage=0)
    ev.write_persona_support('p1', [dict(doc_id=f'd{i}', rank=i+1, kind='desire') for i in range(8)])
    cache = TagCache.open(sid, session['prep']['derivedRef']['prepKey'], prompt_version('tag'))
    tags = {f'd{i}': dict(relevant=i != 6, reason_code='ad' if i == 6 else None, polarity=-1 if i == 0 else 1,
                         pain_point={'text': '불편'}, unmet_need=None, artifacts=['Remote Control'],
                         situation={'state': '태그 상황', 'emotion': None, 'barrier': None}, situation_origin='tag',
                         quotes=[dict(field='body', idx=None, start=0, end=9, text='정말 불편해요.', verified=True)]) for i in range(7)}
    cache.put_tags(tags, 'fake')
    cache.put_known({('d0', 'ki_1'): True, ('d1', 'deleted'): True}, 'fake')
    VectorStore(root).write_shard([f'd{i}' for i in range(8)], np.tile([1., 0], (8, 1)), [False]*8)
    return sid, version, base, seg, ev


def test_metrics(persisted):
    _, _, _, seg, _ = persisted
    ranges = assembly.session_minmax(seg)
    c1 = assembly.context_metrics(seg, 'c1', session_minmax=ranges)
    c2 = assembly.context_metrics(seg, 'c2', session_minmax=ranges)
    assert (c1['importance'], c1['satisfaction'], c1['odi']) == (1., 0., 2.)
    assert (c2['importance'], c2['satisfaction'], c2['odi']) == (0., 1., 0.)
    assert c1['doc_count'] == 6 and c1['author_count'] == 1
    p = assembly.persona_metrics([c1, c2], seg.docs(limit=1000))
    assert (p['importance'], p['satisfaction'], p['odi']) == (.75, .25, 1.5)
    assert p['doc_count'] == 8 and p['author_count'] == 1


def test_metrics_missing_and_constant(tmp_path):
    seg = SegmentStore(tmp_path)
    seg.write_layers(contexts=[dict(context_id='empty', persona_id='p'), dict(context_id='c', persona_id='p')],
                     docs=[dict(doc_id='d', context_id='c', persona_id='p', theta=1)])
    ranges = assembly.session_minmax(seg)
    assert assembly.context_metrics(seg, 'empty', session_minmax=ranges)['importance'] is None
    metric = assembly.context_metrics(seg, 'c', session_minmax=ranges)
    assert metric['importance'] == 0. and metric['satisfaction'] is None and metric['odi'] is None


def test_package_schema_and_fields(persisted):
    sid, version, base, seg, ev = persisted
    package = assembly.assemble(sid, version)
    saved = json.loads((base / 'evidence/package.json').read_text())
    assert EvidencePackage.model_validate(saved) == package
    block = saved['personas'][0]
    context = block['context_evidence'][0]
    assert context['evidence'][0]['tab'] == ['all', 'new']
    assert context['evidence'][0]['novelty'] == 'high'
    assert context['evidence'][0]['known_match'] == 'ki_1'
    assert context['counter_evidence'][0]['doc_id'] == 'd0'
    assert len(context['rare_evidence']) == 5
    assert context['rare_evidence'][1]['known_match'] == 'none'
    assert context['situation']['state'] == '실내 휴식' and context['situation_origin'] == 'dims'
    assert context['action'] == '조절'
    assert context['evidence'][0]['quote']['start'] == 0
    assert context['evidence'][0]['source'] == 'cafe'
    assert 'undifferentiated_candidate' in seg.contexts()[0]['flags']
    assert ev.contexts()[0]['counts']['undifferentiated'] == ['d0', 'd1', 'd2']
    assert len(block['persona_evidence']['desire_support']) == 5
    assert block['persona_evidence']['artifacts'] == [{'name': 'remotecontrol', 'mention_count': 7}]
    assert saved['params']['COUNTER_POLARITY_GAP'] == .3
    assert assembly.assemble(sid, version) == package  # repeatable, flags don't duplicate


def test_stage7_report_fields(persisted):
    sid, version, base, _, _ = persisted
    assembly.assemble(sid, version)
    report = json.loads((base / 'evidence/stage_7.json').read_text())
    assert report['coverage'] == {'c1': {'covered': 4, 'total': 6}, 'c2': {'covered': 0, 'total': 6}}
    for field, value in dict(coverage_supplements=1, new_expansions=2, rare_fallback=1, dpp_fill=2,
                             lazy_dims=3, llm_calls=4, cache_hits=5, query_gen_fail=1, untagged=1,
                             relevant_false=1).items():
        assert report[field] == value
    assert report['reason_code'] == {'ad': 1}
    assert report['per_tab_counts'] == {'all': 1, 'new': 1}
    assert report['band_exposure_ratios'] == {'edge': 1.}
    assert report['novelty_distribution'] == {'high': 1}
    assert report['known_match_distribution'] == {'ki_1': 2}
    assert report['escalation_candidates'] == {'c1': ['d0', 'd1', 'd2']}
    assert report['params']['UNDIFF_COSINE'] == .8
    assert not any('agreement' in k or '일치율' in k for k in report)
    assert assembly.stage_report({}, {})['per_tab_counts'] == {'all': 0, 'new': 0}


def test_metrics_include_more_than_store_default_limit(tmp_path):
    seg = SegmentStore(tmp_path)
    seg.write_layers(contexts=[dict(context_id='c1', persona_id='p'), dict(context_id='c2', persona_id='p')],
        docs=[dict(doc_id=f'd{i:04}', persona_id='p', context_id='c1' if i < 1001 else 'c2',
                   theta=1., sentiment=0., author_hash=f'a{i}') for i in range(1002)])
    metric = assembly.context_metrics(seg, 'c1', session_minmax=assembly.session_minmax(seg))
    assert metric['doc_count'] == metric['author_count'] == 1001
    assert metric['importance'] == 1.


def test_assembly_with_real_stage6_fixture(data_dir):
    from tests.fixtures.evidence_synth import make_evidence_session
    fixture = make_evidence_session(data_dir)
    ev = EvidenceStore.open(fixture.sid, fixture.version)
    ev.reset('r-fixture', {})
    seg = SegmentStore.open(fixture.sid, fixture.version)
    for context in seg.contexts():
        ev.set_context(context['context_id'], context['persona_id'], 'skipped', coverage=0)
    package = assembly.assemble(fixture.sid, fixture.version)
    assert len(package.personas) == len(seg.personas())
    assert sum(p.persona_evidence.metrics.doc_count for p in package.personas) == len(seg.docs(limit=100000))
    assert all(c.action for p in package.personas for c in p.context_evidence)
    assert all(p.persona_evidence.quality['cohesion'] is None for p in package.personas)
