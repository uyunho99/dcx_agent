"""Shared class-based TF-IDF for tokenized document groups."""
from collections import Counter
from math import log1p

from app.segment.stopwords import filter_words


def ctfidf(groups: dict[str, list[list[str]]], top: int, bk: str | None = None) -> dict[str, list[str]]:
    """Rank tokens by class TF * log(1 + mean class length / corpus TF).

    Each group is one concatenated class document. TF is L1-normalized
    within that class; corpus TF counts token occurrences across classes.
    Empty groups return no keywords; lexical ordering breaks score ties.
    Scores use raw tokens; output excludes stopwords and fills from the next ranks.
    """
    if top < 0:
        raise ValueError('top must be nonnegative')
    counts = {key: Counter(word for doc in docs for word in doc)
              for key, docs in groups.items()}
    corpus = Counter()
    for words in counts.values():
        corpus.update(words)
    average = sum(corpus.values()) / len(counts) if counts else 0
    idf = {word: log1p(average / frequency) for word, frequency in corpus.items()}
    result = {}
    for key, words in counts.items():
        length = sum(words.values())
        ranked = sorted(words, key=lambda word: (-words[word] / length * idf[word], word))
        result[key] = filter_words(ranked, bk)[:top]
    return result
