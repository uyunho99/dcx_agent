import re
import json
import time
import requests
from fastapi import APIRouter

from app.services.claude import call_claude
from app.config import settings
from app.models.schemas import KeywordGenRequest

router = APIRouter()


@router.post("/generate-keywords")
def generate_keywords(req: KeywordGenRequest):
    """AI 키워드 생성 - n8n의 r1/r2/r3 로직을 서버에서 직접 처리."""
    bk = req.bk
    problem_def = req.problemDef
    existing_kw = req.existingKeywords
    round_num = req.round

    if not bk:
        return {"status": "error", "error": "bk (제품명) 필요"}

    existing_str = ", ".join(existing_kw) if existing_kw else "없음"

    if round_num == 1:
        ages_str = ", ".join(req.ages) if req.ages else ""
        age_range_str = ", ".join(req.ageRange) if req.ageRange else ""
        gens_str = ", ".join(req.gens) if req.gens else ""
        target_desc = " | ".join(filter(None, [ages_str, age_range_str, gens_str])) or "전체"

        prompt = f"""제품/서비스: "{bk}"
문제정의: {problem_def or '소비자 경험 분석'}
타겟: {target_desc}

당신은 소비자 경험(CX) 리서치 전문가입니다.
네이버 카페에서 "{bk}" 관련 소비자의 숨겨진 경험과 니치한 맥락을 발굴하기 위한 검색 키워드를 생성하세요.

## 키워드 형태 규칙 (매우 중요!)
- 반드시 1~2단어 (최대 3글자 단어 2개)
- 명사, 형용사 위주
- 문장 형태 절대 금지! "일요일도 연락", "휴가중 전화" 같은 문장/구절은 안됨
- 좋은 예: 누수, 화재, 단열, 소음, 곰팡이, 환기, 습도, 결로, 균열
- 나쁜 예: 보험 후기, 보험 비교, 보험 추천

## 절대 금지 키워드
후기, 비교, 추천, 가격, 장단점, 선택, 고민, 리뷰, 평가, 만족, 불만

## 키워드 방향 (문제정의 중심)
- 문제정의에서 출발하여 소비자가 겪는 구체적 상황/사물/현상을 나타내는 단어
- Pain Point 키워드 필수: 불편, 실패, 후회, 걱정, 고장, 분쟁 등 소비자 고통을 드러내는 단어
- "{bk} + [키워드]"로 네이버 카페 검색 시 실제 경험담이 나올 법한 단어
- 에어컨 예시: 습도, 온도, 추위, 환기, 화초, 소음, 쾌적, 타이머, 렌탈, 단열, 결로, 곰팡이, 수면, 외출, 집콕, 요리, 더위, 신혼, 자취, 재택, 강아지, 고양이, 신생아, 임산부
- 보험 예시: 누수, 화재, 침수, 균열, 도난, 분실, 사고, 골절, 입원, 수술, 통원, 약관, 면책, 갱신, 해지, 실손, 치아, 임신, 출산, 노후

## 카테고리 분류
- 상황맥락: 소비자가 처한 구체적 상황
- 감정표현: 감정/심리 상태
- 문제상황: 예상 못한 문제/트러블
- 숨은니즈: 잘 드러나지 않는 니즈
- 타겟특화: {target_desc} 특유의 맥락
- 시즌시간: 계절, 시간대, 시기 관련
- 공간장소: 특정 공간이나 장소

## 출력 (JSON 배열만, 설명 없이)
[{{"kw": "키워드", "cat": "카테고리"}}]

각 카테고리당 최소 12개씩, 총 70개 이상 생성. 카테고리당 1-2개만 나오면 안됨:"""
    else:
        prompt = f"""제품: "{bk}"
문제정의: {problem_def or '소비자 경험 분석'}
기존 키워드: {existing_str}

기존 키워드와 중복되지 않는 새 키워드를 생성하세요.

## 규칙
- "후기/비교/추천/가격/선택/고민" 같은 흔한 키워드 절대 금지
- 소비자의 구체적 상황, 감정, 에피소드를 드러내는 니치한 키워드
- 반드시 1~2단어 명사/형용사. 문장 금지!
- "{bk} + [키워드]"로 크롤링하므로 키워드에 "{bk}" 포함 금지
- 더 깊고, 더 구체적이고, 더 예상 밖의 소비자 경험 맥락

[{{"kw": "키워드", "cat": "카테고리"}}]

각 카테고리당 최소 15개씩, 총 100개 이상 생성. 카테고리당 1-2개만 나오면 절대 안됨. 다양하고 풍부하게. JSON만 출력:"""

    try:
        text = call_claude(prompt, max_tokens=8000, timeout=120)
        if text:
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                keywords = json.loads(match.group())
                scored = []
                for i, kw_obj in enumerate(keywords):
                    kw = kw_obj.get("kw", "")
                    cat = kw_obj.get("cat", "")
                    if not kw or len(kw) < 2:
                        continue
                    if kw.lower() in [e.lower() for e in existing_kw]:
                        continue

                    score = 50
                    total = 0
                    try:
                        nr = requests.get(
                            "https://openapi.naver.com/v1/search/cafearticle.json",
                            headers={
                                "X-Naver-Client-Id": settings.naver_client_id,
                                "X-Naver-Client-Secret": settings.naver_client_secret,
                            },
                            params={"query": f"{bk} {kw}", "display": 1},
                            timeout=3,
                        )
                        total = nr.json().get("total", 0)
                        if total >= 10000:
                            score = 95
                        elif total >= 5000:
                            score = 85
                        elif total >= 1000:
                            score = 75
                        elif total >= 500:
                            score = 65
                        elif total >= 100:
                            score = 55
                        elif total >= 50:
                            score = 45
                        elif total >= 10:
                            score = 35
                        else:
                            score = 25
                    except Exception:
                        pass

                    scored.append({"id": i + 1, "kw": kw, "cat": cat, "score": score, "total": total})
                    if i % 5 == 4:
                        time.sleep(0.1)

                scored.sort(key=lambda x: -x.get("score", 0))
                return {"status": "ok", "keywords": scored, "round": round_num}
        return {"status": "error", "error": "Claude API 응답 파싱 실패"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
