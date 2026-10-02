"""Locate whitespace-normalized quotations with offsets in prepared originals."""
import re


def locate(quote: dict, doc: dict) -> dict:
    field, idx = quote.get('field'), quote.get('idx')
    result = dict(field=field, idx=idx, start=None, end=None,
                  text=quote.get('text', ''), verified=False)
    if field in ('title', 'body'):
        source = doc.get(field) or ''
    elif field == 'comment' and isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(doc.get('comments') or []):
        comment = doc['comments'][idx]
        source = (comment.get('text') or '') if isinstance(comment, dict) else str(comment)
    else:
        return result
    # Each normalized character retains its original half-open span.
    chars, spans = [], []
    for token in re.finditer(r'\s+|\S', source):
        chars.append(' ' if token.group().isspace() else token.group())
        spans.append(token.span())
    needle = ' '.join(result['text'].split())
    start = ''.join(chars).find(needle) if needle else -1
    if start >= 0:
        result.update(start=spans[start][0], end=spans[start + len(needle) - 1][1], verified=True)
    return result
