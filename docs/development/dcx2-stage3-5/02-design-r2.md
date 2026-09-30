# 02 · 설계 r2 — DCX 2.0 3~5단계 개편 (전처리 · 라벨링 · 학습)

> **r2 = 승인된 [`02-design.md`](02-design.md)(2026-09-30 설계 승인, sha256 21a06dd…)에 계획 단계 사용자 결정(D-143 경계 사례 없음 · D-144 τ · α 제외 · D-145 캘리브레이션 제외)을 반영한 판이다.** 하네스는 승인된 원본을 바꾸지 못하게 하므로 원본은 그대로 두고, 구현은 이 r2를 따른다. 변경 요약은 [`03-plan.md`](03-plan.md) "설계 변경" 절. 계획 승인 = 이 r2 승인.

- 기준: 승인된 [`01-brainstorm.md`](01-brainstorm.md) (2026-09-30 제품 승인) · 결정 원장 [`decision-log.md`](decision-log.md)
- 0~2단계 설계 [`../dcx2-stage0-2/02-design.md`](../dcx2-stage0-2/02-design.md)의 원칙 · 저장 구조 · UI 규칙(10절)을 그대로 이어받는다. 여기서는 달라지거나 새로 생기는 것만 적는다.
- **승인된 01과 달라진 점(설계 · 계획 중 사용자 결정):** 01 3절 14 · 15(검수량 6절차 · α 즉시 재계산)와 AC-12 · AC-13의 α 부분은 D-144 · D-145로 빠진다. 검수 큐는 등급 불일치 · 판정 실패만(D-143). 이 밖에: 01의 3절 6 · 27("6.5단계 적재", "6.5 Pinecone 조회")은 D-121로 로컬 검색 하나가 되고 6.5단계 적재는 없어진다. 01의 3절 19(scikit-learn)는 D-130(PyTorch 멀티태스크 MLP 앙상블)으로 바뀐다. 임베딩 모델은 D-129(`voyage-4`). 수용 기준 AC-05("6.5단계 적재가 임베딩 API를 다시 부르지 않는다")는 "6.5단계 적재가 없다"로 읽는다.
- 표기: `AC-xx`는 01 문서의 수용 기준, `D-xxx`는 결정 기록. 이 문서의 새 결정은 12절에 모으고 decision-log D-12x로 옮긴다.

---

## 1. 전체 구조

```
[프론트 Next.js]  … crawling ─ preprocess ─ labeling ─ training ─ (clustering 이후 기존 화면)
                  공통: KnownInsightsDrawer (모든 단계 화면)
        │ REST
[백엔드 FastAPI]
  app/prep/      3단계: 규칙 필터 · 정형 문구 사전 · 정제 두 갈래 · Kiwi 토큰 · stage_3.json
  app/vectors/   3단계: 임베더(voyage | fake) · float16 샤드 저장소 · doc_id 조회 · 로컬 코사인 검색
  app/label/     4단계: 라벨 스키마 · 등급 규칙 · Jev 클라이언트 · GPT 라벨러 · 판정 캐시 · 합치기 ·
                        라우팅 · 감사 통계 · stage_5.json(라벨 부분)
  app/model/     5단계: 다중 헤드 학습 · 확률 보정 · 모델 저장소 · 추론 · 감시 재판정
  app/known/     공통: known_insights 저장 · 문장 임베딩 · RAG 검색 제외 필터
  app/work/      공통: 긴 작업 워커(별도 프로세스) · SQLite 작업표 · heartbeat · 이어 하기
  app/llm/       (0~2단계) codex_exec · openai_api · fake — GPT 라벨러가 그대로 쓴다
        │
[로컬 디스크 data/]
  sessions/{sid}/versions/vN/…     버전별 결정 · 사람 라벨 · 설정 (통째 복사, D-078)
  derived/{sid}/{collectionId}/{prepKey}/   3단계 결과 = 모듈, 만든 뒤 변경하지 않음 (D-103)
  judge/{sid}/{prepKey}/{labeler}/{qver}/   LLM 판정 캐시 = 모듈, 버전끼리 공유 (D-120)
  models/{modelId}/                분류 모델 저장소 = 세션 밖 (D-108)
  work/{sid}/{runId}/              워커 작업표 · 로그
```

**원칙 (0~2단계와 같음 + 추가)**
- 판단이 필요 없는 일(필터 · 등급 · κ · 라우팅 · 확률 계산)은 결정론적 코드다. LLM · Jev는 태그 판정만 한다.
- 비싸거나 오래 걸리는 결과(수집본 · 3단계 벡터 · LLM 판정)는 **버전 밖 모듈**로 두고 버전은 가리키기만 한다. 버전을 새로 만들어도 다시 사지 않는다.
- 외부 호출(Voyage · Jev · codex · OpenAI)은 어댑터 뒤에 두고, 테스트는 가짜로 돈다. 키가 없으면 "미연결"로 표시하고 가짜 없이 실제 실행은 막는다(QA · 시연은 `fake` 설정으로).

---

## 2. 데이터 모델

### 2.1 `session.json` 추가 키 (schemaVersion 2 유지)

```jsonc
{
  "knownInsights": [ /* 2.6 */ ],
  "prep": {
    "config": { /* 3.1 PrepConfig */ },
    "derivedRef": { "collectionId": "c1", "prepKey": "p_3f9a…" },  // 3단계 결과 모듈
    "status": "none | running | done | failed", "savedAt": "…"
  },
  "labeling": {
    "mode": "llm | model",               // LLM 라벨 구간 / 분류 모델 구간 (D-108)
    "modelId": null,                     // mode=model일 때
    "judgeRefs": { "jev": "judge/…/jev/q1", "gpt": "judge/…/gpt/q1" },
    "started": true, "lastSeenAt": "…",
    "audit": [{ "round": 1, "n": 50, "kappaAI": {…}, "at": "…" }],
    "labelerAccuracy": { "jev": {…}, "gpt": {…}, "n": 150 },   // 감사 정답 누적 기준 (D-145)
    "selfConsistency": { "agree": 0.9, "n": 20 },               // 감사 re-issue
    "definitionCheck": { "needed": false, "reason": null }      // κ_AI 하락 신호
  },
  "training": { "modelId": null, "status": "none | running | done | failed", "metrics": {…} },
  "drafts": { "prep": {…}, "labeling": {…}, "training": {…} }
}
```

- τ · α · 캘리브레이션은 이번 범위에서 뺐다(D-144 · D-145). `confidence`는 계속 계산해 저장한다.
- 사람 라벨 · 감사 결과는 버전 폴더의 `labels.sqlite`(2.4)에 둔다. 100만 행을 JSON에 넣지 않는다.
- 옛 세션(`schemaVersion` 없음): 3~5단계 새 화면은 "구버전 세션은 새 라벨링을 쓸 수 없습니다"를 보여 주고 기존 결과만 열람한다. 옛 `labeledData[].label` 0/1은 `anchor`로 읽는다(AC-16, 2.4 호환 뷰).

### 2.2 3단계 결과 모듈 `derived/{sid}/{collectionId}/{prepKey}/`
```
manifest.json      {collectionId, prepKey, config, embedder: {name, model, dim}, analyzer, status, counts, createdAt}
docs/part-00001.jsonl       전처리 통과 문서(원문 정제본 · 호환 필드 desc/cafe/link 포함), 5,000건 샤드
tokens/part-00001.jsonl     {doc_id, tokens[]}  — 토큰 경로(문장부호 삭제 후 Kiwi)
vectors/shard-00001.f16     float16 [n × 1024] 원시 배열 (10,000건 단위)
vectors/ids.jsonl           {doc_id, shard, row}  — 조회 색인
stage_3.json                3단계 산출 계약 (3.5)
```
- `prepKey` = `hash(collectionId + 규칙 설정 정규화 JSON + 사전 내용 + 임베더 이름·모델 + 분석기 버전)`. 같은 수집본 · 같은 규칙이면 같은 키 → 새 버전이 그대로 재사용한다(AC-06).
- 임베딩 실패 건은 0벡터 행 + `ids.jsonl`에 `"failed": true`. 검색 · 학습에서 0벡터는 빼고 센다(AC-07).
- 호환: 3단계가 끝나면 `preprocessed/{sid}/{ts}.jsonl`에도 같은 문서를 한 번 써서 기존 코드가 읽는 경로를 유지한다.

