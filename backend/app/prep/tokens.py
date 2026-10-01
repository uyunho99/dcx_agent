from functools import lru_cache

from kiwipiepy import Kiwi


@lru_cache(maxsize=1)
def _kiwi():
    return Kiwi(num_workers=1)


def tokenize(text, pos) -> list[str]:
    allowed = set(pos)
    return [token.form for token in _kiwi().tokenize(text) if token.tag in allowed]
