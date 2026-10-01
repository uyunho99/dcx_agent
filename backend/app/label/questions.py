"""Versioned, domain-independent definitions shared by both labelers."""
import json
from pathlib import Path

QVER = 'q1'
_QUESTIONS = Path(__file__).with_name(f'questions.{QVER}.json')
_NOUL = ('anchor', 'sense', 'feel', 'think', 'act', 'situation')


def load_questions() -> dict:
    # Return independent definitions so prompt builders cannot mutate the template.
    return json.loads(_QUESTIONS.read_text(encoding='utf-8'))


def jev_questions(one_liner: str) -> dict:
    """Build eight wire questions; the actual context belongs in state's first line."""
    definitions = load_questions()
    return {name: definitions[name] for name in (*_NOUL, 'relate_outcome', 'reason_code')}
