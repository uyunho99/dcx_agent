"""Deterministic stage-five sessions for all stage-six backend tests.

``expected`` contains assignments keyed by doc_id, persona_nouns and
context_tokens keyed by layer ID, plus zero_vector_ids and no_token_ids.
The three exclusion cases are included in (not added to) the requested count.
Settings are restored on return; consumers use conftest's data_dir fixture.
"""
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.config import settings
from app.context import store
from app.crawl.queue import CrawlQueue
from app.label import rule
from app.llm.fake import FakeBackend
from app.prep import pipeline
from app.services import s3
from app.vectors.embedder import FakeEmbedder
from tests.test_integration_stage3_5 import Context, fixed_tags

PERSONAS = (2, 3, 2, 3, 2)
CONTEXTS = (2, 3, 2, 2, 3, 2, 2, 3, 2, 2, 2, 3)
CHANNELS = ('naver_cafe', 'naver_blog', 'youtube', 'ppomppu', 'clien')
NOUNS = ('냉방', '절전', '소음', '필터', '청소', '설치', '습도', '바람', '전기료', '실외기')
TOKENS = ('취침', '예약', '온도', '조절', '거실', '환기', '리모컨', '쾌적')


@dataclass(frozen=True)
class SynthSession:
    sid: str
    version: str
    expected: dict


def fake_dims_backend(doc_ids):
    """Bind the fixed dims example to every ID in an arbitrary LLM batch."""
    responses = {f'segment.{name}': (FakeBackend.fixture_dir / f'segment.{name}.json').read_text(encoding='utf-8')
                 for name in ('dims', 'cluster_name', 'persona_draft', 'context_draft')}
    template = json.loads(responses['segment.dims'])['items'][0]
    responses['segment.dims'] = json.dumps(
        {'items': [{**template, 'doc_id': doc_id} for doc_id in doc_ids]}, ensure_ascii=False)
    return FakeBackend(responses=responses)