### 2.3 라벨 (`app/label/schema.py`)
```jsonc
{
  "doc_id": "nc_…",
  "anchor": true,
  "sem": { "sense": 0, "feel": 1, "think": 0, "act": 1, "relate": 0, "outcome": 0 },
  "situation": true,
  "reason_code": "ad | no_needs | pure_criticism | other | null",   // Non일 때만 값
  "signal": "pain | unmet | workaround | delight | none | null",    // Core·Supporting일 때만 값, GPT 단독 (D-116)
  "evidence_level": "core | supporting | non",   // 규칙 계산 (3.2의 rule_version과 함께 저장)
  "confidence": 0.87,
  "source": "agreed | human | model",
  "votes": {
    "jev": { "probs": { "anchor": 0.96, "sense": 0.12, …, "relate": 0.08, "outcome": 0.31, "situation": 0.9 },
             "reason_probs": { "ad": 0.01, …, "not_non": 0.95 }, "model": "jev-1.13.0" },
    "gpt": { "tags": { … 0/1 … }, "reason_code": null, "signal": "workaround", "backend": "codex_exec" }
  },
  "route": "accepted | escalated:<reason> | audited",
  "rule_version": "r1", "questions_version": "q1"
}
```

### 2.4 버전 폴더의 `labels.sqlite`
| 테이블 | 주요 컬럼 | 비고 |
|---|---|---|
| `final` | doc_id PK, level, confidence, source, route, tags_json, reason_code, signal, rule_version | 합친 결과(3.4). 판정 캐시가 바뀌면 다시 만든다 |
| `human` | doc_id, labeler, mode(`escalate`/`audit`/`reissue`), tags_json, reason_code, signal, submitted_at | 한 건 제출 = 한 행 즉시 커밋(AC-14) |
| `audit_set` | round, doc_id, picked_at | 채택분 무작위 |
| `queue` | doc_id PK, reason, priority, status(`open`/`done`/`skipped`) | escalate 큐 |
- 버전 복사(D-078) 때 이 파일도 통째 복사한다. "4단계부터 다시"면 `human`은 남기고 `final` · `queue`는 `stale`로 표시한다. 판정 캐시는 복사하지 않고 같은 것을 가리킨다.

### 2.5 판정 캐시 `judge/{sid}/{prepKey}/{labeler}/{qver}-{ctxKey}/votes.sqlite` (D-120, O5)
- `votes(doc_id PK, payload_json, status(pending/done/bad), attempts, last_error, run_id, at)`.
- 키는 "어떤 문서 집합 × 어떤 라벨러 × 어떤 질문 버전 × 판정 맥락(`ctxKey` = 한줄 정의 · 질문 원문 · 모델 해시)"이다. 한줄 정의를 바꾸면 새 캐시가 생긴다. 질문 문구 · 모델 · 묶음 크기를 바꾸면 `qver`가 바뀌어 새 캐시가 생긴다. 같은 조건이면 버전을 몇 번 새로 만들어도 LLM · Jev를 다시 부르지 않는다.

### 2.6 `knownInsights[]` (`app/known/models.py`)
```jsonc
{ "id": "ki_01", "type": "statement | doc", "text": "야간 소음이 불만 1순위다",
  "doc_id": null, "from": "stage0 | drawer | rag | prev_session", "createdAt": "…", "vectorRow": 3 }
```
- 0단계 `ProjectContext.knownInsights: list[str]`는 그대로 두고, 세션 생성 시 `from: stage0` 항목으로 복사한다(이미 0~2단계에서 `session.json.knownInsights`에 객체로 저장 중). 옛 문자열 목록은 `statement`로 읽는다.
- 문장 항목 벡터는 버전 폴더 `known_vectors.f16`에 추가 시 1회 계산해 둔다. 원문 항목은 3단계 벡터를 `doc_id`로 찾아 쓴다.

---

## 3. 3단계 · 전처리 + 임베딩

### 3.1 `PrepConfig`
```jsonc
{ "adFilter": [...], "excludeSources": [...], "minBodyChars": 10,   // 0~2단계 D-084~D-086 그대로
  "boilerplate": { "naver_cafe": ["카페 회원이 되시면 …"], "naver_blog": ["공감", "…"], "clien": [], "ppomppu": [], "youtube": [] },
  "analyzer": "kiwi", "tokenPos": ["NNG", "NNP", "VV", "VA", "XR"],
  "embedder": "voyage | fake", "embedModel": "voyage-4", "embedDim": 1024 }   // D-129
```
- 정형 문구 사전 기본값은 `app/prep/boilerplate.v1.json`(녹화 응답에서 뽑은 채널별 목록)이고, 화면에서 추가 · 삭제한 값은 세션 설정에 저장한다(AC-02).

### 3.2 처리 순서 (`app/prep/pipeline.py`, 워커 `prep`)
1. 수집본 문서 읽기(0~2단계 `_crawl_docs` 그대로, parent 합치기 · `doc_id` 중복 제거).
2. HTML 정제(전 경로) → 정형 문구 치환 제거(채널 사전, 본문 · 댓글 각각) → **원문 정제본**.
3. 규칙 필터(원문 정제본의 본문 + 댓글 기준): 광고어 · 제외 출처 · 길이. 규칙별 제거 건수를 센다. 타겟 무관 단어 규칙은 없다(AC-01).
4. 통과 문서를 `docs/`에 쓴다(호환 필드 포함).
5. 토큰 경로: 원문 정제본 → 문장부호 · 특수문자 삭제 → Kiwi 형태소 → 품사 필터 → `tokens/`(AC-03 · AC-04).
6. 임베딩 경로: 원문 정제본(제목 + 본문 + 댓글, 2,000자 절단 — 기존 `voyage.py` 규칙)을 128건씩 임베딩 → `vectors/`. 실패 배치는 3회 재시도 후 0벡터(AC-07).
- 단계 4 · 5 · 6은 샤드 단위로 진행을 기록한다. 강제 종료 후 재시작하면 끝난 샤드를 건너뛴다.
- 문장부호 삭제는 토큰 경로에만 있고, 라벨러 · 임베더 입력은 원문 정제본이다(AC-03 테스트: 같은 문서의 두 경로 출력 비교).

### 3.3 임베더 (`app/vectors/embedder.py`)
- `voyage`: 기존 `services/voyage.py`를 감싸고 모델을 `voyage-4`(1024차원, `output_dimension=1024`)로 바꾼다(D-129). 키가 없으면 `unconnected`.
- `fake`: `sha256(text)`로 시드한 정규분포 벡터(1024D, 정규화). 같은 글 → 같은 벡터. 테스트 · 오프라인 시연용.
- 벡터 저장소(`app/vectors/store.py`): `get(doc_ids) -> ndarray`, `iter_shards()`, `search(query_vec, top_k, allow=set|None) -> [(doc_id, score)]`(샤드별 행렬곱, 100만 건 약 1~2초).

### 3.4 6 · 6.5단계 연결 (AC-05)
- `services/clustering.py`: 문서에 `doc_id`가 있고 세션에 `derivedRef`가 있으면 `get_embeddings` 대신 벡터 저장소에서 읽는다. 없으면(옛 세션) 기존 경로.
- **6.5단계(Pinecone 적재)는 없앤다(D-121).** `services/embedding.py`의 적재 작업은 새 세션에서 "3단계 벡터 사용"으로 즉시 완료 처리하고, 화면의 임베딩 단계는 완료 표시만 남긴다. 옛 세션도 같은 처리(적재된 Pinecone 인덱스는 더 쓰지 않음).
- **RAG 검색은 로컬 벡터 검색 하나다(D-121 확정, 설정 없음).** `services/pinecone_svc.py`를 `app/vectors/search.py`로 대체한다. 활성 버전의 5단계 결과(없으면 4단계 `final`)에서 Core + Supporting 문서만 골라 3단계 벡터와 코사인 비교한다. 여러 질의는 행렬 한 번으로 묶는다(페르소나 생성). 질의문 임베딩만 임베더를 1회 부른다. `pinecone` 의존성과 `pinecone_api_key` 설정을 없앤다.
- 검색할 수 없으면 빈 목록을 숨기지 않고 사유를 돌려준다: `no_vectors`(3단계 전) · `no_labels`(4단계 전) · `all_known`(아는 얘기로 모두 제외) · `embedder_unconnected`.

