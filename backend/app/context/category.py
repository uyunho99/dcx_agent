from collections import Counter
import json
from typing import Literal
from pydantic import BaseModel
from app.external.naver_shopping import search_categories
from app.external.base import Unconnected
from app.llm.base import Attachment, LLMTask
from app.llm.registry import run_task
from app.context.store import StoreError

SHOPPING_CATEGORIES = ['패션의류', '패션잡화', '화장품/미용', '디지털/가전', '가구/인테리어', '출산/육아', '식품', '스포츠/레저', '생활/건강', '여가/생활편의', '도서']


class CategoryPath(BaseModel):
    l1: str
    l2: str
    l3: str


class CategorySuggestion(CategoryPath):
    source: Literal['shopping', 'llm_estimate']


def suggest_category(bk, one_liner) -> CategorySuggestion:
    try:
        paths = search_categories(bk)
    except Unconnected:
        paths = []
    if paths:
        l1, l2, l3 = Counter(paths).most_common(1)[0][0]
        return CategorySuggestion(l1=l1, l2=l2, l3=l3, source='shopping')
    # No session exists yet: attach the supplied context text, never a file path.
    result = run_task(LLMTask(task='category_suggest', sid='category_suggest',
                     instructions='제품 분류 l1,l2,l3을 JSON으로 추정하세요. 대분류: ' + json.dumps(SHOPPING_CATEGORIES, ensure_ascii=False),
                     attachments=[Attachment(title='project_context.md', body=f'- 제품명: {bk}\n- 한줄 정의: {one_liner}')],
                     output_schema=CategoryPath))
    if not result.ok:
        raise StoreError('제품군 추정에 실패했습니다', 502, result.error.kind)
    return CategorySuggestion(**result.data.model_dump(), source='llm_estimate')
