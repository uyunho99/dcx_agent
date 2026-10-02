"""Cached scoring of the committed KnuSentiLex SentiWord_info dictionary."""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _load() -> dict[str, float]:
    """Resolve duplicate keys by mean polarity; roots override word aliases."""
    with Path(__file__).with_name('knu_senti.json').open(encoding='utf-8') as stream:
        entries = json.load(stream)
    roots, words = defaultdict(list), defaultdict(list)
    for entry in entries:
        score = int(entry['polarity']) / 2
        if entry['word_root']:
            roots[entry['word_root']].append(score)
        if entry['word']:
            words[entry['word']].append(score)
    lookup = {word: sum(scores) / len(scores) for word, scores in words.items()}
    lookup.update({root: sum(scores) / len(scores) for root, scores in roots.items()})
    return lookup


def polarity(tokens: list[str]) -> float:
    """Mean matched token polarity / 2, in [-1, 1]; unmatched tokens ignored.

    Match word_root first, then word as fallback. Repeated tokens contribute
    repeatedly; duplicate dictionary roots are averaged once per token.
    """
    lookup = _load()
    scores = [lookup[token] for token in tokens if token in lookup]
    return float(sum(scores) / len(scores)) if scores else 0.0