### 3.6 화면 (`/pipeline/preprocess`, 디자인 리뷰 1bA · 목업 s1)
```
[페이지 제목 · 임시 저장 · 전처리 실행(primary)]
┌ 규칙 필터 (8칸) ───────────────┐ ┌ 만들어지는 것 (4칸) ┐
│ 광고어 · 제외 출처 · 최소 본문  │ │ 정제본 · 토큰 · 임베딩│
├ 채널 정형 문구 (탭: 채널별) ────┤ ├ 예상 ─────────────┤
│ 문구 · 출처 · 치환 건수 · 삭제  │ │ 약 31만 건 · 2시간  │
└ + 문구 추가                    ┘ └───────────────────┘
실행 후: ┌ InsightCard "318,204건이 라벨링으로 넘어갑니다" ┐ ┌ 규칙별 제거 막대 ┐
         └ 해석 · 근거 메타 · 다음 행동 "라벨링으로"      ┘ └────────────────┘
```
- 실행 전에는 설정이 주인공, 실행 후에는 결과 카드가 주인공이다. 결과가 있으면 결과 카드가 설정 위로 올라가고 설정은 접힌다("규칙 수정하고 다시 실행").
- 판단이 있는 화면이므로 페이지 제목은 section.title(24/34/700), 결과 수치만 insight.display(40/52/800).

### 3.5 `stage_3.json`
```jsonc
{ "original": 412330, "after": 318204,
  "removed": { "ad": 51200, "excluded_source": 3100, "duplicate": 812, "too_short": 39014 },
  "boilerplate_replaced": { "naver_cafe": 88120, "naver_blog": 12004 },
  "tokens_written": 318204, "embedded": 318150, "embed_failed_zero_vector": 54,
  "prepKey": "p_3f9a…", "embedder": "voyage-multilingual-2", "analyzer": "kiwi-0.x", "at": "…" }
```

---

## 4. 4단계 · 라벨링

### 4.1 흐름
```
[방식 선택] ─ LLM 라벨 ──▶ ① "라벨링 시작" → Jev · GPT 전량 판정(판정 캐시)
            │             ② 두 표가 모이면 합치기 → 등급 · confidence
            │             ③ 등급이 엇갈리거나 판정에 실패한 문서만 검수 큐 → 사람 판정
            │             ④ 채택분 무작위 감사 → κ_AI · 라벨러 정확도 누적
            └ 분류 모델 ──▶ 모델 추론(5.4) → 확신 구간 채택 · 애매 구간 사람 큐 · 1% 감시
```
- **τ · α · 캘리브레이션은 이번 범위에서 뺐다 (D-144 · D-145, 엔지니어링 리뷰 D5 · D6 사용자 결정).** 두 라벨러가 등급에 합의하면 채택, 엇갈리면 사람이 본다. 라벨러가 얼마나 맞는지는 무작위 감사가 잰다.
- **시작 버튼은 "라벨링 시작" 하나 (D-136 수정).** 누르면 Jev · GPT 판정 워커를 함께 띄우고 개요로 간다. 누르기 전 버튼 옆에 한 줄 예상: "대상 318,204건 · Jev 약 44시간 · 예상 비용 $10 · GPT는 codex 사용량 한도 안에서".
- 태그 정의를 고치면 질문 버전(`qver`)이 바뀌어 그때까지의 판정을 다시 해야 한다. 그래서 **첫 감사 라운드는 채택 1,000건에서** 만들고(이후 1만 건마다), 첫 라운드가 끝나면 개요에 "태그 정의를 고칠 일이 있으면 지금 고치세요(판정 진행 N건)" 안내를 한 번 띄운다.

### 4.2 등급 규칙 (`app/label/rule.py`, D-104)
- `grade(tags) -> "core" | "supporting" | "non"`
  - core = anchor ∧ Σsem ≥ 2 ∧ situation
  - supporting = anchor ∧ Σsem ≥ 1 ∧ ¬core
  - non = 나머지
- `grade_probs(p) -> {core, supporting, non}`: 필드 독립 가정. P(Σsem ≥ k)는 6개 베르누이의 분포를 DP로 계산한다.
  - P(core) = P(a) · P(≥2) · P(s)
  - P(supporting) = P(a) · (P(≥1) − P(≥2) · P(s))
  - P(non) = 1 − 나머지
- 경계 사례 규칙(기획안 8절 ④ "태그 하나만 뒤집혀도 등급이 바뀌는 건 → escalate")은 두지 않는다(D-143, 엔지니어링 리뷰). 문자 그대로면 anchor 하나로 모든 Core · Supporting이 해당해 검수가 전량이 된다.
- `RULE_VERSION = "r1"`. 기획안 6절 표 6행이 고정 테스트다(AC-08). Core 강화(B-101)는 이 파일 한 곳만 바꾼다.
- 화면은 `POST /label/rule/preview {tags}` → `{level}`를 부른다(프론트에 규칙을 다시 쓰지 않음).

### 4.3 질문 정의 (`app/label/questions.q1.json`)
- 태그 정의 문구 한 벌을 두 라벨러가 같이 쓴다. 필드마다 `instructions`(한국어, 1,800자 이내) · 1 조건 · 0 예시("감정어 단독은 0", "대상과 무관한 행동은 0").
- 공통 머리: 0단계 `oneLiner` 한 줄(기획안 횡단 규칙). 도메인 예시는 넣지 않는다(AC-11).

### 4.4 Jev 클라이언트 (`app/label/jev.py`)
- 요청 1회 = 문서 1건 = 질문 8개(D-116):

  | 이름 | 형식 | 선택지 |
  |---|---|---|
  | `anchor` · `sense` · `feel` · `think` · `act` · `situation` | `noul` | – |
  | `relate_outcome` | `choice` | `none` · `relate` · `outcome` · `both` |
  | `reason_code` | `choice` | `ad` · `no_needs` · `pure_criticism` · `other` · `not_non` |
- 되살리기: P(relate) = p(relate) + p(both), P(outcome) = p(outcome) + p(both) (AC-09).
- `state` = `"[맥락] {oneLiner}\n[제목] …\n[본문] …\n[댓글] …"`, 직렬화 8,000자 이내로 댓글 → 본문 끝 순으로 자른다(잘랐으면 `truncated: true` 기록).
- 속도: 키당 분당 120회를 지키는 제한기(0~2단계 `ChannelLimiter` 재사용). 키를 여러 개 설정하면 키마다 제한기를 둔다.
- 오류: 401 → `unconnected` 표시 · 워커 정지 / 402 → "Jev 잔액이 부족합니다" · 워커 일시 정지 / 422 → 해당 문서 `bad` 격리 / 429 · 502 → 지수 백오프 재시도(최대 5회), `Idempotency-Key = {doc_id}:{qver}`로 이중 과금 방지.
- 응답의 `model` 값을 `votes.jev.model`에 남긴다. 기본 `jev-latest`, 설정으로 고정 버전.
- 가짜 Jev(`fake_jev.py`): 텍스트 해시로 결정되는 확률 + 테스트가 지정한 고정 답.

### 4.5 GPT 라벨러 (`app/label/gpt.py`, D-113)
- LLM 공통 층 과업 `label_gpt`. 기본 백엔드 `codex_exec`(`run_many`), 설정으로 `openai_api`.
- 작업 1건 = 문서 N건(기본 20, 설정값). 출력 스키마: `{items: [{doc_id, anchor, sem{…}, situation, reason_code, signal}]}`. `doc_id` 누락 · 중복 · 여분은 스키마 오류로 `bad/` 격리 후 재시도(AC-09).
- 프롬프트 `app/label/prompts/gpt_label.q1.md`: 첫 줄 `oneLiner` → 4.3 태그 정의 원문 → 문서 묶음 → 출력 형식. `signal`은 "등급이 Core · Supporting일 때만, 6차원 태그를 근거로" 고르게 한다(D-116).
- 사용량 한도로 codex가 실패하면 워커가 해당 작업을 `pending`으로 되돌리고 멈춘다. 화면: "GPT 판정이 사용량 한도로 멈췄습니다. 잠시 뒤 이어서 진행하거나 설정에서 API 경로로 바꾸세요."

