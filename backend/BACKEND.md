# DCX Agent 백엔드 구조

> FastAPI 기반 소비자 인사이트 파이프라인 백엔드

## 폴더 구조

```
backend/app/
├── main.py                  # FastAPI 앱 설정 (CORS, 라우터 등록)
├── config.py                # 환경변수 설정 (Pydantic Settings)
├── __init__.py
│
├── models/
│   ├── schemas.py           # Pydantic 요청/응답 스키마
│   └── __init__.py
│
├── routers/                 # API 엔드포인트 (단계별)
│   ├── sessions.py          # 세션 관리
│   ├── keywords.py          # 키워드 생성
│   ├── crawling.py          # 웹 크롤링
│   ├── preprocessing.py     # 데이터 전처리
│   ├── labeling.py          # 수동 라벨링
│   ├── training.py          # 모델 학습
│   ├── clustering.py        # 클러스터링
│   ├── embedding.py         # 벡터 임베딩
│   ├── personas.py          # 페르소나 생성
│   ├── chat.py              # 챗봇 (파이프라인 + 인사이트)
│   ├── search.py            # 유사 문서 검색
│   └── __init__.py
│
├── services/                # 비즈니스 로직
│   ├── claude.py            # Claude API 통합
│   ├── crawling.py          # Naver Cafe 크롤링 로직
│   ├── preprocessing.py     # 데이터 필터링·중복제거
│   ├── training.py          # ML 앙상블 학습
│   ├── clustering.py        # K-means 클러스터링
│   ├── personas.py          # Claude 기반 페르소나 추출
│   ├── embedding.py         # Pinecone 벡터 저장
│   ├── naver.py             # Naver API 래퍼
│   ├── voyage.py            # Voyage AI 임베딩
│   ├── pinecone_svc.py      # Pinecone 벡터 검색
│   ├── s3.py                # AWS S3 파일 입출력
│   └── __init__.py
│
├── jobs/
│   ├── manager.py           # 스레드 안전 작업 상태 관리
│   └── __init__.py
│
└── utils/
    └── text.py              # 텍스트 정제 유틸리티
```

---

## main.py — 앱 설정

FastAPI 앱 인스턴스 생성, CORS 미들웨어 설정 (모든 origin 허용), 전체 라우터 등록.

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `health()` | `GET /health` | API 헬스체크 |

---

## config.py — 환경변수

Pydantic `BaseSettings`를 상속한 `Settings` 클래스. `.env` 파일에서 로드.

| 변수 | 용도 |
|------|------|
| `s3_bucket`, `s3_region` | AWS S3 버킷/리전 |
| `naver_client_id`, `naver_client_secret` | Naver API 인증 |
| `claude_api_key` | Claude API 키 |
| `pinecone_api_key` | Pinecone API 키 |
| `voyage_api_key` | Voyage AI API 키 |

---

## models/schemas.py — 요청/응답 스키마

모든 API 요청에 사용되는 Pydantic `BaseModel` 정의:

| 스키마 | 용도 | 주요 필드 |
|--------|------|----------|
| `SessionSaveRequest` | 세션 저장 | `sid`, `data` |
| `KeywordGenRequest` | 키워드 생성 | `bk`, `problemDef`, `round`, `existing`, `ages`, `ageRange`, `gens` |
| `CrawlRequest` | 크롤링 시작 | `sid`, `bk`, `keywords`, `target`, `dateFrom`, `dateTo`, `includeCafes`, `excludeCafes`, `adFilters` |
| `PreprocessRequest` | 전처리 시작 | `sid`, `adFilters`, `excludeCafes` |
| `TrainRequest` | 학습 시작 | `sid`, `labeledData` |
| `ClusterRequest` | 클러스터링 시작 | `sid` |
| `ClusterRefineRequest` | 클러스터 정제 | `sid`, `keep`, `merge` |
| `EmbedRequest` | 임베딩 시작 | `sid` |
| `PersonaRequest` | 페르소나 생성 | `sid`, `bk`, `problemDef` |
| `SearchRequest` | 유사 문서 검색 | `sid`, `query`, `topK` |
| `ChatRequest` | 파이프라인 챗봇 | `sid`, `message`, `context` |
| `InsightChatRequest` | 인사이트 챗봇 | `sid`, `message`, `personas`, `clusters` |

