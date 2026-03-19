# DCX Agent 파이프라인 단계별 구성

> 소비자 인사이트 분석 파이프라인 — Naver Cafe 데이터 기반 페르소나 도출 시스템

## 전체 아키텍처

- **Backend**: FastAPI (Python) — `backend/app/`
- **Frontend**: Next.js 16 + React 19 + Zustand + Tailwind CSS — `frontend/src/`
- **외부 서비스**: AWS S3, Naver Cafe API, Claude API, Voyage AI, Pinecone
- **데이터 흐름**: 각 단계 결과가 S3에 JSONL/JSON으로 저장되어 다음 단계 입력으로 사용

```
시작 → 키워드 → 크롤링 → 전처리 → 라벨링 → 학습 → 클러스터링 → 페르소나
```

---

## 1단계: 시작 (Start)

### 목적

세션을 생성하고, 분석 대상 제품 및 문제 정의를 입력받는 초기 설정 단계.

### 입력 항목

| 항목 | 필드명 | 설명 |
|------|--------|------|
| 메인 키워드 | `bk` | 분석 대상 제품명 |
| 문제 정의 | `problemDef` | 분석하려는 문제/질문 |
| 타겟 유형 | `ages` | 주부, 직장인, 1인가구 등 |
| 나이대 | `ageRange` | 20대, 30대, 40대, 50대+ |
| 성별 | `gens` | 남성, 여성 |

### 주요 흐름

1. 사용자가 제품명 및 문제 정의 입력
2. 세션 ID 자동 생성: `s{timestamp}` 형식
3. S3에 `sessions/{sid}/session.json`으로 저장
4. 기존 세션 목록 조회 및 불러오기 가능 (`SessionList` 컴포넌트)

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/start/page.tsx`
- **백엔드**: `backend/app/routers/sessions.py`
- **컴포넌트**: `frontend/src/components/SessionList.tsx`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/save-session` | 세션 저장 |
| GET | `/session/{sid}` | 세션 불러오기 |
| GET | `/sessions` | 전체 세션 목록 |
| DELETE | `/delete-session/{sid}` | 세션 삭제 |

### 데이터 저장 경로

- S3: `sessions/{sid}/session.json`

---

## 2단계: 키워드 (Keywords)

### 목적

Claude AI를 활용하여 소비자 인사이트 발굴을 위한 검색 키워드를 반복적으로 생성·확장·수렴.

### 4라운드 워크플로우

| 라운드 | 유형 | 동작 |
|--------|------|------|
| R1 | 발산 | 제품 + 문제정의 기반 70개 이상 키워드 생성 |
| R2 | 발산 | 기존 키워드 제외 100개 이상 추가 생성 |
| R3 | 수렴 | 총 160개 미만이면 100개 이상 추가 |
| R3-Expand | 재발산 | 필요 시 추가 확장 |
| Final | 검토 | 카테고리별 수동 승인/거절 |

### 키워드 스코어링

각 키워드를 Naver Cafe API로 검색량 조회 후 점수 부여:

| 검색 결과 수 | 점수 |
|-------------|------|
| 10,000건 이상 | 95점 |
| 5,000~10,000건 | 85점 |
| 1,000~5,000건 | 75점 |
| 그 이하 | 점수 감소 |

### 키워드 카테고리

`상황맥락`, `감정표현`, `문제상황`, `숨은니즈`, `타겟특화`, `시즌시간`, `공간장소`

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/keywords/page.tsx`
- **백엔드 라우터**: `backend/app/routers/keywords.py`
- **서비스 (Claude)**: `backend/app/services/claude.py`
- **서비스 (Naver)**: `backend/app/services/naver.py`
- **컴포넌트**: `frontend/src/components/KeywordTag.tsx`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/generate-keywords` | 키워드 생성 (라운드별) |

### 데이터 저장 경로

- S3: `sessions/{sid}/session.json` 내 `allKw` 배열에 누적

---

