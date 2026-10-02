"""Deterministic stage-eight fixtures, independent of the stage-seven producer.

Default: four Personas, eleven Contexts, all six zones, two stars, one counter
Context, unverified quotes and one Context without evidence. Coordinates are
intentional, not random. ``seed`` selects the reproducible synthetic session.
"""
from copy import deepcopy
import json
import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

from app.config import settings
from app.context import store as sessions
from app.llm.fake import FakeBackend
from app.persona.package import Package, evidence_index
from app.segment.store import SegmentStore
from app.services import s3
from app.vectors.embedder import FakeEmbedder
from tests.fixtures.segment_synth import CHANNELS, make_segment_session

CONSTRAINT = '의료적 효과 표현 금지'
PROJECT_CONTEXT = dict(bk='LG 에어컨', oneLiner='편안한 실내 생활',
    researchQuestion={'text': '냉방 조절의 불편은 무엇인가?'},
    projectType={'choice': 'ux'}, analysisGoal={'choice': 'needs'},
    constraints=[CONSTRAINT], keyMetrics=['사용 만족도'], targetScope={'note': '가정용 냉방'},
    productCategory={'l1': '가전', 'l2': '에어컨', 'source': 'user'},
    positioning={'price': 'value', 'market': 'leader'}, channels=['naver_cafe'])
# With the remaining points at (.2, .1), S_mean stays below .35, including
# the ten-Context variant. These points therefore realize A, B, C, D, E, F.
POINTS = ((.05, .85), (.65, .55), (.98, .6), (0., .35), (.3, .2), (.95, .05))
QUOTE = 'LG 에어컨을 사용하며 냉방과 전기료를 살펴봤습니다.'
DOCS_PER_CONTEXT = 8


def _counts(personas, contexts, big_persona_contexts):
    counts = list(contexts)
    if personas < 1 or len(counts) != personas or any(not isinstance(n, int) or n < 1 for n in counts):
        raise ValueError('Expected one positive context count per persona')
    if big_persona_contexts is not None:
        if not isinstance(big_persona_contexts, int) or big_persona_contexts < 1:
            raise ValueError('big_persona_contexts must be positive')
        counts[0] = big_persona_contexts
    return counts


def _metrics(i, s, count=DOCS_PER_CONTEXT):
    return dict(importance=i, satisfaction=s, odi=i + max(i-s, 0),
                doc_count=count, author_count=count // 2,
                provisional=['odi', 'importance', 'satisfaction'])


def _evidence(index, offset=0, *, role='support', novelty='low', verified=True):
    text = QUOTE if verified else '원문에서 확인되지 않은 합성 인용'
    return dict(doc_id=f'd{index * DOCS_PER_CONTEXT + offset:06d}', source=CHANNELS[(index * DOCS_PER_CONTEXT + offset) % len(CHANNELS)],
                quote=dict(field='body', idx=None, start=0 if verified else None,
                           end=len(text) if verified else None, text=text, verified=verified),
                tags=['situation', 'pain_point'], polarity=-0.5, novelty=novelty,
                known_match=None, tab=['all', 'new'], role=role, dist_centroid=None, combo_rarity=None)


def make_package(*, personas=4, contexts=(3, 3, 3, 2), big_persona_contexts=None, seed=42, qa_failed_persona=None) -> dict:
    counts = _counts(personas, contexts, big_persona_contexts)
    blocks, index = [], 0
    for p, count in enumerate(counts):
        pid = f'CL0-P{p}'
        first = index
        rows = []
        for c in range(count):
            i, s = POINTS[index] if index < len(POINTS) else (.2, .1)
            empty = index == sum(counts)-1
            star = index in (2, 5)
            rows.append(dict(context_id=f'{pid}-C{c}', context_name=f'냉방 상황 {p+1}-{c+1}',
                action='예약 운전으로 실내 온도를 조절한다',
                situation=dict(state='실내에서 냉방을 사용함', emotion='전기료가 걱정됨', barrier='조절이 번거로움'),
                situation_origin='dims', dominant_constraint='전기료 부담', keywords=['냉방', '예약'],
                metrics={**_metrics(i, s), 'quality': dict(cohesion=.8, boundary=.1, stability=.9, npmi=.4)},
                evidence=[] if empty else [_evidence(index, novelty='high' if star else 'low'),
                    _evidence(index, 1, novelty='very_high' if star else 'low', verified=index % 2 == 0)],
                counter_evidence=[] if empty else [_evidence(index, 2, role='counter')],
                rare_evidence=[] if empty else [{**_evidence(index, 3, role='rare'), 'dist_centroid': .8, 'combo_rarity': .9}],
                flags=['counter_context'] if index == 3 else []))
            index += 1
        importance = sum(c['metrics']['importance'] for c in rows)/count
        satisfaction = sum(c['metrics']['satisfaction'] for c in rows)/count
        blocks.append(dict(persona_evidence=dict(cluster_id='CL0', persona_id=pid,
            persona_name=f'쾌적한 냉방 사용자 {p+1}' + (' [QA-P6:invalid-card]' if p == qa_failed_persona else ''), desire=f'편안한 실내 생활을 원한다 {p+1}',
            goal=['쾌적한 온도 유지', '전기료 절약'], desire_support=[_evidence(first)],
            artifacts=[dict(name='에어컨', mention_count=count)],
            metrics=_metrics(importance, satisfaction, count * DOCS_PER_CONTEXT),
            quality=dict(cohesion=.8, boundary=.1, stability_ari=.9)), context_evidence=rows))
    from app.evidence import params
    used_params = json.loads(json.dumps({name: getattr(params, name) for name in vars(params) if name.isupper()}))
    return dict(schema='evidence-package/1', version='v1', params=used_params, personas=blocks)