---

## routers/ — API 엔드포인트

### routers/sessions.py — 세션 관리

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `save_session(req)` | `POST /save-session` | 세션 데이터를 S3에 저장 |
| `get_session(sid)` | `GET /session/{sid}` | S3에서 세션 로드 |
| `list_sessions()` | `GET /sessions` | 전체 세션 목록 (최근 20개) |
| `delete_session(sid)` | `DELETE /delete-session/{sid}` | 세션 삭제 |
| `pipeline_status(sid)` | `GET /pipeline-status/{sid}` | 전체 파이프라인 작업 상태 조회 |

### routers/keywords.py — 키워드 생성

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `generate_keywords(req)` | `POST /generate-keywords` | Claude API로 키워드 생성 + Naver Cafe 검색량 스코어링 |

**로직 상세:**
1. 라운드별 프롬프트 구성 (R1/R2/R3/R3-Expand)
2. Claude API 호출 → JSON 형태 키워드 목록 반환
3. 각 키워드를 Naver Cafe API로 검색 → 결과 수 기반 점수 부여
4. 중복/무효 키워드 필터링 후 점수순 정렬

### routers/crawling.py — 웹 크롤링

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_crawl(req)` | `POST /crawl` | 크롤링 작업 시작 (데몬 스레드) |
| `get_status(sid)` | `GET /status/{sid}` | 크롤링 진행 상태 + 카페 통계 |

**상태 응답 구조:**
- `status`: running / done / error / not_found
- `total`: 수집된 총 건수
- `cafe_stats`: 카페별 수집 통계
- S3 폴백: JobManager에 상태 없으면 S3 데이터로 추정

### routers/preprocessing.py — 전처리

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_preprocess(req)` | `POST /preprocess` | 전처리 작업 시작 (데몬 스레드) |
| `get_preprocess_status(sid)` | `GET /preprocess-status/{sid}` | 전처리 상태 (원본/필터링 건수) |

### routers/labeling.py — 라벨링

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `get_sample(sid, percent)` | `GET /sample/{sid}?percent=2` | 전처리 데이터의 N% 랜덤 샘플 추출 (최대 20건 반환) |

### routers/training.py — 모델 학습

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_train(req)` | `POST /train` | 학습 작업 시작 (데몬 스레드) |
| `get_train_status(sid)` | `GET /train-status/{sid}` | 학습 상태 (phase, progress, 관련/무관 건수) |

### routers/clustering.py — 클러스터링

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_cluster(req)` | `POST /cluster` | 클러스터링 작업 시작 (데몬 스레드) |
| `get_cluster_status(sid)` | `GET /cluster-status/{sid}` | 클러스터 상태 (클러스터별 크기, 키워드, 샘플) |
| `cluster_refine(req)` | `POST /cluster-refine` | 클러스터 유지/병합 정제 |

**상태 응답:**
- 각 클러스터의 `id`, `size`, `keywords`, `keyword_counts`, `samples` 포함
- S3 폴백: JobManager 상태 없으면 S3 데이터에서 직접 구성