### 4.6 판정 워커 (`app/work/judge.py`, 워커 종류 `judge`)
- `python -m app.work.worker judge --sid --version --labeler {jev|gpt}`. 라벨러마다 따로 띄워 동시에 돈다.
- 작업표는 판정 캐시 `votes.sqlite` 자체다. pending 행을 lease → 호출 → 결과 쓰기 + `done` 커밋. 0~2단계 워커 규칙(pid 잠금 · heartbeat 10초 · 죽은 lease 회수 · 배치 커밋)을 `app/work/`로 옮겨 공용화한다(AC-10).
- 진행 · 예상 완료: Jev는 `남은 건수 / (120 × 키 수)`분, GPT는 최근 10분 처리 속도 기준. 예상 Jev 토큰 = Σ ceil(len(요청 JSON)/4) → 예상 비용 표시.

### 4.7 합치기 · confidence (`app/label/merge.py`)
- 필드별 최종값: 두 라벨러가 같으면 그 값, 다르면 Jev 값(확률이 있으므로) + `disagree` 표시.
  - Jev 값 = p ≥ 0.5. reason_code는 최대 확률 선택지(`not_non`이면 null).
  - `signal`은 GPT 값 그대로.
- `confidence` = (8개 등급 필드 일치 수 / 8) × min(해당 필드의 Jev 확신도 max(p, 1−p)) 〔튠, 기획안 7절〕.
- 등급 = `grade(최종 태그)`. 두 라벨러 각자의 등급(Jev는 p≥0.5 태그로)이 다르면 `grade_mismatch`.
- 한 라벨러만 끝난 문서는 합치지 않는다(대기).

### 4.8 감사 통계 (`app/label/audit.py`, D-145)
- **라벨러 성능:** 감사 정답(사람 independent 판정) 누적 대비 Jev · GPT 각각의 필드별 정확도 · κ(기획안 12절 미결 1의 측정). `relate` · `outcome`은 합친 질문이라 따로 표시한다(D-116 확인 항목). 표본 수를 함께 보여 준다("감사 150건 기준").
- **자기 일관성:** 감사 라운드마다 이전 감사 문서 중 2건을 판정 내용을 숨긴 채 다시 보여 준다(re-issue). 같은 답 비율을 누적한다.
- 캘리브레이션 · τ · α · δ는 두지 않는다. `confidence`(4.7)는 저장만 한다(학습 가중치 · 나중에 τ를 되살릴 때 사용).

### 4.9 라우팅 (`app/label/route.py`)
- 순서대로 첫 번째로 맞는 사유 하나를 붙인다: `labeler_failed` → `grade_mismatch` → 없으면 `accepted`(D-143 · D-144).
- `queue` 우선순위: 사유 순서 → confidence 오름차순.
- 예상 소요: 큐 건수 × 한 건 평균 제출 시간(이 세션에서 측정, 처음엔 10초).
- 개요에 등급 불일치율(큐 건수 / 합친 문서)을 숫자로 보여 준다.

### 4.10 감사 · 정의 점검 신호 (`app/label/audit.py`)
- 채택 1,000건에서 첫 라운드, 이후 새로 `accepted` 1만 건(설정값)마다, 또는 사용자가 "감사 라운드 만들기"를 누르면 채택분에서 무작위 50건을 뽑는다.
- independent 모드로 사람이 라벨하면 라운드별 κ_AI(필드별 · 등급)를 계산해 `labeling.audit[]`에 쌓고, 4.8의 라벨러 성능을 갱신한다.
- 정의 점검 신호: κ_AI(등급)가 두 라운드 연속 하락 **그리고** 0.75 아래. 신호가 켜지면 배너 "최근 감사에서 일치도가 두 번 연속 떨어졌습니다. 태그 정의를 확인하세요." 자동으로 판정을 멈추지 않는다.
- 감사 사람 라벨이 채택 라벨과 다르면 그 문서는 사람 값으로 바꾼다(`source=human`).

### 4.11 라벨링 화면 (`/pipeline/labeling`)
- **첫 화면 = 개요 탭 + "지금 할 일" 카드 (디자인 리뷰 1A).** 개요 맨 위에 InsightCard 하나를 두고, 상황에 따라 문구 · 버튼 하나만 바뀐다. 우선순위(위가 먼저):
  1. 판정 워커 멈춤(잔액 · 사용량 한도 · 미연결) → "Jev 잔액이 부족해 판정을 멈췄습니다" + "이어서 진행"
  2. 정의 점검 신호 → "최근 감사에서 일치도가 두 번 연속 떨어졌습니다" + "태그 정의 보기"
  3. 검수 큐 > 0 → "사람이 볼 문서가 214건 있습니다" + "검수 시작"(예상 시간 포함)
  4. 감사 라운드 대기 → "채택 라벨 50건을 확인하세요" + "감사 시작"
  5. 판정 진행 중이고 할 일 없음 → "판정 중입니다 · 예상 완료 10. 1. 16:40" (버튼 없음)
  6. 전부 끝남 → "라벨링이 끝났습니다" + "학습으로"
  - 라벨링 시작 전에는 이 카드 자리에 방식 선택 + "라벨링 시작" + 예상 한 줄이 온다.
- "지난 접속 이후" 변화(새로 판정 · 채택 · 큐에 쌓인 건수)를 카드 해석 문장에 넣는다. 기준 시각은 이 버전의 `labeling.lastSeenAt`(화면을 열 때 갱신).
- 개요의 나머지 순서: 불일치율 · 채택 · 큐 요약(오른쪽) → 전량 판정 진행 → 등급 분포 → 라벨러 성능 표(감사 기준).
- 상단: 라벨링 방식 · 임시 저장 · 저장(보조 버튼, D-137).
  - **방식은 "라벨링 시작" 전에 한 번만 고른다 (디자인 리뷰 7A, D-139).** 시작 전에는 선택(LLM 라벨 / 분류 모델 + 모델 선택, 모델이 없으면 분류 모델 비활성), 시작 뒤에는 "LLM 라벨" 배지만 보인다. 바꾸려면 "4단계부터 다시"로 새 버전을 만든다. 이전 버전 결과는 그대로 남는다.
- 탭 3개:
  1. **개요**: 판정 진행(Jev · GPT 각각 진행 막대 · 예상 완료 · 예상 Jev 비용 · 일시 정지/이어서) · 불일치율 · 채택 · 큐 요약 · 등급 분포 · 라벨러 성능 표.
  2. **검수 큐**: 기획안 9절 화면. 사유 배지 · 원문 · anchor · 6차원 토글 · 상황 · signal · Non 사유 · **계산 등급 실시간 표시** · 제출(= 저장) · 건너뛰기. 제출 뒤에만 "Jev · GPT와 엇갈린 필드" 표시(앵커링 방지).
  3. **감사**: 라운드 목록 · κ_AI 추이 · 새 라운드 · independent 모드 판정(AI 값 숨김, 태그 정의 옆 표시) · re-issue(라운드마다 이전 감사 문서 2건).
- 키보드: 1~6 = 6차원 토글, A = anchor, S = 상황, Enter = 제출, → = 건너뛰기.
  - **단축키 범위 (디자인 리뷰 6A, D-138):** 입력칸 · 텍스트 영역 · 열린 패널(Known Insight 등) · 팝오버에 포커스가 있으면 단축키를 끈다. 판정 카드 영역에 포커스가 있을 때만 동작한다.
  - **읽어 주기:** 계산 등급이 바뀌면 `aria-live="polite"` 영역이 "등급 Supporting으로 바뀜"을 읽는다. 제출 뒤 다음 건이 열리면 포커스는 원문 문단으로 간다.

