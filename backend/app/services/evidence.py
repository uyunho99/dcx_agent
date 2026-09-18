"""STEP 09 evidence packages. Retrieval requires the T4 scoped search contract."""
from copy import deepcopy
from datetime import datetime, timezone
import logging
import math

from app.jobs.manager import job_manager
from app.services import pinecone_svc, s3

logger = logging.getLogger(__name__)
DIMENSIONS = ('Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome')
alpha_known_penalty = 0.50
beta_rarity_bonus = 0.30
coverage_min = 4 / 6
FILTER_KEYS = ('cluster_id', 'persona_id', 'context_id')


class RetrievalUnavailable(RuntimeError):
    """No trustworthy retrieval result; callers must not return empty success."""


def quality_score(relevance, known, rarity, has_known):
    """Use the golden/detail-contract multiplicative adjustment, without clamping.

    Scaling both adjustments by relevance keeps irrelevant material from receiving
    an additive rarity-only score. Empty known input disables BOTH adjustments:
    QA-EDGE-002 takes precedence over the usual rarity bonus, but rarity is kept.
    """
    return (relevance * (1 - alpha_known_penalty * known) * (1 + beta_rarity_bonus * rarity)
            if has_known else relevance)


def scoped_search(sid, query, filters, top_k=50):
    if any(not isinstance(filters.get(k), str) or not filters[k].strip() for k in FILTER_KEYS):
        raise ValueError('cluster_id, persona_id and context_id are required')
    try:
        # T4 integration boundary: never fall back to the legacy unfiltered call.
        rows = pinecone_svc.search_similar(sid, query, top_k=top_k, filters=filters)
    except Exception as exc:
        raise RetrievalUnavailable('Evidence search unavailable; STEP 05 재실행 필요') from exc
    if not isinstance(rows, list) or any(
        any(row.get(k) != filters[k] for k in FILTER_KEYS) for row in rows
    ):
        raise RetrievalUnavailable('Pinecone returned invalid scope; STEP 05 재실행 필요')
    return rows


def supplement_search(sid, persona, actions, missing_dims):
    """One bounded, dimension-targeted retrieval pass in each original scope."""
    rows = []
    for action in actions:
        filters = dict(cluster_id=persona['cluster_id'], persona_id=persona['persona_id'],
                       context_id=action['context_id'])
        rows.extend(scoped_search(sid, action['sentence'] + ' ' + ' '.join(missing_dims), filters))
    return rows


def _unit(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'{name} must be finite and in [0, 1]')
    return value


def _text(record):
    return record.get('text') or record.get('body') or record.get('desc') or ''


def centroid_sentence(persona, cluster, records):
    by_id = {r['doc_id']: r for r in records}
    members = [d for d in cluster['documents'] if d['doc_id'] in persona['doc_ids']]
    if not members:
        raise ValueError('Persona has no cluster documents')
    closest = min(members, key=lambda d: (d['dist_centroid'], d['doc_id']))
    return dict(doc_id=closest['doc_id'], text=_text(by_id[closest['doc_id']]),
                dist_centroid=closest['dist_centroid'])


def _rank(rows, sort_by):
    if sort_by not in ('quality', 'relevance'):
        raise ValueError('sort_by must be quality or relevance')
    for metric in ('relevance', 'quality'):
        for rank, row in enumerate(sorted(rows, key=lambda r: (-r[metric], r['doc_id'])), 1):
            row[f'{metric}_rank'] = row[f'rank_{metric}'] = rank
    return sorted(rows, key=lambda r: (r[f'{sort_by}_rank']))


