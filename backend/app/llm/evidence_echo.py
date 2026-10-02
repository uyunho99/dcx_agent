"""Deterministic offline QA responses anchored to the actual task inputs.

These intentionally varied labels are synthetic, not semantic judgments. Stable
content/ID hashes keep results independent of batching and thread scheduling.
"""
import hashlib
import json
import re


def _seed(text):
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], 'big')


def queries(task):
    from app.evidence.params import FORBIDDEN, QUERY_DIMS
    endings = ('감각을 살펴봤어요.', '마음이 편해지고 싶어요.', '차이를 알고 싶어요.',
               '직접 조절했어요.', '가족과 이야기했어요.', '원하는 결과를 얻고 싶어요.',
               '기대와 달라 불편했어요.', '다른 방법도 시도하고 싶어요.')
    rows = {}
    for attachment in task.attachments:
        for line in attachment.body.splitlines():
            if ' · 주된 제약: ' not in line or ' · 키워드: ' not in line:
                continue
            cid, action = line.split(' · ', 1)
            topic = re.sub(FORBIDDEN, '', action.split(' · 주된 제약: ')[0] + ' ' + line.split(' · 키워드: ', 1)[1]).strip()
            rows[cid] = {dim: f'나는 {topic or "일상 경험"} {ending}'
                         for dim, ending in zip(QUERY_DIMS, endings)}
    return dict(persona_query=dict(desire_check=['나는 편안하게 지내고 싶어요.', '나는 부담을 줄이고 싶어요.'],
                                  artifact=['나는 도구를 직접 조절했어요.']),
                context_queries=rows, anchor_context_ids=list(rows))


def tag(task):
    known = re.findall(r'^(#[1-9][0-9]*) (.+)$', task.instructions.split('Known Insight:\n')[-1], re.M)
    items = []
    for attachment in task.attachments:
        doc = json.loads(attachment.body)
        fields = [('body', None, doc.get('body')), ('title', None, doc.get('title'))]
        fields += [('comment', c['idx'], c['text']) for c in doc.get('comments', [])]
        quotes = []
        for field, idx, text in fields:
            if text and text.strip():
                excerpt = re.split(r'(?<=[.!?。！？])\s+|\n', text.strip(), maxsplit=1)[0]
                quotes = [dict(field=field, idx=idx, text=excerpt)]
                break
        seed = _seed(attachment.title)
        relevant = bool(quotes) and seed % 11 != 0
        text = '\n'.join(value or '' for _, _, value in fields)
        match = next((label for label, sentence in known if sentence.strip() in text), 'none')
        pain = relevant and seed % 3 != 0
        items.append(dict(doc_id=attachment.title, relevant=relevant,
            reason_code=None if relevant else ('no_needs', 'other', 'pure_criticism', 'ad')[seed % 4],
            polarity=(-.9, -.5, -.1, .3, .8)[seed % 5],
            pain_point=dict(text=quotes[0]['text'], quote=quotes[0]['text']) if pain else None,
            unmet_need='나는 더 편안하게 사용하고 싶어요.' if relevant and seed % 3 != 1 else None,
            situation=dict(state='사용 중', emotion='기대', barrier=None),
            context_dims=doc.get('context_dims'), artifacts=[], known_match=match, quotes=quotes))
    return dict(items=items)


def novelty(task):
    payload = json.loads(task.attachments[0].body)
    levels = ('none', 'low', 'medium', 'high', 'very_high')
    return dict(items=[dict(doc_id=row['doc_id'], novelty=levels[_seed(row['doc_id']) % 5],
                           reason='오프라인 QA용 새로움 단계입니다.') for row in payload['new_rows']])


BUILDERS = {'evidence.queries': queries, 'evidence.tag': tag, 'evidence.novelty': novelty}