### 4.12 여정 (디자인 리뷰 3)
| 단계 | 사용자가 하는 일 | 느끼는 것 | 설계가 받쳐 주는 것 |
|---|---|---|---|
| 1 | 3단계 실행 | 얼마나 걸리나 | 예상 건수 · 시간(3.6), 결과 카드 |
| 2 | 라벨링 첫 진입 | 뭘 먼저 하지 | "라벨링 시작" 하나 + 예상 한 줄(4.1) |
| 3 | 첫 감사 50건(채택 1,000건 시점) | 기준이 맞나 | 태그 정의 옆 표시, 계산 등급 실시간, 첫 라운드 뒤 정의 수정 안내 |
| 4 | 자리 비움(며칠) | 잘 돌고 있나 | 세션 목록 "판정 62%" 배지 · 멈추면 "중단됨" 배지(7절) |
| 5 | 돌아옴 | 그사이 뭐가 됐지 | "지금 할 일" 카드 + 지난 접속 이후 변화(4.11) |
| 6 | 검수 큐 | 빨리 끝내고 싶다 | 키보드 조작 · 제출 = 저장 · 남은 건수와 예상 시간 |
| 7 | 감사 | AI를 믿어도 되나 | 라운드별 κ 추이 · 하락 시 경고 배너 |
| 8 | 학습 · 저장 | 다음엔 편해지나 | 결과 카드 · 모델 저장소 · 다음 세션에서 "분류 모델" 선택 |

---

## 5. 5단계 · 학습

### 5.1 학습셋 · 모델 구조 (`app/model/`, 워커 `train`, D-130)
- 학습셋 = `final`에서 `source ∈ {agreed(accepted), human}`인 문서 + 3단계 벡터(0벡터 제외). 분할 학습 80 / 검증 10(조기 종료) / 보정 10(temperature), 층화(등급 × 채널), 시드 고정.
- **입력 1032** = Voyage 1024 + 채널 원-핫 5 + log(본문 글자 수) 1 + 스니펫 문서 1 + Jev 입력 잘림 1.
- **멤버 구조(멀티태스크 MLP, PyTorch CPU):**
  ```
  입력 1032 → LayerNorm → Linear 512 → GELU → Dropout 0.2 → Linear 256 → GELU → Dropout 0.2  (공유 몸통)
     ├ anchor     Linear 1  → sigmoid
     ├ sem        Linear 6  → sigmoid ×6   (sense · feel · think · act · relate · outcome)
     ├ situation  Linear 1  → sigmoid
     ├ signal     Linear 5  → softmax
     └ reason     Linear 4  → softmax
  ```
- **손실(헤드별 마스크 가중합):** anchor BCE(전량) · sem · situation BCE(anchor=1만) · signal CE(Core · Supporting만) · reason CE(Non만). 드문 태그는 `pos_weight`.
- **소프트 라벨:** 합의분 목표 = (Jev 확률 + GPT 0/1) / 2, `signal`은 GPT 원-핫. 사람 판정은 0/1, 샘플 가중치 3.
- **학습 설정:** AdamW(lr 1e-3, weight decay 1e-4) · 배치 256 · 최대 30 에폭 · 검증 손실 3회 연속 비개선 시 멈춤.
- **앙상블 4개:** MLP × 3(시드 · 부트스트랩 표본 다름) + 선형 멤버 × 1(몸통 없이 헤드만, 같은 손실). 멤버마다 따로 학습하고, 출력 = 멤버 확률 평균, 평균 뒤 헤드별 temperature를 보정 데이터로 맞춘다.
- **모델 간 불일치** = 헤드별 멤버 확률 표준편차, 등급 불일치 = 멤버별 등급이 갈린 비율. 분류 모델 구간 라우팅에 쓴다(5.4).
- 헤드별 표본이 30건 미만이면 그 헤드를 학습하지 않고 "표본 부족"(분류 모델 구간 사용 불가).
- 지표: 헤드별 정확도 · F1 · ECE(보정 오차), 등급 정확도, 멤버별 · 앙상블 비교표.
- **단일 모델 만들기(증류)는 이번에 만들지 않는다(D-140 → B-107).** 아래는 나중을 위한 기록:  앙상블을 선생으로, 같은 구조의 MLP 하나를 **전량 벡터**(라벨 없는 문서 포함)에 앙상블 평균 확률을 목표로 학습한다. 모델 저장소에 `kind: "distilled"`, `parent: 앙상블 ID`로 저장하고, 보정 데이터에서 앙상블과 지표를 나란히 보여 준다. 단일 모델은 불일치 신호가 없으므로 라우팅은 확률 컷만 쓴다. 기본 사용은 앙상블.

### 5.2 등급 · 확률 (`app/model/infer.py`)
- 예측 태그 확률 → `rule.grade_probs` → `evidence_level_pred` = 최대 확률 등급, `confidence` = 그 확률, `pred_entropy` = 등급 분포 엔트로피. `relevance_score` = P(core) + P(supporting)(D-109).
- 규칙이 바뀌면(rule_version) 저장된 태그 확률로 다시 계산만 한다. 재학습 없음(AC-17).

### 5.3 모델 저장소 `models/{modelId}/` (D-108)
```
members/m{0..3}.pt   멤버 가중치 (앙상블) 또는 student.pt (증류)
calib.json       헤드별 temperature
meta.json        {modelId, kind: ensemble|distilled, members, createdAt, trainedFrom: {sid, version}, bk, oneLiner, n, perHead: {n, acc, f1, ece},
                  embedder: {name, model, dim}, rule_version, questions_version, parent: null | modelId}
```
- 임베더가 다른 세션에서는 고를 수 없다(벡터 공간이 다름). 목록에서 비활성 + 이유.
- "추가 학습": 기존 모델의 학습셋 + 이 세션 라벨로 새 모델을 만든다(`parent`). 기존 모델은 바뀌지 않는다.

### 5.4 분류 모델 구간 (4단계 mode=model)
- 3단계가 끝나면 전량 추론 → P(core ∪ supporting)이 0.2 미만 또는 0.8 초과 **그리고** 멤버 등급 불일치가 없으면 채택. 확률이 사이면 `model_uncertain`, 확률은 확실한데 멤버가 갈리면 `model_disagree`로 사람 큐. 컷은 설정값(기획안 12절).
- 감시: 무작위 1%를 Jev · GPT로 판정해(같은 판정 캐시) 등급 괴리율을 `stage_5.json`에 남긴다. 괴리율이 15%를 넘으면 "이 도메인에서는 LLM 라벨 구간으로 다시 하거나 추가 학습하세요" 배너.
- 새 도메인 첫 세션은 LLM 라벨 구간을 기본값으로 둔다(모델 선택 화면에 모델의 `bk` · `oneLiner`를 같이 보여 줌).

### 5.5 뒤 단계 호환 (AC-19)
- 5단계 저장 시 `classified/{sid}/{version}/relevant.jsonl`(Core + Supporting)과 `all.jsonl`을 쓰고 세션 `training.exportRef`에 경로를 남긴다. 6단계 군집은 이 파일만 읽는다(로컬 로더가 `relevant_` 접두사를 찾지 못하는 문제, 엔지니어링 리뷰 O4). 문서마다 `doc_id` · `evidence_level_pred` · `confidence` · `pred_entropy` · `relevance_score` · 태그 확률 · `signal`을 붙인다.
- LLM 라벨 구간에서 모델을 학습하지 않고 넘어가도 된다: 그러면 `final` 라벨을 그대로 내보낸다(`source`별, confidence는 4.7 값).
- 6단계 이후 코드는 고치지 않는다(3.4의 벡터 조회만 예외).

### 5.7 화면 (`/pipeline/training`, 디자인 리뷰 1bA · 목업 s6)
```
[페이지 제목 · 모델 없이 내보내기 · 학습 시작(primary)]
┌ InsightCard "등급 정확도 88%" (8칸) ──────┐ ┌ 헤드별 F1 · 보정 오차 (4칸) ┐
│ 학습 건수 · Jev 대비 · 멤버 불일치 비율     │ │ 선형 대비 MLP 차이          │
│ 근거 메타 · 다음 행동 "저장하고 클러스터링으로"│ └───────────────────────────┘
└──────────────────────────────────────────┘
모델 저장소 표 (12칸): 모델 · 종류(앙상블/단일) · 학습한 세션(bk + 한줄 정의) · 학습 건수 · 등급 정확도 · 임베딩 · 행 동작(단일 모델 만들기)
```
- 학습 전: 결과 카드 자리에 "학습할 라벨 281,410건(합의 280,800 · 사람 610)" + "학습 시작". 학습 중: 멤버 4개 진행 막대.
- 다른 임베딩으로 학습된 모델 행은 흐리게 두고 이유를 행 끝에 쓴다.

