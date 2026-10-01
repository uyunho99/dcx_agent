"""Versioned channel phrase defaults; callers receive independent copies."""
import json
from pathlib import Path


def default_boilerplate() -> dict[str, list[str]]:
    return json.loads(Path(__file__).with_name('boilerplate.v1.json').read_text(encoding='utf-8'))