## 3단계: 크롤링 (Crawling)

### 목적

승인된 키워드를 사용하여 Naver Cafe에서 소비자 게시글을 대량 수집.

### 설정 항목

| 항목 | 기본값 | 설명 |
|------|--------|------|
| 목표 수집 건수 | 50,000 | 최대 수집할 문서 수 |
| 날짜 범위 | - | from/to 날짜 지정 |
| 포함 카페 | 전체 | 특정 카페만 포함 (미입력 시 전체) |
| 제외 카페 | - | 중고거래 등 제외할 카페 |
| 광고 필터 | - | 광고 게시글 필터 키워드 |

### 크롤링 로직

1. 각 키워드에 대해 `{bk} {keyword}`로 Naver Cafe API 호출
2. 페이지당 100건, 키워드당 최대 1,000건 조회
3. 필터링: 날짜 범위, 광고 키워드, 제외 카페, 제품명 포함 여부
4. 링크 기준 중복 제거
5. 500건마다 배치 저장, 목표 도달 시 중단

### 수집 데이터 구조

```json
{
  "kw": "검색 키워드",
  "title": "게시글 제목",
  "desc": "게시글 설명",
  "link": "카페 게시글 URL",
  "cafe": "카페명",
  "date": "YYYYMMDD"
}
```

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/crawling/page.tsx`
- **백엔드 라우터**: `backend/app/routers/crawling.py`
- **서비스**: `backend/app/services/crawling.py`, `backend/app/services/naver.py`
- **작업 관리**: `backend/app/jobs/manager.py`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/crawl` | 크롤링 시작 (비동기) |
| GET | `/status/{sid}` | 진행 상태 조회 |

### 비동기 처리

- 데몬 스레드로 백그라운드 실행
- `JobManager`로 스레드 안전한 상태 추적
- 프론트엔드에서 3초 간격 폴링

### 데이터 저장 경로

- S3: `crawl/{sid}/*.jsonl` (500건 단위 배치)

---

## 4단계: 전처리 (Preprocessing)

### 목적

크롤링 데이터의 노이즈 제거, 중복 제거, 품질 필터링.

### 전처리 로직

1. S3에서 크롤링 데이터 로드: `crawl/{sid}/*.jsonl`
2. **필터링 단계**:
   - 광고 필터 매칭 제거 (제목 + 설명)
   - 제외 카페 매칭 제거
   - 링크 기준 중복 제거
   - 제목 5자 미만 AND 설명 10자 미만 문서 제거
3. 각 문서에 `idx` (원본 인덱스) 부여

### 출력 정보

- 원본 건수
- 필터링 후 건수
- 제거율(%)

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/preprocess/page.tsx`
- **백엔드 라우터**: `backend/app/routers/preprocessing.py`
- **서비스**: `backend/app/services/preprocessing.py`
- **유틸리티**: `backend/app/utils/text.py`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/preprocess` | 전처리 시작 |
| GET | `/preprocess-status/{sid}` | 상태 조회 |

### 데이터 저장 경로

- S3: `preprocessed/{sid}/{timestamp}.jsonl`

---

## 5단계: 라벨링 (Labeling)

### 목적

반지도 학습(Semi-supervised Learning)을 위해 전처리 데이터의 2% 샘플에 대해 관련/무관 수동 라벨링.

### 라벨링 프로세스

1. 전처리 데이터의 **2% 랜덤 샘플** 로드
2. 배치당 최대 **20개 샘플** 표시
3. 각 샘플에 **관련(1)** 또는 **무관(0)** 라벨 토글
4. 최소 **5개** 이상 라벨링 필요
5. 진행률: `라벨링 완료 수 / (전체 × 2%)`

### 라벨 데이터 구조

```json
{
  "title": "게시글 제목",
  "desc": "게시글 설명",
  "cafe": "카페명",
  "kw": "검색 키워드",
  "link": "URL",
  "label": 1
}
```

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/labeling/page.tsx`
- **백엔드 라우터**: `backend/app/routers/labeling.py`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/sample/{sid}?percent=2` | 랜덤 샘플 추출 |
| POST | `/save-session` | 라벨 결과 세션에 저장 |

