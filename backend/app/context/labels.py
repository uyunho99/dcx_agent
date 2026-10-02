"""Shared Korean display labels, kept as plain data for frontend parity."""

LABELS: dict[str, dict[str, str]] = {
    "taskMode": {
        "metric": "지표 개선형",
        "explore": "탐색·기획형",
    },
    "personaDimensions": {
        "social": "사회적 외부 페르소나",
        "taste": "개인 취향·활동",
        "movement": "신체 외부 동선",
        "bio": "내부 바이오",
    },
    "projectType": {
        "branding": "브랜딩",
        "new": "신규기획",
        "renewal": "리뉴얼",
        "ux": "UX개선",
    },
    "analysisGoal": {
        "needs": "니즈탐색",
        "marketing": "마케팅전략",
        "concept": "컨셉발굴",
        "segment": "세그먼트개척",
    },
    "price": {
        "premium": "프리미엄",
        "value": "가성비",
    },
    "market": {
        "leader": "시장 선도자",
        "challenger": "시장 도전자",
        "new": "신규 진입자",
    },
    "channels": {
        "naver_cafe": "네이버 카페",
        "naver_blog": "네이버 블로그",
        "youtube": "유튜브",
        "ppomppu": "뽐뿌",
        "clien": "클리앙",
        "fixture": "개발용 샘플",
    },
    "source": {
        "shopping": "쇼핑 분류",
        "llm_estimate": "언어 모델 추정",
        "user": "사용자 입력",
    },
    "households": {
        "single": "1인 가구",
        "newlywed": "신혼 가구",
        "infant": "영유아 자녀 가구",
        "school": "학령기 자녀 가구",
        "senior_cohab": "고령자 동거 가구",
    },
    "lifeStages": {
        "student": "학생",
        "early_career": "사회 초년기",
        "parenting": "자녀 양육기",
        "empty_nest": "자녀 독립기",
        "retired": "은퇴기",
    },
    "futureCustomer": {
        "competitor_users": "경쟁 제품 사용자",
        "watchers": "구매 관망자",
        "churned": "이탈 고객",
        "adjacent_needs": "인접 니즈 고객",
    },
    "alignmentSource": {
        "constraints": "사내 제약",
        "analysisGoal": "분석 목표",
        "positioning": "포지셔닝",
    },
}