def write_session_with_package(local_data_dir, **kw):
    """Write synthetic prep data, confirmed stage-six rows, then the file contract.

    Segmentation is planted from the synthetic helper's known assignments;
    no clustering, stage-seven service, network or language model is invoked.
    Existing identical synthetic sessions are rejected by make_segment_session.
    """
    package = make_package(**kw)
    blocks = package['personas']
    counts = tuple(len(b['context_evidence']) for b in blocks)
    base = Path(local_data_dir).resolve()
    session = make_segment_session(base, clusters=1, personas=(len(blocks),), contexts=counts,
                                   docs_per_context=DOCS_PER_CONTEXT, seed=kw.get('seed', 42))
    directory = base / 'sessions' / session.sid / 'versions' / session.version
    store = SegmentStore(directory)
    store.write_layers(clusters=[dict(cluster_id='CL0', name_draft='실내 냉방')],
        personas=[dict(persona_id=b['persona_evidence']['persona_id'], cluster_id='CL0') for b in blocks],
        contexts=[dict(context_id=c['context_id'], persona_id=b['persona_evidence']['persona_id'],
                       flags=c['flags'], keywords=c['keywords']) for b in blocks for c in b['context_evidence']],
        docs=[dict(doc_id=doc, cluster_id=a['cluster'], persona_id=a['persona'], context_id=a['context'],
                   author_hash=hashlib.sha256(f'author-{int(doc[1:]) // 2}'.encode()).hexdigest())
              for doc, a in session.expected['assignments'].items()])
    store.confirm('clusters', 'CL0', {'name': '실내 냉방'})
    for b in blocks:
        p = b['persona_evidence']
        confirmed = store.confirm('personas', p['persona_id'],
                                  dict(name=p['persona_name'], desire=p['desire'], goals=p['goal']))
        p.update(persona_name=confirmed['name'], desire=confirmed['desire'], goal=confirmed['goals'])
        confirmed_contexts = store.confirm_contexts(p['persona_id'],
            [dict(id=c['context_id'], name=c['context_name'], action=c['action']) for c in b['context_evidence']])
        for c, confirmed in zip(b['context_evidence'], confirmed_contexts):
            c.update(context_name=confirmed['name'], action=confirmed['action'])
    store.set_run(f'fake-segment-{kw.get("seed", 42)}')
    # The synthetic helper plants assignments without running segmentation.
    # Supply its missing centroid outputs for downstream insight radar reads.
    contexts = [c for b in blocks for c in b['context_evidence']]
    with patch.object(settings, 'embed_dim', 1024):
        centroids = FakeEmbedder().embed([c['context_name'] for c in contexts])
    with sqlite3.connect(directory / 'segment/segment.sqlite') as db:
        db.executemany('UPDATE contexts SET centroid=? WHERE context_id=?',
                       [(vector.tobytes(), c['context_id'])
                        for c, vector in zip(contexts, centroids)])
    with patch.multiple(settings, local_data_dir=str(base), storage='local'), \
            patch.multiple(s3, _USE_LOCAL=True, _DATA_DIR=base):
        sessions.update_session(session.sid, dict(bk='LG 에어컨', projectContext=deepcopy(PROJECT_CONTEXT),
            segment=dict(status='done', run=store.get_run(), savedAt=sessions.now()),
            evidence=dict(status='done', run=f'fake-evidence-{kw.get("seed", 42)}', savedAt=sessions.now()),
            completion=dict(segmentDone=True)))
        sessions.write_json(directory / 'evidence/package.json', package)
    return session


