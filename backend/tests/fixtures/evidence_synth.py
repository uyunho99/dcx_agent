"""Offline stage-seven inputs and deterministic evidence LLM responses.

QueryEmbedder(session, VectorStore(prepared_root(...))) uses the fixture's
original vocabulary assignments, independent of stage-six ID renumbering.
Pass the requested document batch as a doc_id -> prepared-document mapping to
fake_evidence_backend; its responses contain exactly those document IDs.
"""
import hashlib
import json
from pathlib import Path
import re
from unittest.mock import patch

import numpy as np

from app.config import settings
from app.llm import registry
from app.llm.fake import FakeBackend
from app.segment import pipeline
from app.segment.store import SegmentStore
from app.services import s3
from tests.fixtures.segment_synth import SynthSession, fake_dims_backend, make_segment_session
from tests.test_integration_stage3_5 import Context

QUERY_DIMS = ('Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome', 'Counter', 'Residual')
FORBIDDEN = r'페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은'


class _SegmentBackend:
    def run(self, task):
        return fake_dims_backend([attachment.title for attachment in task.attachments]).run(task)


def make_evidence_session(local_data_dir, **segment_kwargs) -> SynthSession:
    """Create stage five, run real stage six offline, and confirm every layer.

    All segment fixture options (including qa and seed) pass through unchanged.
    Application settings and fake backend bindings are restored on return.
    """
    base = Path(local_data_dir).resolve()
    with patch.multiple(settings, local_data_dir=str(base), storage='local',
                        embed_backend='fake', llm_backend='fake', embed_dim=1024), \
            patch.multiple(s3, _USE_LOCAL=True, _DATA_DIR=base), \
            patch.object(registry, 'get_backend', return_value=_SegmentBackend()):
        fixture = make_segment_session(base, **segment_kwargs)
        pipeline.run(Context(fixture.sid, fixture.version))
        store = SegmentStore.open(fixture.sid, fixture.version)
        for layer, key in [('clusters', 'cluster_id'), ('personas', 'persona_id'),
                           ('contexts', 'context_id')]:
            for row in getattr(store, layer)():
                values = {'name': row['name_draft'] or f"{row[key].split('-')[0]} 이름"}
                if layer == 'personas':
                    values.update(desire=row['desire_draft'], goals=row['goals_draft'])
                elif layer == 'contexts':
                    values['action'] = row['action_draft']
                store.confirm(layer, row[key], values)
        if not pipeline.mark_done_if_complete(fixture.sid, fixture.version):
            raise RuntimeError('Synthetic stage six did not produce confirmable contexts')
    return fixture


class QueryEmbedder:
    """Normalized fixture centroids for matching words; SHA-256 seeded fallback.

    Context vocabulary takes precedence over persona vocabulary. Multiple hits
    in a layer average its matched directions. Zero/no-token documents are
    excluded just as they are in stage six. input_type is accepted for parity
    with the production embedder but does not change deterministic results.
    """
    name = 'fake'
    model = 'evidence-synth'

    def __init__(self, session: SynthSession, vectors):
        expected = session.expected
        excluded = set(expected['zero_vector_ids']) | set(expected['no_token_ids'])
        ids, values = vectors.get([i for i in expected['assignments'] if i not in excluded])
        self.dim = values.shape[1]
        self._layers = []
        for layer, vocabulary in [('context', 'context_tokens'), ('persona', 'persona_nouns')]:
            groups = {}
            for doc_id, vector in zip(ids, values):
                if np.linalg.norm(vector) > 0:
                    groups.setdefault(expected['assignments'][doc_id][layer], []).append(vector)
            matches = []
            for owner, words in expected[vocabulary].items():
                if owner not in groups:
                    continue
                center = np.mean(groups[owner], axis=0)
                direction = center / np.linalg.norm(center)
                pattern = re.compile(r'(?<![A-Za-z0-9_-])(?:' + '|'.join(map(re.escape, words))
                                     + r')(?![A-Za-z0-9_-])')
                matches.append((pattern, direction))
            self._layers.append(matches)

    def embed(self, texts, input_type='document') -> np.ndarray:
        result = np.empty((len(texts), self.dim), dtype=np.float32)
        for index, text in enumerate(texts):
            for layer in self._layers:
                matches = [direction for pattern, direction in layer if pattern.search(text)]
                if matches:
                    vector = np.mean(matches, axis=0)
                    break
            else:
                seed = int.from_bytes(hashlib.sha256(text.encode('utf-8')).digest(), 'big')
                vector = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            result[index] = vector / np.linalg.norm(vector)
        return result