### routers/embedding.py — 벡터 임베딩

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_embed(req)` | `POST /embed` | 임베딩 작업 시작 (데몬 스레드) |
| `get_embed_status(sid)` | `GET /embed-status/{sid}` | 임베딩 상태 |

### routers/personas.py — 페르소나 생성

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `start_persona(req)` | `POST /persona` | 페르소나 생성 작업 시작 (데몬 스레드) |
| `get_persona_status(sid)` | `GET /persona-status/{sid}` | 페르소나 상태 (결과 포함) |
| `get_sna_data(sid)` | `GET /sna-data/{sid}` | SNA 그래프 데이터 (노드 + 링크) |

**SNA 노드 구조:**
- `product` 노드: 중심 제품
- `cluster` 노드: 각 클러스터
- `persona` 노드: 각 페르소나 (pain_point, insight 포함)

### routers/chat.py — 챗봇

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `chat_agent(req)` | `POST /chat` | 파이프라인 챗봇 — RAG 검색 + 키워드 추가 지원 |
| `insight_chat(req)` | `POST /insight-chat` | 인사이트 챗봇 — 클러스터/페르소나 수정 지원 |

**chat_agent 특수 기능:**
- Pinecone RAG로 유사 문서 검색 후 컨텍스트 주입
- `ADDED_KEYWORDS:` 플래그로 키워드 자동 추가

**insight_chat 특수 기능:**
- 클러스터 병합/이름 변경 지원
- 페르소나 필드 수정 지원
- `MODIFIED_DATA` JSON 블록으로 변경사항 반환

### routers/search.py — 유사 문서 검색

| 함수 | 엔드포인트 | 설명 |
|------|-----------|------|
| `search_docs(req)` | `POST /search` | Pinecone RAG로 유사 문서 검색 |

---

## services/ — 비즈니스 로직

### services/claude.py — Claude API

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `call_claude(prompt, max_tokens, model, timeout)` | `prompt: str`, `max_tokens: int = 4096`, `model: str = "claude-sonnet-4-20250514"`, `timeout: int = 120` | `str \| None` | Anthropic Claude API 호출. 실패 시 None 반환 |

### services/naver.py — Naver API

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `search_naver_cafe(query, display, start)` | `query: str`, `display: int = 100`, `start: int = 1` | `dict \| None` | Naver Cafe 검색 API 호출. 인증 헤더 포함 |

### services/crawling.py — 크롤링 로직

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `crawl_keywords(config)` | `config: dict` (sid, bk, keywords, target, dateFrom, dateTo, includeCafes, excludeCafes, adFilters) | `int` | Naver Cafe 게시글 대량 수집. 키워드별 최대 1,000건, 500건 단위 배치 S3 저장 |

**config 필드:**
- `sid`: 세션 ID
- `bk`: 메인 키워드 (제품명)
- `keywords`: 검색 키워드 목록
- `target`: 목표 수집 건수
- `dateFrom/dateTo`: 날짜 범위
- `includeCafes`: 포함할 카페 목록
- `excludeCafes`: 제외할 카페 목록
- `adFilters`: 광고 필터 키워드 목록

**크롤링 필터 순서:**
1. 날짜 범위 체크
2. 광고 키워드 필터
3. 제외 카페 필터
4. 포함 카페 필터 (지정 시)
5. 제품명 포함 여부
6. 링크 기준 중복 제거

### services/preprocessing.py — 전처리 로직

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `preprocess_data(config)` | `config: dict` (sid, adFilters, excludeCafes) | `None` | S3에서 크롤링 데이터 로드 → 필터링 → 중복 제거 → 저장 |

**필터링 단계:**
1. 광고 필터 매칭 제거 (제목 + 설명 결합)
2. 제외 카페 매칭 제거
3. 링크 기준 중복 제거
4. 제목 5자 미만 AND 설명 10자 미만 제거
5. 각 문서에 `idx` 인덱스 부여

### services/training.py — ML 학습 로직

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `train_models(config)` | `config: dict` (sid, labeledData) | `None` | 라벨 데이터 로드 → TF/sklearn 선택 → 학습 → 전체 데이터 분류 |
| `_train_tensorflow(sid, texts, labels)` | `sid: str`, `texts: list[str]`, `labels: list[int]` | `None` | LSTM + CNN + GRU 앙상블 학습 (TensorFlow/Keras) |
| `_train_sklearn(sid, texts, labels)` | `sid: str`, `texts: list[str]`, `labels: list[int]` | `None` | LogReg + RF + GB 앙상블 학습 (Scikit-learn 폴백) |

**TensorFlow 모델:**

| 모델 | 레이어 구성 |
|------|------------|
| LSTM | Embedding(10000, 64) → LSTM(64) → Dense(32, relu) → Dropout(0.3) → Dense(1, sigmoid) |
| CNN | Embedding(10000, 64) → Conv1D(64, 5) → GlobalMaxPool → Dense(32, relu) → Dropout(0.3) → Dense(1, sigmoid) |
| GRU | Embedding(10000, 64) → GRU(64) → Dense(32, relu) → Dropout(0.3) → Dense(1, sigmoid) |

**Scikit-learn 폴백:**

| 모델 | 구성 |
|------|------|
| Logistic Regression | TF-IDF(max 5000, ngram 1-2) → LogisticRegression(max_iter=500) |
| Random Forest | TF-IDF → RandomForestClassifier(n_estimators=100) |
| Gradient Boosting | TF-IDF → GradientBoostingClassifier(n_estimators=100) |

**앙상블 로직:**
- 3개 모델 확률 평균 → threshold 0.5 → relevant/irrelevant 분류

### services/clustering.py — 클러스터링 로직

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `run_clustering(config)` | `config: dict` (sid) | `None` | 임베딩 생성 → 최적 k 탐색 → K-means → 키워드 추출 → 저장 |
| `refine_clusters(config)` | `config: dict` (sid, keep, merge) | `dict` | 클러스터 유지/병합 → 재인덱싱 → 키워드 추출 → 정제 데이터 저장 |

**클러스터링 프로세스:**
1. `classified/{sid}/relevant_*.jsonl` 로드
2. Voyage AI 임베딩 (1024차원, 128건 배치)
3. 최적 k 탐색: k = 3 ~ min(15, len/10), 실루엣 점수 최대화
4. K-means 클러스터링 수행
5. TF-IDF 키워드 추출 (max_features=3000, ngram 1-2, 클러스터당 top 10)

**정제 로직:**
- `keep`: 유지할 클러스터 ID 목록
- `merge`: 병합할 클러스터 문자열 (예: "1,3,5" → 첫 번째 ID로 통합)
- 순차적 재인덱싱: 0, 1, 2, ...

### services/personas.py — 페르소나 생성

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `run_persona(config)` | `config: dict` (sid, bk, problemDef) | `None` | 클러스터별 RAG 샘플 → Claude 프롬프트 → 페르소나 JSON 생성 → S3 저장 |

**페르소나 수 결정 로직:**

| 클러스터 크기 | 기본 페르소나 수 | 키워드 다양성 높으면 |
|-------------|----------------|------------------|
| 50건 미만 | 1개 | +1개 |
| 50~200건 | 2개 | +1개 |
| 200건 이상 | 3개 | +1개 |

### services/embedding.py — 벡터 임베딩

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `run_embedding(config)` | `config: dict` (sid) | `None` | Pinecone 인덱스 생성 → Voyage 임베딩 → 배치 upsert |

**Pinecone 설정:**
- 인덱스명: `cx-{sid}`
- 차원: 1024
- 메트릭: cosine
- 스펙: Serverless (aws, us-east-1)

**메타데이터:** title, desc, kw, cafe, cluster

### services/voyage.py — Voyage AI 임베딩

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `get_embeddings(texts)` | `texts: list[str]` | `list[list[float]]` | Voyage multilingual-2 모델로 임베딩 생성 (128건 배치, 텍스트 2000자 절삭) |

### services/pinecone_svc.py — Pinecone 검색

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `search_similar(sid, query, top_k)` | `sid: str`, `query: str`, `top_k: int = 5` | `list[dict]` | 쿼리 임베딩 → Pinecone 검색 → 메타데이터 포함 결과 반환 |

### services/s3.py — AWS S3 입출력

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `load_data(prefix)` | `prefix: str` | `list[dict]` | S3 프리픽스 하위 모든 JSONL 파일 로드 후 합산 |
| `save_jsonl(key, data)` | `key: str`, `data: list[dict]` | `None` | JSONL 형식으로 S3 저장 |
| `save_json(key, data)` | `key: str`, `data: dict` | `None` | JSON 형식으로 S3 저장 |
| `load_json(key)` | `key: str` | `dict \| None` | S3에서 JSON 로드 |
| `list_objects(prefix)` | `prefix: str` | `list[dict]` | S3 프리픽스 하위 객체 목록 조회 |
| `list_prefixes(prefix)` | `prefix: str` | `list[str]` | S3 프리픽스 하위 폴더 목록 조회 |
| `delete_object(key)` | `key: str` | `None` | S3 객체 삭제 |

---

## jobs/ — 작업 상태 관리

### jobs/manager.py — JobManager

스레드 안전한 인메모리 작업 상태 추적 클래스.

| 메서드 | 파라미터 | 반환 | 설명 |
|--------|---------|------|------|
| `get(job_type, sid)` | `job_type: str`, `sid: str` | `dict` | 작업 상태 조회. 없으면 `{"status": "not_found"}` |
| `set(job_type, sid, data)` | `job_type: str`, `sid: str`, `data: dict` | `None` | 작업 상태 설정/교체 |
| `update(job_type, sid, **kwargs)` | `job_type: str`, `sid: str`, `**kwargs` | `None` | 작업 상태 부분 업데이트 |

**작업 유형 (job_type):**
- `crawl`, `preprocess`, `train`, `cluster`, `embed`, `persona`

**상태 값 (status):**
- `running`, `done`, `error`, `not_found`

**전역 싱글턴:** `job_manager = JobManager()`

---

## utils/ — 유틸리티

### utils/text.py — 텍스트 정제

| 함수 | 파라미터 | 반환 | 설명 |
|------|---------|------|------|
| `clean_text(t)` | `t: str` | `str` | HTML 태그 제거 + HTML 엔티티 디코딩 (&amp;, &lt;, &gt;) |
| `get_llm_predictions(batch, bk, problem_def)` | `batch: list`, `bk: str`, `problem_def: str` | `list[int]` | Claude API로 문서 관련성 분류 (0/1 예측 목록 반환) |

---

## S3 데이터 경로 정리

| 경로 패턴 | 단계 | 형식 | 설명 |
|-----------|------|------|------|
| `sessions/{sid}/session.json` | 시작~라벨링 | JSON | 세션 메타데이터, 키워드, 라벨 데이터 |
| `crawl/{sid}/*.jsonl` | 크롤링 | JSONL | 수집된 게시글 (500건 단위 배치) |
| `preprocessed/{sid}/{ts}.jsonl` | 전처리 | JSONL | 필터링 완료된 문서 |
| `classified/{sid}/relevant_{ts}.jsonl` | 학습 | JSONL | 관련 문서 (relevance_score 포함) |
| `classified/{sid}/irrelevant_{ts}.jsonl` | 학습 | JSONL | 무관 문서 |
| `clusters/{sid}/cluster_{id}_{ts}.jsonl` | 클러스터링 | JSONL | 초기 클러스터 데이터 |
| `clusters_refined/{sid}/data_{ts}.jsonl` | 클러스터링 | JSONL | 정제된 클러스터 데이터 |
| `personas/{sid}/result_{ts}.json` | 페르소나 | JSON | 페르소나 결과 |

---

## 전체 API 엔드포인트 요약

| 단계 | Method | Endpoint | 비동기 | 설명 |
|------|--------|----------|--------|------|
| 시작 | POST | `/save-session` | - | 세션 저장 |
| | GET | `/session/{sid}` | - | 세션 로드 |
| | GET | `/sessions` | - | 세션 목록 |
| | DELETE | `/delete-session/{sid}` | - | 세션 삭제 |
| | GET | `/pipeline-status/{sid}` | - | 전체 파이프라인 상태 |
| 키워드 | POST | `/generate-keywords` | - | 키워드 생성 |
| 크롤링 | POST | `/crawl` | O | 크롤링 시작 |
| | GET | `/status/{sid}` | - | 크롤링 상태 |
| 전처리 | POST | `/preprocess` | O | 전처리 시작 |
| | GET | `/preprocess-status/{sid}` | - | 전처리 상태 |
| 라벨링 | GET | `/sample/{sid}` | - | 랜덤 샘플 |
| 학습 | POST | `/train` | O | 학습 시작 |
| | GET | `/train-status/{sid}` | - | 학습 상태 |
| 클러스터링 | POST | `/cluster` | O | 클러스터링 시작 |
| | GET | `/cluster-status/{sid}` | - | 클러스터 상태 |
| | POST | `/cluster-refine` | - | 클러스터 정제 |
| 임베딩 | POST | `/embed` | O | 임베딩 시작 |
| | GET | `/embed-status/{sid}` | - | 임베딩 상태 |
| 페르소나 | POST | `/persona` | O | 페르소나 생성 |
| | GET | `/persona-status/{sid}` | - | 페르소나 상태 |
| | GET | `/sna-data/{sid}` | - | SNA 그래프 데이터 |
| 챗봇 | POST | `/chat` | - | 파이프라인 챗봇 |
| | POST | `/insight-chat` | - | 인사이트 챗봇 |
| 검색 | POST | `/search` | - | 유사 문서 검색 |
| 공통 | GET | `/health` | - | 헬스체크 |
