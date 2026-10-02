"""Derived keyword labels for responses only; storage keeps the original kw."""
import re
from functools import lru_cache

from kiwipiepy import Kiwi


_kiwi: Kiwi | None = None
_HANGUL = re.compile('[\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7af\ud7b0-\ud7ff]')
_KEEP = {'전', '후', '중', '약', '앱', '길', '날'}
_KEEP_TAGS = {'MM', 'MAG', 'MAJ', 'NR', 'NNB', 'NP', 'VV', 'VA', 'VX', 'IC'}
_PREFIX = {'선', '암', '타', '재', '초', '입', '노', '회', '가', '미', '제', '첫'}


@lru_cache(maxsize=4096)
def display_form(kw: str) -> str:
    if len(kw) <= 3 or any(char.isspace() for char in kw) or not _HANGUL.search(kw):
        return kw
    global _kiwi
    try:
        if _kiwi is None:
            _kiwi = Kiwi()
        segments = _kiwi.space(kw).split()
        tokens = _kiwi.tokenize(kw)
        # Offsets refer to the original unspaced keyword throughout merging.
        offsets = []
        offset = 0
        for segment in segments:
            offsets.append(offset)
            offset += len(segment)
        index = 0
        while index < len(segments):
            segment = segments[index]
            if len(segment) == 1 and len(segments) > 1:
                tag = next((token.tag for token in tokens
                            if token.start <= offsets[index] < token.start + token.len), None)
                if segment in _KEEP or tag in _KEEP_TAGS:
                    index += 1
                    continue
                if index + 1 < len(segments) and (
                    index == 0 or tag == 'XPN' or segment in _PREFIX
                ):
                    segments[index + 1] = segment + segments[index + 1]
                    offsets[index + 1] = offsets[index]
                else:
                    segments[index - 1] += segment
                del segments[index]
                del offsets[index]
                continue
            index += 1
        result = ' '.join(segments)
        return result if ''.join(result.split()) == kw else kw
    except Exception:
        return kw


def with_display(keywords: list[dict]) -> list[dict]:
    return [
        {**keyword, 'display': display_form(keyword['kw'])}
        if isinstance(keyword.get('kw'), str) else dict(keyword)
        for keyword in keywords
    ]