### 5.6 `stage_5.json`
```jsonc
{ "mode": "llm", "selfConsistency": { "agree": 0.90, "n": 20 },
  "kappaLabelers": { "anchor": 0.79, …, "relate": 0.61, "outcome": 0.66 },
  "labelerAccuracy": { "jev": {…}, "gpt": {…}, "n": 150 }, "agreementRate": 0.74,
  "levelDistribution": { "core": 0.12, "supporting": 0.31, "non": 0.57 },
  "accepted": 281002, "escalated": 37202, "mismatchRate": 0.117,
  "audit": [{ "round": 1, "kappaAI": 0.78 }],
  "model": { "modelId": "m_…", "perHead": {…} } | null, "monitorDivergence": null | 0.07 }
```

---

## 6. 공통 · known_insights

### 6.1 API · 저장
- `GET /known/{sid}` · `POST /known/{sid}` `{type: "statement", text}` 또는 `{type: "doc", doc_id}` · `PATCH /known/{sid}/{id}` · `DELETE /known/{sid}/{id}`.
- 문장 추가 시 임베더 1회 호출. 미연결이면 문장은 저장하되 "유사도 제외는 임베딩 연결 후 적용됩니다" 표시(문장 자체는 doc_id 제외에 쓰이지 않으므로 그동안은 효과 없음).
- 이전 세션 자동 채우기: 새 세션을 만들 때 같은 `bk`의 다른 세션 활성 버전의 `statement` 항목을 `from: prev_session`으로 복사한다(원문 항목은 수집본이 달라 복사하지 않음).

### 6.2 검색 제외 필터 (`app/known/filter.py`)
- `search_similar(sid, query, top_k, novel=True)`: 후보를 `top_k × 3`개 받아 ⓐ 원문 항목 `doc_id` 제외 ⓑ 후보 벡터와 known 벡터(문장 + 원문)의 최대 코사인 ≥ θ(0.85) 제외 → 앞에서 `top_k`개. `novel=False`면 필터 없음(AC-21).
- 로컬 검색(3.4) 안에서 한다: 후보 점수 계산 → 제외 → 상위 `top_k`. 호출부: `routers/chat.py`(채팅 · 인사이트 채팅) · `services/personas.py` · `routers/search.py`. 요청 스키마에 `novel`(기본 true) 추가.

### 6.3 화면
- **Known Insight 패널** `KnownInsightsDrawer`: 사이드바 하단 "Known Insight · N" 버튼 → 오른쪽 드로어(너비 360). 목록(유형 배지 문장/원문 · 출처 배지 · 삭제) + 새 문장 입력. 모든 단계 화면에서 열린다(`pipeline/layout.tsx`).
- **근거 원문 카드**: 채팅 답변 아래 "근거 원문" 목록(지금은 화면에 안 보이던 `sources`) · 카드마다 "Known Insight에 추가" · 목록 머리에 "새 발견 찾기" 스위치 · 넘긴 뒤 "추가한 이야기 빼고 다시 찾기".

---

## 7. 공통 워커 (`app/work/`)
- 0~2단계 `app/crawl/worker.py`의 프로세스 관리(pid 등록 · `BEGIN IMMEDIATE` 중복 방지 · heartbeat · interrupted 판정 · 이어서 진행)를 `app/work/runner.py`로 뽑아 크롤러와 새 워커가 같이 쓴다. 크롤러 동작은 바꾸지 않는다(기존 테스트가 회귀 계약).
- 워커 종류: `prep` · `judge` · `train` · `infer` · `monitor`. `python -m app.work.worker {kind} --sid --version [...]`.
- 화면은 `GET /work/{sid}/status`를 5초마다 폴링한다. 세션 목록 작업 배지(0~2단계 4.1)에 "판정 42%" · "학습 중" 등을 추가한다.
- 버전 만들기 제한(D-091 확장): `prep` · `judge` · `train` · `infer`가 실행 중이면 새 버전을 막는다. 일시 정지 상태의 `judge`는 판정 캐시가 버전 밖이라 허용한다.

---

## 8. API

| 메서드 · 경로 | 설명 |
|---|---|
| `PUT /prep/{sid}/config` · `POST /prep/{sid}/run` | 3단계 설정 저장 · 실행(같은 prepKey가 있으면 재사용하고 즉시 완료) |
| `GET /prep/{sid}/status` | 진행 · `stage_3.json` |
| `POST /label/{sid}/mode` | `{mode, modelId?}` — 라벨링 시작 전에만 허용, 시작 뒤에는 409 "새 버전에서 방식을 바꾸세요" |
| `POST /label/{sid}/start` | 라벨링 시작 = 두 판정 워커 시작(D-136) |
| `POST /label/{sid}/judge` · `POST /label/{sid}/judge/{labeler}/pause|resume` | 전량 판정 워커 시작 · 정지 · 이어서 |
| `GET /label/{sid}/overview` | 진행 · 예상 · 분포 · 불일치율 · κ · 라벨러 성능 |
| `GET /label/{sid}/next?mode=escalate|audit|reissue` | 다음 한 건 |
| `POST /label/{sid}/submit` | 한 건 제출 = 저장 → 계산 등급 · (제출 뒤) 라벨러 비교 |
| `POST /label/rule/preview` | `{tags}` → `{level}` |
| `POST /label/{sid}/audit` | 감사 라운드 만들기 |
| `POST /train/{sid}` · `GET /train/{sid}/status` | 학습 · 상태 |
| `GET /models` · `GET /models/{id}` | 모델 저장소 목록 · 상세 |
| `POST /train/{sid}/export` | 5단계 저장 → `classified/…` 내보내기 · `stage_5.json` |
| `GET/POST/PATCH/DELETE /known/{sid}…` | 6.1 |
| `GET /work/{sid}/status` | 모든 워커 상태 |
| `GET /integrations` | 기존 + `voyage` · `jev` · `codex` 항목, `pinecone` 항목 삭제 |

- 기존 `/preprocess`, `/sample/{sid}`, `/train`(옛 3모델) 경로는 새 세션에서 쓰지 않는다. 옛 세션 열람을 위해 코드는 남기고, 옛 `training.py`의 TensorFlow 경로는 제거한다(`requirements.txt`에서 TF 제외).
- 오류 응답은 0~2단계와 같은 `{status: "error", error: {kind, message}}`.

---

## 9. 실패 상태

| 상황 | 동작 | 화면 |
|---|---|---|
| Voyage 미연결 | 3단계 임베딩 단계에서 멈춤(`fake`가 아니면) | "임베딩 API가 연결되지 않았습니다. 연결하거나 내부용 설정에서 가짜 임베더로 바꾸세요." |
| 임베딩 일부 실패 | 0벡터 + 건수 | 3단계 결과 카드 "임베딩 실패 54건(검색 · 학습에서 제외)" |
| Kiwi 미설치 | 토큰 단계 실패 | "형태소 분석기를 불러오지 못했습니다. 설치 후 이어서 진행하세요." |
| Jev 401 / 미설정 | 워커 정지 · `unconnected` | "Jev가 연결되지 않았습니다." 배지 |
| Jev 402 | 일시 정지 | "Jev 잔액이 부족합니다. 충전한 뒤 이어서 진행하세요." |
| Jev 429 · 502 | 백오프 재시도 | 진행 막대 옆 "재시도 중" |
| codex 사용량 한도 · 실행 실패 | GPT 워커 일시 정지 | 4.5 문구 |
| 스키마 불량 답 | `bad` 격리 · 3회 후 `labeler_failed` escalate | 개요 "불량 12건" |
| 정의 점검 신호 | 배너 | "최근 감사에서 일치도가 두 번 연속 떨어졌습니다. 태그 정의를 확인하세요." |
| 학습 헤드 표본 부족 | 헤드 미학습 | "signal 헤드는 표본이 부족해 학습하지 않았습니다(18/30)." |
| 모델 임베더 불일치 | 선택 불가 | 모델 행 비활성 "다른 임베딩으로 학습된 모델입니다" |
| 감시 괴리율 > 15% | 배너 | 5.4 문구 |
| 워커 비정상 종료 | `interrupted` | "이어서 진행" |
| 구버전 세션 | 새 화면 편집 차단 | "구버전 세션은 새 라벨링을 쓸 수 없습니다. 기존 결과만 볼 수 있습니다." |

