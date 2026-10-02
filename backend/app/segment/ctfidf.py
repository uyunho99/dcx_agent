"""Shared class-based TF-IDF for tokenized document groups."""
from collections import Counter
from math import log1p


def ctfidf(groups: dict[str, list[list[str]]], top: int) -> dict[str, list[str]]:
    """Rank tokens by class TF * log(1 + mean class length / corpus TF).

    Each group is one concatenated class document. TF is L1-normalized
    within that class; corpus TF counts token occurrences across classes.
    Empty groups return no keywords; lexical ordering breaks score ties.
    Raw tokens are retained (including Korean and single-character tokens).
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
        result[key] = sorted(words, key=lambda word: (-words[word] / length * idf[word], word))[:top]
    return result