def _quote(doc):
    """Copy the first sentence, retaining exact whitespace inside the sentence."""
    fields = [('body', None, doc.get('body')), ('title', None, doc.get('title'))]
    fields.extend(('comment', idx, comment.get('text'))
                  for idx, comment in enumerate(doc.get('comments') or []))
    for field, idx, text in fields:
        if text and text.strip():
            sentence = re.split(r'(?<=[.!?。！？])\s+|\n', text.strip(), maxsplit=1)[0]
            return dict(field=field, idx=idx, text=sentence)
    raise ValueError('A fake tagged document must contain text to quote')


def fake_evidence_backend(contexts, docs=None) -> FakeBackend:
    """Build valid responses with real IDs, without JSON template substitution.

    contexts is a list of SegmentStore context rows; docs is the requested batch
    mapping IDs to original documents. Omit docs for query-only tests. Construct
    a backend for each requested batch when testing tagging/novelty batching.
    """
    docs = {} if docs is None else docs
    context_queries = {}
    endings = ('감각을 살펴봤어요.', '마음이 편해지고 싶어요.', '차이를 알고 싶어요.',
               '직접 조절했어요.', '가족과 함께 이야기했어요.', '원하는 결과를 얻고 싶어요.',
               '기대와 달라 불편했어요.', '다른 방법도 시도하고 싶어요.')
    for context in contexts:
        keywords = ' '.join(context.get('keywords') or [])
        topic = re.sub(FORBIDDEN, '', keywords).strip() or '예약 냉방'
        context_queries[context['context_id']] = {
            dim: f'나는 {topic} {ending}' for dim, ending in zip(QUERY_DIMS, endings)}
    queries = dict(persona_query=dict(
        desire_check=['나는 전기료 부담 없이 시원하게 지내고 싶어요.', '나는 편안하게 쉬고 싶어요.'],
        artifact=['나는 리모컨으로 예약 시간을 설정했어요.']),
        context_queries=context_queries, anchor_context_ids=list(context_queries))
    tags, novelty = [], []
    for doc_id, doc in docs.items():
        quote = _quote(doc)
        has_dims = bool(doc.get('context_dims'))
        core = doc.get('evidence_level', doc.get('evidence_level_pred', 'core')) == 'core'
        tags.append(dict(doc_id=doc_id, relevant=True, reason_code=None, polarity=-0.2,
            pain_point=dict(text=quote['text'], quote=quote['text']),
            unmet_need='편안하게 쉬고 싶어요.',
            situation=None if has_dims else dict(state='여름 실내', emotion='더위 걱정', barrier='전기료 부담'),
            context_dims=None if has_dims or not core else dict(environment='여름 실내', internal_state='더위 걱정',
                              task_goal='편안한 휴식', activity_response='예약 운전',
                              resource_constraint='전기료 부담'),
            artifacts=[], known_match='none', quotes=[quote]))
        novelty.append(dict(doc_id=doc_id, novelty='high', reason='예약 운전의 새로운 경험을 담고 있어요.'))
    return FakeBackend(responses={
        'evidence.queries': json.dumps(queries, ensure_ascii=False),
        'evidence.tag': json.dumps({'items': tags}, ensure_ascii=False),
        'evidence.novelty': json.dumps({'items': novelty}, ensure_ascii=False),
    })