def _responses(package, block, selected=None, concept_edit=False):
    refs = evidence_index(block)
    rows = block.context_evidence if selected is None else [c for c in block.context_evidence if c.context_id in selected]
    cards = []
    for c in rows:
        cites = [key for key, ref in refs.items() if ref.context_id == c.context_id and ref.role == 'support']
        cards.append(dict(context_id=c.context_id, **{field: dict(text=getattr(c.situation, field) if cites else None, cite=cites[:1])
                                                      for field in ('state', 'emotion', 'barrier')}))
    cids = [c.context_id for c in block.context_evidence]
    cite = list(refs)[:1]
    violation = block.persona_evidence.persona_id == package.personas[0].persona_evidence.persona_id
    check = [dict(constraint=CONSTRAINT, verdict='violates' if violation else 'ok',
                  reason='의료적 효과를 단정함' if violation else '의료적 효과를 표현하지 않음')]
    # Prefer the first Persona's Contexts so concept citations have one namespace.
    all_ids = [c.context_id for b in package.personas for c in b.context_evidence]
    items = [dict(id=f'I{n+1}', title=f'냉방 조절 경험 개선 {n+1}', pain_point='냉방을 조절할 때 번거로움을 겪는다.',
                  context_ids=[all_ids[n % len(all_ids)]], known_ki_id=None) for n in range(3)]
    concept = dict(persona_profile='편안한 실내 생활을 원하는 합성 사용자',
        pain_points=list(refs)[:3], journey=[dict(context_id=cids[0], action='온도를 조절한다',
            feeling='번거롭다', service='예약 조절 안내', service_action='예약 방법을 안내한다', cx_4d='시스템')],
        constraint_check=check)
    return {
        'persona.card': dict(contexts=cards),
        'persona.summary': dict(intent=dict(text='쾌적한 생활을 원한다', basis_context_ids=cids,
            reserved_context_ids=[c.context_id for c in block.context_evidence if 'counter_context' in c.flags]),
            usage_context=dict(text='실내 냉방 사용', cite=cite), jtbd=dict(text='편안하게 쉬기', cite=cite),
            journey=dict(pre_purchase=None, purchase=None, post_purchase=None),
            sensitivity=dict(price='상', brand='중', feature='상'), values=None, decision_style=None),
        'persona.prescribe': dict(direction='에어컨으로 질병을 치료한다고 안내한다' if violation else '예약 조절을 안내한다',
            target_metric='사용 만족도', contribution='조절 부담을 줄인다',
            journey_hypothesis='ENTRY 예약 안내 → EXPAND 사용 적응 → COMMIT 지속 사용'),
        'persona.constraint_check': dict(constraints=check),
        'persona.scope': dict(verdict='in', reason='가정용 냉방 사용 맥락에 해당함'),
        'insight.derive': dict(items=items), 'insight.concept': concept,
        'insight.edit': concept if concept_edit else dict(items=items),
    }


def fake_persona_backend(package):
    """FakeBackend responses bound to actual package IDs and Persona-wide E refs.

    Defaults to the first Persona (the deliberate constraint violation). For
    another Persona/chunk, supply JSON attachments with persona_id/context_ids
    or a persona_evidence/context_evidence block. insight.edit accepts a JSON
    attachment with target='concept:<id>' for the concept response shape.
    Output wrappers are contexts/items/constraints; later task schemas own the
    production validation. No calculated metrics or source quotes are emitted.
    """
    package = Package.model_validate(package) if isinstance(package, dict) else package

    class PersonaFakeBackend(FakeBackend):
        def run(self, task):
            selected, pid, concept_edit = None, None, False

            def inspect(value):
                nonlocal selected, pid, concept_edit
                if isinstance(value, dict):
                    if 'persona_id' in value:
                        pid = value['persona_id']
                    if 'context_ids' in value:
                        selected = value['context_ids']
                    if 'context_evidence' in value:
                        selected = [c['context_id'] for c in value['context_evidence']]
                    if str(value.get('target', '')).startswith('concept:'):
                        concept_edit = True
                    for child in value.values():
                        inspect(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child)

            for attachment in task.attachments:
                try:
                    inspect(json.loads(attachment.body))
                except ValueError:
                    continue
            block = next((b for b in package.personas if b.persona_evidence.persona_id == pid), package.personas[0])
            responses = _responses(package, block, selected, concept_edit)
            return FakeBackend(responses={name: json.dumps(value, ensure_ascii=False)
                                          for name, value in responses.items()}).run(task)

    return PersonaFakeBackend(responses={name: json.dumps(value, ensure_ascii=False)
        for name, value in _responses(package, package.personas[0]).items()})