def build_package(*, sid, persona, cluster, records, actions, known_insights,
                  sort_by='quality', query=None):
    """Build from v2 persona, 07 membership, 06 text, and scoped T4 hits.

    T4 hits supply max_sim_to_known and combo_rarity (not the 06 classifier
    score). No missing metric is silently fabricated when known insights exist.
    """
    if persona['cluster_id'] != cluster['cluster_id']:
        raise ValueError('Persona/cluster mismatch')
    centroid = centroid_sentence(persona, cluster, records)
    actions = deepcopy(actions)
    contexts = {a['context_id']: a for a in actions}
    if not actions or len(contexts) != len(actions):
        raise ValueError('Unique Action contexts are required')
    members = {d['doc_id']: d for d in cluster['documents']}
    allowed = set(persona['doc_ids']) & members.keys()
    warnings = []
    if not known_insights:
        warnings.append('KNOWN_INSIGHTS_EMPTY')
        logger.warning('KNOWN_INSIGHTS_EMPTY sid=%s persona=%s: quality == relevance', sid, persona['persona_id'])
    merged = {}

    def merge(hits):
        for hit in hits:
            if (hit.get('cluster_id') != persona['cluster_id'] or
                    hit.get('persona_id') != persona['persona_id'] or hit.get('context_id') not in contexts):
                raise RetrievalUnavailable('Invalid evidence scope; STEP 05 재실행 필요')
            doc_id = hit['doc_id']
            if doc_id not in allowed:
                raise RetrievalUnavailable('Document outside persona membership; STEP 05 재실행 필요')
            quote = hit.get('quote') or _text(hit)
            if not quote:
                raise ValueError(f'Missing quote: {doc_id}')
            if doc_id == centroid['doc_id'] or quote.strip() == centroid['text'].strip():
                continue
            action = contexts[hit['context_id']]
            relevance = _unit(hit.get('score', hit.get('relevance')), 'relevance')
            known = _unit(hit['max_sim_to_known'], 'known') if known_insights else 0.0
            rarity = _unit(hit['combo_rarity'], 'rarity')
            dims = hit['dims']
            if not isinstance(dims, list) or any(d not in DIMENSIONS for d in dims):
                raise ValueError('Invalid experience dimensions')
            role = hit.get('role', 'support')
            if role not in ('support', 'refute'):
                raise ValueError('Invalid evidence role')
            row = dict(doc_id=doc_id, quote=quote, cluster_id=persona['cluster_id'],
                       persona_id=persona['persona_id'], context_id=action['context_id'],
                       action_id=action['action_id'], role=role, relevance=relevance,
                       known=known, max_sim_to_known=known, rarity=rarity, combo_rarity=rarity,
                       quality=quality_score(relevance, known, rarity, bool(known_insights)),
                       dims=list(dict.fromkeys(dims)), band=members[doc_id]['band'], source='auto')
            # Repeated hits refresh dimensions but never duplicate ranks or citations.
            if doc_id in merged:
                previous = merged[doc_id]
                row['dims'] = sorted(set(row['dims']) | set(previous['dims']))
                if previous['relevance'] > row['relevance']:
                    row = dict(previous, dims=row['dims'])
            merged[doc_id] = row

    for action in actions:
        filters = dict(cluster_id=persona['cluster_id'], persona_id=persona['persona_id'],
                       context_id=action['context_id'])
        merge(scoped_search(sid, query or action['sentence'], filters))
    dims = {d for row in merged.values() for d in row['dims']}
    if len(dims) / len(DIMENSIONS) < coverage_min:
        merge(supplement_search(sid, persona, actions, sorted(set(DIMENSIONS) - dims)))
        dims = {d for row in merged.values() for d in row['dims']}
        if len(dims) / len(DIMENSIONS) < coverage_min:
            warnings.append('COVERAGE_BELOW_MIN')
    for action in actions:
        action['doc_ids'] = sorted(r['doc_id'] for r in merged.values() if r['action_id'] == action['action_id'])
        action['docs'] = len(action['doc_ids'])
    return dict(sid=sid, timestamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'),
                persona_id=persona['persona_id'], cluster_id=persona['cluster_id'], actions=actions,
                centroid_sentence=centroid, evidence=_rank(list(merged.values()), sort_by),
                coverage={'dims': sorted(dims), 'min': math.ceil(coverage_min * len(DIMENSIONS))},
                warnings=warnings)