### 9.1 화면 상태 표 (0~2단계 8.1 규칙)
| 기능 | 로딩 | 빈 결과 | 오류 | 성공 | 부분 성공 |
|---|---|---|---|---|---|
| 3단계 실행 | 단계별 진행(필터 → 토큰 → 임베딩) | 통과 0건 → "규칙을 통과한 문서가 없습니다. 광고어와 길이 규칙을 확인하세요." | 9절 | 결과 카드(`stage_3.json`) + "라벨링으로" | 임베딩 일부 실패 |
| 전량 판정 | 라벨러별 진행 막대 | – | 9절 | 개요 갱신 | 한 라벨러만 진행 → 합친 건수 "합친 문서 31,020 / 판정 완료 Jev 80,112 · GPT 31,020" |
| 검수 큐 | 카드 스켈레톤 | 큐 0건 → "사람이 볼 문서가 없습니다. 감사 라운드를 만들거나 학습으로 넘어가세요." | 제출 실패 → "저장하지 못했습니다. 입력은 그대로 있습니다. 다시 제출하세요." | 다음 건 | – |
| 학습 | 헤드별 진행 | 학습셋 0건 → "학습할 라벨이 없습니다. 라벨링을 먼저 끝내세요." | 9절 | 지표 표 + 모델 ID | 일부 헤드 표본 부족 |
| 3단계 재사용 | – | – | – | 같은 수집본 · 규칙이면 즉시 결과 카드 + "같은 규칙의 결과를 그대로 씁니다(2026. 9. 30. 생성)" | – |
| 감사 탭 | – | 채택분 부족 → "채택 라벨이 1,000건 쌓이면 첫 라운드가 생깁니다(현재 320)." + "지금 라운드 만들기"(50건 이상일 때) | – | 라운드 표 | – |
| "4단계부터 다시" 새 버전 | – | – | – | 상단 안내 "이 라벨은 v1 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다." | – |
| Known Insight 패널 | – | 항목 0개 → "아직 Known Insight가 없습니다. 근거 원문에서 추가하거나 한 문장으로 적으세요." + 입력칸 포커스 | 문장 임베딩 실패 → 항목은 저장, "유사도 제외는 임베딩 연결 후 적용됩니다" 배지 | 목록 | – |
| 근거 원문 | 카드 스켈레톤 | 전부 제외됨 → "이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다." | 검색 실패 | 카드 목록 | – |

---

## 10. UI
- **이름 (D-135):** 이미 아는 이야기 목록은 화면 어디서나 **"Known Insight"**로 부른다(버튼 "Known Insight · N", 패널 제목, 카드 버튼 "Known Insight에 추가"). 한국어 UI 규칙의 예외인 고유 기능명이다. 코드 이름은 `knownInsights` 그대로.
- 0~2단계 10절(Person A Design System · 문구 규칙 · 접근성 · 내부용 표시)을 그대로 따른다. 3 · 4 · 5단계 화면 본문을 이번에 새 스타일로 바꾼다(0~2단계에서 미뤘던 부분).
- **화면당 파란 주요 버튼 하나 (디자인 리뷰 5A, D-137).** 머리의 "임시 저장 · 저장"은 흰 보조 버튼이다. 파란 버튼은 지금 할 일 하나에만 쓴다: 라벨링은 카드 안 다음 행동(검수 시작 · 제출 · 감사 시작), 3단계는 결과 전 "전처리 실행" · 결과 뒤 "라벨링으로"(이때 머리 버튼은 "다시 실행" 보조), 5단계는 학습 전 "학습 시작" · 학습 뒤 "저장하고 클러스터링으로".
- 새 공용 컴포넌트: `TagToggle`(6차원 · anchor · 상황, `aria-pressed`), `LevelBadge`(core/supporting/non, 글자 포함), `AlphaPanel`, `LabelerProgress`, `KappaTable`, `QueueCard`, `KnownInsightsDrawer`, `SourceCard`.
- 목업: `mockups/index.html`에 5개 화면(3단계 · 라벨링 개요 · 검수 큐 · 학습/모델 저장소 · Known Insight 패널 + 근거 원문)을 디자인 리뷰에서 만든다.
- 내부용(`NEXT_PUBLIC_INTERNAL_TOOLS`): prepKey · judge 캐시 경로 · modelId 원문 · 가짜 임베더/라벨러 스위치 · 예상 Jev 토큰 세부.
- 반응형 · 접근성 기준은 0~2단계와 같다(최소 1024px, 키보드 조작 4.11).

---

## 11. 테스트 전략
- 백엔드 pytest(네트워크 · 키 · codex · Kiwi 모델 다운로드 없이):
  - 임베더 `fake`, Jev `httpx.MockTransport`(200 · 401 · 402 · 422 · 429 · 502 응답 녹화), GPT는 가짜 codex 실행 파일(0~2단계 `tests/fakes/fake_codex.py` 확장).
  - Kiwi: 실제 패키지를 쓰되 짧은 고정 문장 몇 개로만(설치되지 않았으면 해당 테스트만 skip하지 않고 실패 — requirements에 포함).
  - 규칙: 기획안 6절 6행 고정 테스트 + `grade_probs` 합 = 1 · 몬테카를로 대조.
  - 이어 하기: 판정 워커 SIGKILL 후 재시작 → 가짜 Jev 호출 횟수가 문서 수와 같다(AC-10).
  - 통합: fixture 수집본 → 3단계 → 가짜 라벨러 판정 → 가짜 사람 제출 → 학습 → 내보내기 → 6단계 군집이 벡터 저장소를 읽음(API 호출 0회 확인).
- 프론트 Vitest: α 패널 상태 · 큐 키보드 · 태그 토글 → 미리보기 호출 · Known Insight 목록 · 근거 카드 필터 토글.
- 브라우저 QA: 03-plan에서 시나리오 정의(LG 에어컨 fixture · 가짜 백엔드).
- 의존성: `kiwipiepy`, `torch`(CPU), `numpy`. 제거: `tensorflow`, `pinecone`.
- 모델 테스트: 합성 벡터(태그별로 방향이 다른 가우시안)에서 앙상블이 학습 · 보정되고, 마스크된 칸이 손실에 들어가지 않으며(기울기 0), 규칙 변경 후 재추론만으로 등급이 바뀐다(AC-17). 증류 학생이 선생 확률을 따라간다.

---

## 12. 새 설계 결정 요약 (decision-log D-12x)
- D-120 LLM 판정 캐시는 버전 밖 모듈(`judge/`), 키 = 문서 집합 × 라벨러 × 질문 버전.
- D-121 RAG 검색은 로컬 벡터 검색 하나, Pinecone · 6.5단계 적재 제거(사용자 확정).
- D-129 임베딩 `voyage-4` 1024차원(사용자 확정).
- D-130 5단계 = 멀티태스크 MLP 앙상블(MLP ×3 + 선형 ×1) + 선택적 증류, PyTorch(사용자 확정 방향).
- D-122 필드가 엇갈리면 최종값은 Jev 값, 등급이 엇갈리면 escalate.
- D-123 (D-144로 제외) τ 계산.
- D-124 정의 점검 신호는 배너만, 판정을 자동으로 멈추지 않는다.
- D-125 긴 작업 워커를 `app/work/`로 공용화(크롤러 동작 불변).
- D-126 LLM 라벨 구간에서 모델 없이도 5단계 내보내기 가능.
- D-127 모델 헤드 표본 30건 미만이면 학습하지 않음, 분류 모델 구간 컷 0.2/0.8, 감시 괴리율 경고 15%.
- D-131 (D-145로 대체) 캘리브레이션은 한 사람.
- D-143 경계 사례 규칙 없음 · D-144 τ · α 제외 · D-145 캘리브레이션 제외, 감사로 라벨러 성능 측정(엔지니어링 리뷰 사용자 결정).

