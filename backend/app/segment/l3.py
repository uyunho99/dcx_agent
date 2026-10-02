"""Per-Persona LDA Contexts and geometry in the supplied Voyage space."""
from dataclasses import dataclass, field

import numpy as np
from gensim.corpora import Dictionary
from gensim.models import CoherenceModel, LdaModel

from app.segment import params


@dataclass
class ContextResult:
    """Context IDs are local C1.., in surviving LDA topic order.

    theta_all retains the *full* original posterior, including unused topics,
    so theta remains the original maximum probability. topic_ids maps its
    columns to Context IDs (None for topics with no hard assignments).
    flags contains aggregate warnings; context_flags identifies counter
    Contexts. Missing sentiment observations are excluded from both means.
    scan.perplexity is 2 ** (-gensim's per-word log perplexity bound).
    """
    assign: dict = field(default_factory=dict)
    theta: dict = field(default_factory=dict)
    theta_all: dict = field(default_factory=dict)
    topic_words: dict = field(default_factory=dict)
    scan: dict = field(default_factory=dict)
    centroids: dict = field(default_factory=dict)
    dist: dict = field(default_factory=dict)
    band: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    context_flags: dict = field(default_factory=dict)
    topic_ids: list[str | None] = field(default_factory=list)


def contexts(doc_ids, tokens, vectors_by_id, sentiment_by_id=None) -> ContextResult:
    """Select maximum C_v over 2..10; ties favor the smaller topic count."""
    doc_ids = list(doc_ids)
    result = ContextResult()
    if not doc_ids:
        result.flags.append('few_docs')
        return result
    texts = [tokens[doc] for doc in doc_ids]
    dictionary = Dictionary(texts)
    dictionary.filter_extremes(no_below=params.DICT_NO_BELOW,
                               no_above=params.DICT_NO_ABOVE, keep_n=None)
    if len(doc_ids) < params.L3_MIN_DOCS or not dictionary:
        result.flags.append('few_docs')
        result.topic_ids = ['C1']
        result.topic_words['C1'] = []
        for doc in doc_ids:
            result.assign[doc] = 'C1'
            result.theta[doc] = 1.
            result.theta_all[doc] = [1.]
    else:
        corpus = [dictionary.doc2bow(words) for words in texts]
        best, best_cv = None, -np.inf
        for k in range(params.L3_TOPICS[0], params.L3_TOPICS[1] + 1):
            model = LdaModel(corpus=corpus, id2word=dictionary, num_topics=k,
                             passes=params.LDA_PASSES, random_state=params.SEED)
            cv = float(CoherenceModel(model=model, texts=texts, dictionary=dictionary,
                                      coherence='c_v', processes=1).get_coherence())
            result.scan[k] = dict(cv=cv, perplexity=float(2. ** -model.log_perplexity(corpus)))
            # Undefined coherence cannot beat a finite score. Keep the first
            # model if all candidates are undefined, giving a stable fallback.
            if best is None or (np.isfinite(cv) and cv > best_cv):
                best = model
                best_cv = cv if np.isfinite(cv) else -np.inf
        winners = {}
        for doc, bow in zip(doc_ids, corpus):
            posterior = [0.] * best.num_topics
            for topic, probability in best.get_document_topics(bow, minimum_probability=0):
                posterior[topic] = float(probability)
            result.theta_all[doc] = posterior
            winners[doc] = int(np.argmax(posterior))
            result.theta[doc] = max(posterior)
        active = sorted(set(winners.values()))
        result.topic_ids = [None] * best.num_topics
        for index, topic in enumerate(active, 1):
            context = f'C{index}'
            result.topic_ids[topic] = context
            result.topic_words[context] = [word for word, _ in best.show_topic(topic, topn=params.CTFIDF_TOP)]
        result.assign = {doc: result.topic_ids[topic] for doc, topic in winners.items()}
        if len(active) > params.CONTEXT_WARN_MAX:
            result.flags.append('granularity_exceeded')
    _geometry(result, vectors_by_id)
    _counter_flags(result, sentiment_by_id)
    return result


def _geometry(result, vectors):
    groups = {context: [] for context in result.topic_words}
    for doc, context in result.assign.items():
        groups[context].append(doc)
    # Never materialize the full Persona's float32 embedding matrix.
    for context, ids in groups.items():
        total = np.zeros_like(vectors[ids[0]], dtype=np.float32)
        for doc in ids:
            total += np.asarray(vectors[doc], dtype=np.float32)
        centroid = total / len(ids)
        norm = np.linalg.norm(centroid)
        if norm:
            centroid /= norm
        result.centroids[context] = centroid
        distances = []
        for doc in ids:
            vector = np.asarray(vectors[doc], dtype=np.float32)
            norm = np.linalg.norm(vector)
            cosine = float(vector @ centroid / norm) if norm else 0.
            distances.append(float(1. - np.clip(cosine, -1., 1.)))
        p50, p90 = np.percentile(distances, params.BAND_P)
        for doc, distance in zip(ids, distances):
            result.dist[doc] = distance
            result.band[doc] = 'core' if distance <= p50 else 'fringe' if distance <= p90 else 'edge'


def _counter_flags(result, sentiment):
    result.context_flags = {context: [] for context in result.centroids}
    if sentiment is None:
        return
    observed = {doc: float(sentiment[doc]) for doc in result.assign
                if doc in sentiment and np.isfinite(sentiment[doc])}
    if not observed:
        return
    persona_mean = np.mean(list(observed.values()))
    for context in result.centroids:
        ids = [doc for doc, assigned in result.assign.items() if assigned == context]
        values = [observed[doc] for doc in ids if doc in observed]
        if (len(ids) / len(result.assign) < params.COUNTER_DOC_SHARE and values
                and np.mean(values) <= persona_mean - params.COUNTER_SENT_GAP):
            result.context_flags[context].append('counter_context')
    if any('counter_context' in flags for flags in result.context_flags.values()):
        result.flags.append('counter_context')