def derive_actions(persona, cluster, records):
    """Deterministic LDA topic grouping with extractive Action sentences.

    No synthetic LLM claim is introduced: each sentence is the highest topic
    weight source text. Context IDs are stable for sorted source IDs and seed 42.
    These scopes must be attached to T4 metadata before scoped retrieval.
    """
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import CountVectorizer

    centroid = centroid_sentence(persona, cluster, records)
    docs = sorted((r for r in records if r['doc_id'] in persona['doc_ids']
                   and r['doc_id'] != centroid['doc_id'] and _text(r).strip() != centroid['text'].strip()),
                  key=lambda r: r['doc_id'])
    if not docs:
        raise ValueError('No non-centroid documents for Actions')
    matrix = CountVectorizer(token_pattern=r'(?u)\b\w+\b').fit_transform([_text(r) for r in docs])
    weights = LatentDirichletAllocation(n_components=min(3, len(docs)), random_state=42,
                                        learning_method='batch').fit_transform(matrix)
    groups = {}
    for record, vector in zip(docs, weights):
        topic = int(vector.argmax())
        groups.setdefault(topic, []).append((record, float(vector[topic])))
    result = []
    for i, (topic, group) in enumerate(sorted(groups.items()), 1):
        representative = min(group, key=lambda item: (-item[1], item[0]['doc_id']))[0]
        result.append(dict(action_id=f"{persona['persona_id']}-A{i}", context_id=f"{persona['persona_id']}-C{i}",
                           sentence=_text(representative), lda_topic=topic, topic_weight=len(group) / len(docs),
                           docs=len(group), doc_ids=[r['doc_id'] for r, _ in group]))
    return result


def _latest(prefix):
    keys = sorted(o['Key'] for o in s3.list_objects(prefix.rsplit('/', 1)[0] + '/') if o['Key'].startswith(prefix) and o['Key'].endswith('.json'))
    if not keys:
        raise FileNotFoundError(prefix)
    result = s3.load_json(keys[-1])
    if result is None:
        raise FileNotFoundError(keys[-1])
    return result


def load_inputs(sid, persona_id):
    session = s3.load_json(f'sessions/{sid}/session.json')
    if session is None:
        raise FileNotFoundError('Session not found')
    personas = _latest(f'personas/{sid}/result_')['personas']
    persona = next((p for p in personas if p.get('persona_id') == persona_id), None)
    if persona is None:
        raise FileNotFoundError('v2 persona not found')
    clusters = _latest(f'clusters/{sid}/result_')['clusters']
    cluster = next((c for c in clusters if c['cluster_id'] == persona['cluster_id']), None)
    if cluster is None:
        raise FileNotFoundError('Cluster not found')
    # load_data accepts a file key; select only the latest relevant run, not sidecars.
    prefix = f'classified/{sid}/relevant_'
    keys = sorted(o['Key'] for o in s3.list_objects(f'classified/{sid}/')
                  if o['Key'].startswith(prefix) and o['Key'].endswith('.jsonl'))
    if not keys:
        raise FileNotFoundError('Classified documents not found')
    # Local load_data reads the directory: explicitly select the intended JSONL.
    if s3._USE_LOCAL:
        import json
        records = [json.loads(line) for line in s3._local_path(keys[-1]).read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        records = s3.load_data(keys[-1])
    return dict(sid=sid, persona=persona, cluster=cluster, records=records,
                known_insights=session.get('known_insights', []))


def collect(sid, persona_id):
    inputs = load_inputs(sid, persona_id)
    actions = derive_actions(inputs['persona'], inputs['cluster'], inputs['records'])
    result = build_package(**inputs, actions=actions)
    key = f"evidence/{sid}/{persona_id}_{result['timestamp']}.json"
    s3.save_json(key, result)
    return key


def get_package(sid, persona_id, sort_by='quality'):
    package = _latest(f'evidence/{sid}/{persona_id}_')
    package['evidence'] = _rank(package['evidence'], sort_by)
    return package


def search(sid, query, filters, sort_by='quality'):
    inputs = load_inputs(sid, filters['persona_id'])
    if inputs['persona']['cluster_id'] != filters['cluster_id']:
        raise ValueError('Cluster does not match persona')
    package = get_package(sid, filters['persona_id'])
    actions = [a for a in package['actions'] if a['context_id'] == filters['context_id']]
    if not actions:
        raise ValueError('Context does not belong to persona')
    return build_package(**inputs, actions=actions, sort_by=sort_by, query=query)


def job_key(sid, persona_id):
    return f'evidence:{sid}:{persona_id}'


def run_collect(sid, persona_id):
    key = job_key(sid, persona_id)
    try:
        job_manager.update('persona', key, phase='collect', progress=10)
        artifact = collect(sid, persona_id)
        job_manager.update('persona', key, status='done', progress=100, phase='done', key=artifact)
    except Exception as exc:
        logger.exception('Evidence collection failed')
        job_manager.update('persona', key, status='error', phase='error', error=str(exc))