### 데이터 저장 경로

- S3: `sessions/{sid}/session.json` 내 `labeledData` 배열

---

## 6단계: 학습 (Training)

### 목적

라벨링된 소량의 데이터를 기반으로 앙상블 분류 모델을 학습하여, 전체 데이터에 관련성 점수 부여.

### 모델 앙상블

**TensorFlow 사용 가능 시:**

| 모델 | 구조 |
|------|------|
| LSTM | Embedding → LSTM(64) → Dense(32) → Sigmoid |
| CNN | Embedding → Conv1D(64, kernel=5) → GlobalMaxPool → Dense(32) → Sigmoid |
| GRU | Embedding → GRU(64) → Dense(32) → Sigmoid |

**TensorFlow 불가 시 (Scikit-learn 폴백):**

| 모델 | 구조 |
|------|------|
| Logistic Regression | TF-IDF → LogisticRegression |
| Random Forest | TF-IDF → RandomForestClassifier(100 trees) |
| Gradient Boosting | TF-IDF → GradientBoostingClassifier(100 trees) |

### 학습 프로세스

1. 텍스트 토큰화 (최대 200단어, vocab 10,000)
2. 3개 모델 각각 학습
3. 전체 전처리 데이터에 대해 예측 수행
4. **앙상블**: 3개 모델의 확률값 평균
5. **임계값 0.5**: score ≥ 0.5 → 관련 문서

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/training/page.tsx`
- **백엔드 라우터**: `backend/app/routers/training.py`
- **서비스**: `backend/app/services/training.py`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/train` | 학습 시작 (비동기) |
| GET | `/train-status/{sid}` | 상태 조회 |

### 데이터 저장 경로

- S3: `classified/{sid}/relevant_{timestamp}.jsonl` (relevance_score 포함)
- S3: `classified/{sid}/irrelevant_{timestamp}.jsonl`

---

## 7단계: 클러스터링 (Clustering)

### 목적

관련 문서들을 주제별로 그룹화하고, 사용자가 클러스터를 선택/병합하여 정제.

### 클러스터링 프로세스

1. 관련 문서 로드 (`classified/{sid}/relevant_*.jsonl`)
2. **Voyage AI 임베딩 생성**:
   - 모델: `voyage-multilingual-2` (1024차원)
   - 128건씩 배치 처리
3. **최적 k 자동 결정**:
   - 탐색 범위: k = 3 ~ min(15, 데이터수/10)
   - 실루엣 점수(Silhouette Score) 최대값 선택
4. **K-means 클러스터링** 수행
5. **TF-IDF 키워드 추출**:
   - Max features: 3,000 / N-gram: 1-2
   - 클러스터당 상위 10개 키워드

### 클러스터 정제

- 체크박스로 유지할 클러스터 선택
- 병합할 클러스터 지정 (예: "1,3,5" → 클러스터 1로 통합)
- 정제 후 순차적 재인덱싱

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/clustering/page.tsx`
- **백엔드 라우터**: `backend/app/routers/clustering.py`
- **서비스**: `backend/app/services/clustering.py`
- **임베딩**: `backend/app/services/voyage.py`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/cluster` | 클러스터링 시작 |
| GET | `/cluster-status/{sid}` | 상태 조회 |
| POST | `/cluster-refine` | 클러스터 정제 |

### 데이터 저장 경로

- S3: `clusters/{sid}/cluster_{id}_{timestamp}.jsonl` (초기)
- S3: `clusters_refined/{sid}/data_{timestamp}.jsonl` (정제 후)

---

## 8단계: 페르소나 (Personas)

### 목적

정제된 클러스터 기반으로 Claude AI가 소비자 페르소나를 생성하고, Pinecone에 임베딩하여 RAG 검색 지원.