---

## 13. 디자인 리뷰 (plan-design-review, 2026-09-30)

대상은 이 문서의 3.6 · 4.11 · 4.12 · 5.7 · 6.3 · 9.1 · 10절과 [`mockups/index.html`](mockups/index.html)(화면 8개: 3단계 · 라벨링 개요 · 캘리브레이션 · 검수 큐 · 감사 · 학습/모델 저장소 · Known Insight/근거 원문 · 상태 모음)이다. 0~2단계와 같이 Person A 규칙으로 직접 그린 HTML 목업을 쓰고 AI 변형 목업은 만들지 않았다. 외부 의견(Codex · 서브에이전트)은 사용자 선택으로 돌리지 않았다(D2).

### 결정 (9건, 모두 사용자 개별 승인)
| # | 이슈 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | 라벨링 첫 화면에서 무엇을 먼저 보나 | A 개요 + "지금 할 일" 카드(우선순위 7단계) | 4.11 · D-132 · 목업 s2 |
| 1b | 3 · 5단계 화면 절 없음 | A 목업 구조로 확정 | 3.6 · 5.7 · D-133 |
| 2 | 빠진 상태 | 3단계 재사용 · 감사 대기 · "4단계부터 다시" 추가, 모델 저장소 빈 상태는 불필요(사용자) | 9.1 · D-134 |
| 2′ | 캘리브레이션 인원 | **사용자 지정: 한 사람**, κ_human 대신 자기 일관성 10% | 4.8 · D-131 |
| 2″ | "서랍" 이름 | **사용자 지정: "Known Insight"** + 빈 상태 문구 | 6.3 · 9.1 · 10 · D-135 |
| 3 | 라벨링 시작 버튼 여러 개 | A "라벨링 시작" 하나 + 예상 한 줄 + 100건 뒤 정의 수정 안내 | 4.1 · D-136 |
| 5 | 화면당 primary 둘 | A 머리 저장은 보조, 파란 버튼은 지금 할 일 하나 | 10 · D-137 |
| 6 | 단축키가 입력칸에서도 동작 · 등급 변경을 안 읽어 줌 | A 입력칸 · 패널 포커스면 끔 + aria-live | 4.11 · D-138 |
| 7 | 라벨링 방식을 중간에 바꾸면 결과가 섞임 | A 시작 전에 한 번만, 바꾸려면 새 버전 | 4.11 · 8 · D-139 |

### 점검별 점수
| 점검 | 전 | 후 | 남은 것 |
|---|---|---|---|
| 1 정보 구조 | 4 | 8 | Known Insight 패널과 외부 API 드로어가 같은 오른쪽 드로어 자리를 쓴다(동시에 하나만 열림으로 구현) |
| 2 상태 | 6 | 9 | 문구 · 모양은 브라우저 QA에서 확인 |
| 3 여정 | 5 | 8 | 6일 판정 중 알림(macOS 알림)은 범위 밖 |
| 4 뻔한 AI 디자인 | 8 | 8 | 개요 탭 카드 모자이크(0~2단계 규칙과 같아 유지) |
| 5 디자인 시스템 | 7 | 9 | 신규 컴포넌트 8종 규격은 구현 때 `components/ds/` 규칙 표(0~2단계 10절)를 따른다 |
| 6 반응형 · 접근성 | 6 | 8 | 데스크톱 전용(0~2단계 D-069) |

### 뻔한 AI 디자인 점검 (작업 도구 화면 기준)
- 즉시 탈락 패턴: 없음.
- 판정 기준: 브랜드 식별 YES · 시각 중심 하나 YES · 제목만 훑어도 이해 YES · 영역마다 역할 하나 YES · 카드 필요 대부분 YES(개요는 모자이크 주의) · 모션 없음 · 그림자 없이도 성립 YES.

### 이전 학습 반영
- `dcx-full-session-save`(2026-09-29): 3~5단계 옛 화면은 세션 통째 저장을 한다. 새 화면은 `PATCH /session`(drafts) + 기능별 API로 부분 저장만 한다(2.1 · 8절). 옛 `/save-session` 호출을 새 화면에서 쓰지 않는다.

### 범위 밖 (이번 리뷰에서 결정하지 않음)
- macOS 알림(판정 완료 · 멈춤): 세션 목록 배지로 대신한다.
- 다크 테마 · 모바일: 0~2단계와 같음.
- 6단계 이후 화면 본문 스타일.

### 이미 있는 것 (재사용)
- `components/ds/` 21종(Tabs · Banner · InsightCard · ProgressBar · Segmented · Switch · Table · Badge · Popover · Skeleton 등), `VersionPicker` · `StageVersion`, `usePolling`, 세션 목록 작업 배지, 외부 API 드로어 패턴(오른쪽 360px).

### 구현 과제 (03-plan으로 넘김)
- [ ] **T-D1 (P1)** 3단계 화면(3.6): 규칙 · 정형 문구 탭 · 예상 · 결과 카드 · 재사용 상태. 확인: 브라우저 QA.
- [ ] **T-D2 (P1)** 라벨링 개요(4.11): "지금 할 일" 우선순위 7단계 · 지난 접속 이후 변화 · α 패널 즉시 재계산 · 판정 진행 표. 확인: Vitest(우선순위 선택 로직) + 브라우저 QA.
- [ ] **T-D3 (P1)** 캘리브레이션 · 검수 큐 판정 카드: TagToggle · LevelBadge · 규칙 미리보기 API · 제출 뒤 비교 · 단축키 범위 · aria-live. 확인: Vitest(키보드 범위) + 브라우저 QA.
- [ ] **T-D4 (P1)** 감사 탭: 라운드 표 · 재캘리브레이션 배너 · re-issue. 확인: 브라우저 QA.
- [ ] **T-D5 (P1)** 학습 화면 · 모델 저장소(5.7). 확인: 브라우저 QA.
- [ ] **T-D6 (P1)** Known Insight 패널 + 근거 원문 카드(6.3). 확인: Vitest(필터 토글) + 브라우저 QA.
- [ ] **T-D7 (P1)** 9.1 상태 표 문구 · 모양 전부. 확인: 상태별 브라우저 QA.
- [ ] **T-D8 (P2)** 라벨링 방식 잠금(시작 뒤 409 + 배지). 확인: pytest + 브라우저 QA.

### 완료 요약
```
+====================================================================+
|         DESIGN PLAN REVIEW — COMPLETION SUMMARY                    |
+====================================================================+
| System Audit         | DESIGN.md 없음 → 0~2단계 10·13절 규칙 사용, UI 8화면 |
| Step 0               | 4/10, 7개 항목 전부                           |
| Pass 1  (Info Arch)  | 4/10 → 8/10 after fixes                       |
| Pass 2  (States)     | 6/10 → 9/10 after fixes                       |
| Pass 3  (Journey)    | 5/10 → 8/10 after fixes                       |
| Pass 4  (AI Slop)    | 8/10 → 8/10 (no new fixes)                    |
| Pass 5  (Design Sys) | 7/10 → 9/10 after fixes                       |
| Pass 6  (Responsive) | 6/10 → 8/10 after fixes                       |
| Pass 7  (Decisions)  | 1 resolved, 0 deferred                        |
+--------------------------------------------------------------------+
| NOT in scope         | written (3 items)                             |
| What already exists  | written                                       |
| TODOS.md updates     | 0 items proposed                              |
| Approved Mockups     | HTML 목업 8화면 (mockups/index.html)          |
| Decisions made       | 9 added to plan                               |
| Decisions deferred   | 0                                             |
| Overall design score | 4/10 → 8/10                                   |
+====================================================================+
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | — | Independent 2nd opinion | 0 | skipped (사용자 선택) | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 4/10 → 8/10, 9 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** design phase — Codex · 서브에이전트 모두 사용자 선택으로 생략(skipped). 외부 검증 없음.
- **VERDICT:** DESIGN CLEARED — eng review required (계획 단계에서 plan-eng-review 실행 예정).

NO UNRESOLVED DECISIONS
