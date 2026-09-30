"""Deliberately code-only errors: adapter messages may contain credentials."""
import re


def safe_error(exc) -> str:
    if isinstance(exc, str):
        # Only accept codes produced here, including legacy rule numbers.
        return exc if re.fullmatch(r'(?:[A-Za-z]+Error|HTTP [1-5][0-9]{2}|AdapterBlocked|parse_error|timeout|[1-6])', exc) else 'crawl_error'
    response = getattr(exc, 'response', None)
    code = getattr(response, 'status_code', None)
    if isinstance(code, int) and 100 <= code <= 599:
        return f'HTTP {code}'
    name = type(exc).__name__
    return name if re.fullmatch(r'[A-Za-z]+', name) else 'crawl_error'