### 페르소나 생성 프로세스

1. 정제된 클러스터 데이터 로드
2. 클러스터별 Pinecone RAG 검색 (키워드로 유사 문서 Top 10)
3. 컨텍스트 구성: 클러스터명, 크기, 키워드 다양성, 샘플 문서
4. Claude가 클러스터별 페르소나 생성:

| 클러스터 크기 | 페르소나 수 |
|-------------|-----------|
| 50건 미만 | 1개 |
| 50~200건 | 2개 |
| 200건 이상 | 3개 |
| 키워드 다양성 높음 | +1개 |

### 페르소나 출력 구조

```json
[
  {
    "cluster_id": 1,
    "cluster_name": "클러스터 이름",
    "personas": [
      {
        "name": "위트있는 은유적 이름",
        "situation": "소비자 상황 설명",
        "pain_point": "핵심 고민",
        "insight": "마케팅 액셔너블 인사이트"
      }
    ]
  }
]
```

### SNA 네트워크 시각화

- D3.js force-directed 그래프
- 노드 유형: 제품(indigo) → 클러스터(amber) → 페르소나(green)
- 드래그 가능, 호버 시 pain_point + insight 툴팁

### 관련 파일

- **프론트엔드**: `frontend/src/app/pipeline/personas/page.tsx`
- **백엔드 라우터**: `backend/app/routers/personas.py`, `backend/app/routers/embedding.py`
- **서비스**: `backend/app/services/personas.py`, `backend/app/services/embedding.py`
- **벡터 DB**: `backend/app/services/pinecone_svc.py`, `backend/app/services/voyage.py`
- **컴포넌트**: `frontend/src/components/PersonaCard.tsx`, `frontend/src/components/SNAGraph.tsx`

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/persona` | 페르소나 생성 시작 |
| GET | `/persona-status/{sid}` | 상태 조회 |
| POST | `/embed` | 임베딩 시작 |
| GET | `/embed-status/{sid}` | 임베딩 상태 조회 |
| GET | `/sna-data/{sid}` | SNA 그래프 데이터 |

### 데이터 저장 경로

- S3: `personas/{sid}/result_{timestamp}.json`
- Pinecone: `cx-{sid}` 인덱스 (1024차원, 코사인 메트릭)

---

## 전체 데이터 파이프라인 요약

```
[시작] 세션 생성
   ↓ sessions/{sid}/session.json
[키워드] Claude AI 키워드 생성 (4라운드)
   ↓ sessions/{sid}/session.json → allKw
[크롤링] Naver Cafe 대량 수집
   ↓ crawl/{sid}/*.jsonl
[전처리] 노이즈·중복 제거
   ↓ preprocessed/{sid}/*.jsonl
[라벨링] 2% 수동 라벨링
   ↓ sessions/{sid}/session.json → labeledData
[학습] 3모델 앙상블 분류
   ↓ classified/{sid}/relevant_*.jsonl
[클러스터링] Voyage 임베딩 + K-means
   ↓ clusters_refined/{sid}/data_*.jsonl
[페르소나] Claude AI 페르소나 생성 + Pinecone 임베딩
   ↓ personas/{sid}/result_*.json + Pinecone index
```

---

## 공통 인프라

| 구성요소 | 기술 | 역할 |
|----------|------|------|
| 비동기 작업 관리 | `JobManager` (데몬 스레드) | 크롤링/학습/클러스터링/임베딩/페르소나 비동기 실행 |
| 상태 폴링 | `usePolling` 커스텀 훅 | 3~5초 간격 작업 상태 확인 |
| 상태 관리 | Zustand | 세션·키워드·단계 전역 상태 |
| UI 레이아웃 | 3컬럼 구조 | StepBar(진행바) + Content(메인) + ChatPanel(챗봇) |
| 챗봇 | `POST /chat`, `/insight-chat` | 파이프라인 컨텍스트 기반 대화 + RAG 검색 |