def make_segment_session(local_data_dir, *, clusters=5, personas=PERSONAS,
                         contexts=CONTEXTS, docs_per_context=40, seed=42, qa=False):
    """Create one isolated session using the integration test's prep workflow.

    Pass one persona count per cluster and one context count per persona.
    Gaussian vectors use orthogonal cluster directions (length 3), persona
    offsets (length .5), and independent noise with sigma .05, then normalize.
    qa=True makes 1,200 documents: one eight-topic Persona with a 16-document
    negative topic (<15% of its retained documents), plus nine three-topic Personas.
    Repeated identical calls in the same data directory are rejected.
    """
    if qa:
        clusters, personas, contexts, docs_per_context = 5, (2,) * 5, (8,) + (3,) * 9, 40
    personas, contexts = tuple(personas), tuple(contexts)
    if (clusters < 1 or len(personas) != clusters or any(n < 1 for n in personas)
            or len(contexts) != sum(personas) or any(n < 1 for n in contexts)
            or docs_per_context < 1 or sum(contexts) * docs_per_context < 3
            or clusters + sum(personas) > 1024):
        raise ValueError('Expected positive, matching layer counts and at least three documents')
    config = dict(clusters=clusters, personas=personas, contexts=contexts,
                  docs_per_context=docs_per_context, seed=seed)
    if qa:
        config['qa'] = True
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    sid, version = f'segment-synth-{digest}', 'v1'
    base = Path(local_data_dir).resolve()
    if (base / 'sessions' / sid).exists():
        raise FileExistsError(f'Synthetic session already exists: {sid}')
    rng = np.random.default_rng(seed)
    basis, _ = np.linalg.qr(rng.normal(size=(1024, clusters + sum(personas))))
    expected = dict(k=clusters, assignments={}, persona_nouns={}, context_tokens={},
                    zero_vector_ids=[], no_token_ids=[])
    docs, tokens, vectors = [], [], []
    persona_index = 0
    for cluster_index, count in enumerate(personas):
        cluster_id = f'CL{cluster_index}'
        for p in range(count):
            persona_id = f'{cluster_id}-P{p}'
            nouns = [f'{word}_{persona_id}' for word in NOUNS]
            expected['persona_nouns'][persona_id] = nouns
            for c in range(contexts[persona_index]):
                context_id = f'{persona_id}-C{c}'
                words = [f'{word}_{context_id}' for word in TOKENS]
                expected['context_tokens'][context_id] = words
                count = (8 if c == 0 else 16) if qa and persona_index == 0 else docs_per_context
                negative = qa and persona_index == 0 and c == 1
                for _ in range(count):
                    index = len(docs)
                    doc_id = f'd{index:06d}'
                    expected['assignments'][doc_id] = dict(cluster=cluster_id, persona=persona_id, context=context_id)
                    author = hashlib.sha256(f'author-{index // 2}'.encode()).hexdigest()
                    docs.append(dict(doc_id=doc_id, title=f'LG 휘센 에어컨 사용 경험 {doc_id}',
                        body='LG 에어컨을 사용하며 냉방과 전기료를 살펴봤습니다. ' + ' '.join(nouns + words) + (' 짜증 불편 실망' if negative else ''),
                        comments=[dict(text='에어컨 예약 운전으로 편안하게 쉬고 싶어요.', author_hash=author)],
                        source=CHANNELS[index % len(CHANNELS)], author_hash=author,
                        date=(date(2026, 6, 1) + timedelta(days=index % 90)).isoformat()))
                    tokens.append(nouns + words + (['짜증', '불편', '실망'] if negative else []))
                    vector = (3 * basis[:, cluster_index] + .5 * basis[:, clusters + persona_index]
                              + rng.normal(0, .05, 1024))
                    vectors.append(vector / np.linalg.norm(vector))
            persona_index += 1
    matrix = np.asarray(vectors, dtype=np.float32)
    matrix[:2] = 0
    tokens[2] = []
    expected['zero_vector_ids'] = [d['doc_id'] for d in docs[:2]]
    expected['no_token_ids'] = [docs[2]['doc_id']]
    expected['documents'] = len(docs)
    # Match conftest.data_dir's local-storage overrides without leaking globals.
    with patch.multiple(settings, local_data_dir=str(base), storage='local',
                        embed_backend='fake', llm_backend='fake', embed_dim=1024), \
            patch.multiple(s3, _USE_LOCAL=True, _DATA_DIR=base):
        source = base / 'crawl' / sid / 'collections/c1'
        store.write_json(source / 'manifest.json', {'parent': None})
        with closing(CrawlQueue(source / 'queue.sqlite')) as queue:
            queue.finish_run(queue.register_run('detail'), 'done')
        pipeline._jsonl(source / 'docs/shard-0001.jsonl', docs)
        store.update_session(sid, {'schemaVersion': 2, 'collectionId': 'c1',
            'prep': {'config': {'embedder': 'fake', 'tokenPos': ['NNG', 'NNP'], 'boilerplate': {}}}})
        embedder = FakeEmbedder()
        by_text = {pipeline._text(doc)[:2000]: matrix[i] for i, doc in enumerate(docs)}
        with patch.object(pipeline, 'get_embedder', return_value=embedder), \
                patch.object(embedder, 'embed', side_effect=lambda texts: np.asarray([by_text[t] for t in texts])), \
                patch.object(pipeline, 'tokenize', side_effect=tokens):
            pipeline.run_prep(Context(sid), sid, version)
        _write_export(base, sid, version, docs)
    return SynthSession(sid, version, expected)


def _write_export(base, sid, version, docs):
    """Mirror model.export's label-origin projection without running judges."""
    rows = []
    for i, doc in enumerate(docs):
        level = 'supporting' if i % 4 == 0 else 'core'
        tags = fixed_tags(level)
        rows.append({**doc, 'desc': doc['body'], 'cafe': '', 'kw': '',
            'source': 'agreed', 'evidence_level_pred': level,
            'tagProbs': dict(anchor=float(tags['anchor']), situation=float(tags['situation']),
                             **{key: float(value) for key, value in tags['sem'].items()}),
            'confidence': 1., 'pred_entropy': 0., 'relevance_score': 1.,
            'signal': tags['signal'], 'rule_version': rule.RULE_VERSION, 'modelId': None})
    export_base = f'classified/{sid}/{version}/gen-synth'
    for name in ('all', 'relevant'):
        pipeline._jsonl(base / export_base / f'{name}.jsonl', rows)
    stage5 = dict(model=None, mode='llm', accepted=len(rows), escalated=0,
                  levelDistribution={level: sum(r['evidence_level_pred'] == level for r in rows) / len(rows)
                                     for level in ('core', 'supporting', 'non')})
    store.write_json(base / export_base / 'stage_5.json', stage5)
    store.write_json(store.session_dir(sid) / 'stage_5.json', stage5)
    store.update_session(sid, {'labeling': {'status': 'done'}, 'training': {'inferStatus': 'done',
        'exportRef': export_base + '/relevant.jsonl', 'allRef': export_base + '/all.jsonl',
        'stage5Ref': export_base + '/stage_5.json', 'exportedAt': '2026-09-01T00:00:00+00:00'}})
