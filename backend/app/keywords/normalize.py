"""Normalize comparison keys and clean generated keywords without mutating inputs."""

import unicodedata

from .models import Keyword
from .taxonomy import AXES, is_valid

BANNED = {"후기", "비교", "추천", "가격", "장단점", "선택", "고민", "리뷰", "평가", "만족", "불만"}


def norm_key(kw: str) -> str:
    """Apply NFC, remove Unicode whitespace, then lowercase for comparisons."""
    return "".join(unicodedata.normalize("NFC", kw).split()).lower()


def clean_generated(
    items: list[dict], existing: list[Keyword], banned: set[str]
) -> tuple[list[dict], list[str]]:
    """Keep first valid occurrences, logging each drop or subcategory correction.

    The supplied banned set supplements the built-in words. Comparisons use
    normalized keys; retained dictionaries preserve their original keyword text.
    """
    seen = {norm_key(item.kw) for item in existing}
    banned_keys = {norm_key(word) for word in BANNED | banned}
    passed: list[dict] = []
    logs: list[str] = []
    for item in items:
        kw = item.get("kw")
        if not isinstance(kw, str):
            logs.append("Dropped keyword: kw must be a string.")
            continue
        key = norm_key(kw)
        if len(key) < 2:
            logs.append(f"Dropped {kw!r}: normalized keyword is shorter than 2 characters.")
            continue
        if key in banned_keys:
            logs.append(f"Dropped {kw!r}: banned keyword.")
            continue
        if key in seen:
            logs.append(f"Dropped {kw!r}: duplicate normalized keyword.")
            continue
        axis = item.get("axis")
        if not isinstance(axis, str) or axis not in AXES:
            logs.append(f"Dropped {kw!r}: unknown axis {axis!r}.")
            continue
        cleaned = item.copy()
        sub = item.get("sub")
        if not isinstance(sub, str) or not is_valid(axis, sub):
            cleaned["sub"] = AXES[axis][0]
            logs.append(f"Corrected {kw!r}: sub {sub!r} to {cleaned['sub']!r} for axis {axis!r}.")
        passed.append(cleaned)
        seen.add(key)
    return passed, logs
