# DCX 2.0 묶음 ② (7단계 근거 탐색) · 구현 계획 + QA 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 6단계에서 확정한 Persona · Context마다 근거 원문을 찾아(전체 10 · 새 발견 10 · 반례 · 희소) 화면 7에 보여 주고 8단계 입력인 Evidence Package를 만든다.

**Architecture:** 새 패키지 `backend/app/evidence/`(쿼리 → Context 필터 검색 → 지연 태깅(버전 밖 캐시) → quality × DPP 선택 → 탭 · novelty → 조립)를 `evidence` 워커가 Context 단위 체크포인트로 돌린다. 결과는 `versions/vN/evidence/`(evidence.sqlite · package.json · stage_7.json). 프론트 `/pipeline/evidence` 화면이 실행 중에도 완료 Context를 보여 준다.

**Tech Stack:** FastAPI · SQLite(WAL) · NumPy · Pydantic v2 · 기존 `app/llm` 레지스트리 · Voyage 임베딩 / Next.js 16 · Vitest.

**Spec:** [`02-design.md`](02-design.md)(묶음 ② 설계) + [`../dcx2-stage6-8/02-design.md`](../dcx2-stage6-8/02-design.md) 2.3 · 2.4 · 4 · 6~11절. 결정: [`../dcx2-stage6-8/decision-log.md`](../dcx2-stage6-8/decision-log.md) D-201~D-251.

## 전역 제약

- 구현은 모든 Task를 Codex(`codex:codex-rescue --wait --fresh`, 쓰기)가 TDD(RED → GREEN → 리팩터링)로 한다. Codex 샌드박스는 커밋하지 못하므로 controller가 diff · 테스트 확인 뒤 커밋한다.
- 테스트는 네트워크 · 키 없이 돈다(소켓 차단 conftest 그대로). LLM은 `app/llm/fake.py`(작업 이름별 `tests/fixtures/llm/{task}.json` 또는 `FakeBackend(responses=…)`), 임베더는 가짜.
- LLM 호출은 `app/llm` 레지스트리 `run_task` + Pydantic 출력 스키마만(D-221). 레거시 `call_claude` 금지.
- 판단이 필요 없는 계산(검색 · 리랭킹 · 인용 위치 · 지표 · 탭)은 코드. LLM은 쿼리 문장 · 태깅 · novelty만.
- 7단계 모듈은 `app/vectors/search.cosine_topk`를 직접 부르지 않는다 — `app/evidence/search.filtered_topk`만(AC-06).
- 튜닝값은 `app/evidence/params.py` 한곳, 결과 JSON에 쓰인 값 기록, 잠정 값은 화면 "잠정" 배지(D-211).
- 화면 문구는 02-design 9절 · 묶음 ② 02 7절 문구 그대로. 파란 주요 버튼은 화면당 하나(D-137).
- 묶음 ① 동작(6단계 결과 · 확정 · 버전)은 바뀌지 않는다. 예외: D-246/D-249 불용어(표시 · 전달 키워드만).

## 파라미터 (`app/evidence/params.py`, 02-design 4절 값 그대로)

```python
QUERY_DIMS = ('Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome', 'Counter', 'Residual')
FORBIDDEN = r'페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은'
TOP_PER_QUERY = 15          # 4.2
CANDIDATES_M = 50           # 4.2
CORE_BONUS = 0.05           # 4.2 (Counter 제외)
TAG_BATCH = 8               # 4.3
TAG_BODY_CHARS = 1500; TAG_COMMENTS = 10; TAG_COMMENT_CHARS = 300; KI_SUMMARY_CHARS = 200
SELECT_N = 10               # 4.4
W_RARITY = 0.3              # 잠정
DPP_SIGMA = 0.3             # 잠정
COVERAGE_MIN = 4            # /6, 미만이면 보충
COVERAGE_EXTRA = 15
TAG_PROB_ON = 0.5
RARE_MIN = 2
DUP_COSINE = 0.95           # 4.5 ⓒ
NEW_EXPAND = 50; NEW_EXPAND_MAX = 3
NOVELTY_SHOW = ('high', 'very_high')   # 잠정 임계
NOVELTY_CORE_REPS = 5
COUNTER_POLARITY_GAP = 0.3; COUNTER_TOP = 5; RARE_TOP = 5; DESIRE_TOP = 5
UNDIFF_COSINE = 0.8; UNDIFF_MIN = 3
CONCURRENCY = 4             # D-250, settings.evidence_llm_concurrency로 덮어씀
PROVISIONAL = ('W_RARITY', 'DPP_SIGMA', 'NOVELTY_SHOW', 'odi', 'persona_metrics')
```

## 파일 소유 · 의존 관계

| Task | 소유 파일(생성 · 수정) | 의존 | 병렬 가능 |
|---|---|---|---|
| T1 불용어 | `app/segment/stopwords.py`(생성), `app/segment/{l2,ctfidf,pipeline}.py`, `tests/segment/test_stopwords.py` | – | T2 · T3 |
| T2 임베더 · 필터 검색 | `app/vectors/embedder.py`, `app/evidence/__init__.py` · `search.py`(생성), `tests/evidence/test_search.py` | – | T1 · T3 |
| T3 픽스처 · 가짜 응답 | `tests/fixtures/evidence_synth.py`(생성), `tests/fixtures/llm/evidence.{queries,tag,novelty}.json`, `tests/scripts/make_segment_qa.py`(`--confirm-all`) | – | T1 · T2 |
| T4 저장 · 캐시 · 스키마 | `app/evidence/{params,store,cache,package}.py`, `tests/evidence/test_store.py` | T2 | – |
| T5 쿼리 | `app/evidence/queries.py` · `prompts/queries.v1.md`, `tests/evidence/test_queries.py` | T3 · T4 | T6 |
| T6 후보 검색 | `app/evidence/candidates.py`, `tests/evidence/test_candidates.py` | T2 · T3 · T4 | T5 |
| T7 지연 태깅 · 인용 | `app/evidence/tagging.py` · `quotes.py` · `prompts/tag.v1.md`, `tests/evidence/test_tagging.py` · `test_quotes.py` | T4 · T6 | T8 |
| T8 리랭킹 | `app/evidence/rerank.py`, `tests/evidence/test_rerank.py` | T4 | T7 |
| T9 탭 · novelty | `app/evidence/tabs.py` · `novelty.py` · `prompts/novelty.v1.md`, `tests/evidence/test_tabs.py` | T7 · T8 | – |
| T10 조립 · 지표 | `app/evidence/assemble.py`, `tests/evidence/test_assemble.py` | T1 · T9 | – |
| T11 워커 · 버전 · 완료 | `app/evidence/pipeline.py`, `app/work/worker.py`, `app/context/versions.py`, `app/routers/sessions.py`, `app/config.py`, `tests/evidence/test_pipeline.py`, `tests/context/test_versions_stage7.py` | T5 · T10 | – |
| T12 API | `app/routers/evidence.py`, `app/main.py`, `tests/evidence/test_api.py` | T11 | T13 |
| T13 프론트 API · 로직 | `frontend/src/lib/api/evidence.ts`, `lib/types.ts`, `components/evidence/evidenceView.ts`, 테스트 | T12 계약 | T12 |
| T14 화면 7 | `components/evidence/{EvidenceScreen,EvidenceCard,ContextList,QueryPanel}.tsx`, `app/pipeline/evidence/page.tsx`, `components/StepBar.tsx`, `lib/logic/completedThrough.ts`, 테스트 | T13 | T15 |
| T15 곁가지 UI | `components/segment/ContextLayer.tsx` · `SegmentScreen.tsx`, `app/pipeline/labeling/page.tsx`, 테스트 | T13 | T14 |
| T16 통합 · 성능 | `tests/evidence/test_integration.py`, `tests/evidence/test_perf.py`(`-m perf`, 기본 제외) | T11 · T12 | – |

경로는 `backend/` · `frontend/src/` 기준. 같은 파일을 두 Task가 고치지 않는다(T11만 `worker.py` · `versions.py` · `sessions.py`).

## 계약

### Python 내부 인터페이스

```python
# app/segment/stopwords.py (T1)
STOPWORDS: frozenset[str]
def is_stopword(word: str, bk: str | None) -> bool          # 목록 · 1글자 · 숫자만 · bk(공백 제거) · bk 포함 복합어
def filter_words(words: Iterable[str], bk: str | None) -> list[str]   # 순서 유지
def stopwords_signature() -> dict  # {'count': int, 'hash': sha256[:12]}

# app/vectors/embedder.py (T2) — 하위 호환
class Embedder(Protocol):
    def embed(self, texts: list[str], input_type: Literal['document', 'query'] = 'document') -> np.ndarray

# app/evidence/search.py (T2)
def filtered_topk(store: VectorStore, queries: np.ndarray, top_k: int, allow: set[str],
                  exclude: set[str] = frozenset(), bonus: dict[str, float] | None = None) -> list[list[tuple[str, float]]]
    # allow is None → ValueError('allow set required'); bonus = doc_id별 가산(Core +0.05)

# app/evidence/store.py (T4) — versions/vN/evidence/evidence.sqlite, D-251 표
class EvidenceStore:
    @classmethod
    def open(cls, sid: str, version: str) -> 'EvidenceStore'
    def reset(self, run: str, params: dict) -> None
    def get_run(self) -> str | None
    def write_queries(self, owner: str, rows: list[dict]) -> None
    def queries(self, owner: str | None = None) -> list[dict]
    def write_candidates(self, context_id: str, rows: list[dict]) -> None
    def candidates(self, context_id: str) -> list[dict]
    def write_selected(self, context_id: str, tab: str, rows: list[dict]) -> None   # 그 탭 행 교체
    def selected(self, context_id: str, tab: str | None = None) -> list[dict]
    def set_context(self, context_id: str, persona_id: str, status: str, **fields) -> None
    def contexts(self) -> list[dict]
    def write_persona_support(self, persona_id: str, rows: list[dict]) -> None
    def snapshot(self) -> 'EvidenceSnapshot'     # run + 행을 한 읽기 트랜잭션에서(D-239 패턴)

# app/evidence/cache.py (T4) — llmcache/{sid}/{prepKey}/tag-{pver}.sqlite
class TagCache:
    @classmethod
    def open(cls, sid: str, prep_key: str, pver: str) -> 'TagCache'
    def get_tags(self, doc_ids: Iterable[str]) -> dict[str, dict]
    def put_tags(self, rows: dict[str, dict], model: str) -> None
    def get_known(self, doc_ids: Iterable[str], ki_ids: Iterable[str]) -> dict[tuple[str, str], bool]
    def put_known(self, rows: dict[tuple[str, str], bool], model: str) -> None
    def drop_known(self, ki_id: str) -> None
def prompt_version(name: str) -> str   # 프롬프트 파일 sha256[:12]

# app/evidence/package.py (T4) — 02-design 2.4, 묶음 ③이 읽는다
class Quote(BaseModel): field: Literal['title','body','comment']; idx: int | None; start: int | None; end: int | None; text: str; verified: bool
class EvidenceItem(BaseModel): doc_id: str; source: str; quote: Quote | None; tags: list[str]; polarity: float | None; novelty: str | None; known_match: str | None; tab: list[Literal['all','new']]; role: Literal['support','counter','rare']; dist_centroid: float | None = None; combo_rarity: float | None = None
class ContextEvidence(BaseModel): context_id; context_name; action; situation: Situation; situation_origin: Literal['dims','tag']; dominant_constraint; keywords: list[str]; metrics: ContextMetrics; evidence: list[EvidenceItem]; counter_evidence; rare_evidence; flags: list[str]
class PersonaEvidence(BaseModel): cluster_id; persona_id; persona_name; desire; goal: list[str]; desire_support: list[EvidenceItem]; artifacts: list[Artifact]; metrics: PersonaMetrics; quality: dict
class EvidencePackage(BaseModel): schema_: Literal['evidence-package/1'] = Field(alias='schema'); version: str; params: dict; personas: list[PersonaBlock]

# app/evidence/queries.py (T5)
class PersonaQueryOut(BaseModel): persona_query: dict; context_queries: dict[str, dict[str, str]]; anchor_context_ids: list[str]
def validate_queries(out: PersonaQueryOut, context_ids: list[str]) -> list[str]   # 위반 목록 (a)~(c)
def generate_queries(sid: str, persona: dict, contexts: list[dict], one_liner: str, *, run_task=registry.run_task) -> QueryResult
    # QueryResult: persona_rows, context_rows{context_id: [{dim,text,origin}]}, failed: list[context_id], calls: int

# app/evidence/candidates.py (T6)
def search_context(context_id: str, queries: list[dict], *, docs: dict[str, dict], store: VectorStore,
                   embedder: Embedder, exclude: set[str] = frozenset(), top_per_query=TOP_PER_QUERY, m=CANDIDATES_M) -> list[dict]
    # [{doc_id, relevance, dims_hit:[dim], band}] relevance 내림차순, 동점은 doc_id
def search_persona(persona_id: str, queries: list[dict], **same) -> list[dict]

# app/evidence/quotes.py (T7)
def locate(quote: dict, doc: dict) -> dict   # {field, idx, start, end, text, verified}; 공백 정규화 후 정확 일치

# app/evidence/tagging.py (T7)
class TagOut(BaseModel): items: list[TagItem]   # 02-design 4.3 출력
def tag_documents(sid: str, doc_ids: list[str], *, docs, dims_by_id, known_items, cache: TagCache,
                  run_task, concurrency: int) -> TagResult    # 캐시 적중은 LLM 0회; TagResult.tags[doc_id], calls, cache_hits
def judge_known(sid: str, doc_ids: list[str], ki_ids: list[str], *, cache, run_task, concurrency) -> dict[tuple[str, str], bool]  # D-212

# app/evidence/rerank.py (T8)
def quality(relevance: float, combo_rarity: float | None, w_r=W_RARITY) -> float
def dpp_greedy(quality: np.ndarray, vectors: np.ndarray, k: int, sigma=DPP_SIGMA) -> list[int]  # Chen 2018 빠른 탐욕 MAP
def coverage(doc_ids: list[str], tag_probs: dict[str, dict | None]) -> int   # 0~6
def select(candidates: list[dict], tags: dict, vectors: dict, docs: dict, *, k=SELECT_N) -> Selection
    # Selection: rows[{doc_id, quality, rank, rare}], coverage, missing_dims, rare_fallback: int

# app/evidence/tabs.py (T9)
def known_exclusions(candidates, tags, handed_doc_ids: set[str], handed_vectors: np.ndarray, vectors) -> dict[str, str]  # doc_id → handed|match|dup
def new_tab(context_id, ..., expand: Callable[[int], list[dict]]) -> NewTab   # 확장 최대 3회, rounds 기록

# app/evidence/novelty.py (T9)
def judge_novelty(sid, context, new_rows, core_reps, known_items, *, run_task) -> dict[str, tuple[str, str]]

# app/evidence/assemble.py (T10)
def context_metrics(store_seg, context_id, *, session_minmax) -> dict
def assemble(sid: str, version: str) -> EvidencePackage      # package.json 저장 + 반환
def stage_report(counts: dict, params: dict) -> dict          # 4.8 항목

# app/evidence/pipeline.py (T11)
def run(context) -> None     # worker 진입점, args {'fresh': bool, 'contexts': list[str] | None}
def refresh_new(sid: str, version: str | None, context_id: str, run: str) -> dict   # LLM 0회
```

### API (T12 ↔ T13)

| 메서드 · 경로 | 요청 | 응답 | 오류 kind |
|---|---|---|---|
| `POST /evidence/{sid}/run?version=` | `{fresh?: bool, contexts?: string[]}` | `{runId}` | `segment_required`(409, 6-C 미확정 · segment 미완료) · `running` · `locked` |
| `GET /evidence/{sid}/status?version=` | – | `{status, run, progress, contexts: [{id, personaId, name, status, coverage, counts, error, knownChanged}], stage7?, reason?}` | – |
| `GET /evidence/{sid}/contexts/{id}?tab=all\|new&version=` | – | `{context, tab, items: EvidenceItemView[], counter, rare, excludedKnown: n, queries: [{dim, text, origin}], queryFailed, undifferentiated: string[]}` | `not_found` · `not_ready`(409, 그 Context 미완료) |
| `GET /evidence/{sid}/personas/{id}?version=` | – | `{desireSupport, artifacts}` | – |
| `POST /evidence/{sid}/contexts/{id}/refresh-new?version=` | `{run}` | 위 contexts 응답(tab=new) | `stale_run`(409) |
| `GET /evidence/{sid}/package?version=` | – | Evidence Package | `not_ready` |
| `POST /evidence/{sid}/contexts/{id}/skip?version=` | `{run}` | status | `stale_run` |
`EvidenceItemView` = `{docId, source, location: {field, idx}, quote: {text, start, end, verified}, text(원문 앞 600자), tags, band, novelty, noveltyReason, knownMatch, rare, role}`. Known Insight 추가는 기존 `POST /known/{sid}`(`from: 'rag'`, `docId`) 후 `refresh-new`.

### 완료 · 버전 (T11 ↔ T14)

- `session.evidence = {status: none|running|done|failed|interrupted|stale, run, progress, contexts: {done, total}, reason, savedAt}`.
- 서버 `_completion`에 `evidenceDone = evidence.status == 'done' ∧ 'stage7' ∉ stale`(segmentDone과 같은 모양). 프론트 `completedThrough`: `evidenceDone` → 7.
- 6단계 재실행(segment 새 run) 시작 시 `evidence.status = 'stale'`, `completion.evidenceDone` 제거. versions `_restart` 7: 이미 `evidence/` 삭제 — `completion.evidenceDone` 제거 추가.
- `compare(stage7)` = `{same, before: summary, after: summary}`, summary = `{report: stage_7 핵심 수치, contexts: {id: {selectedAll: [doc_id], selectedNew: [doc_id]}}}` → 프론트 기존 `MetricsComparison`/전용 표.

## Task별 단계

### T1 불용어 (D-246 · D-249)
- [ ] RED `tests/segment/test_stopwords.py`: `test_is_stopword_rules`(목록 단어 · '가' · '2024' · bk '에어컨' · 'LG에어컨' 복합어 → True, '냉방' → False), `test_list_size_and_editable`(80 ≤ len ≤ 150, 모듈 상수 하나), `test_l2_network_excludes_stopwords`(합성 노이즈 단어 '사용' · '생각'을 모든 문서에 넣어도 centrality 상위 16 · network 노드에 없음), `test_ctfidf_keywords_exclude_stopwords`, `test_context_keywords_exclude_stopwords`(LDA 표시 키워드), `test_lda_topic_count_unchanged`(불용어 적용 전후 Persona별 선택 토픽 수 동일), `test_stage6_params_record_stopwords`(`stage_6.json` params.stopwords = {count, hash}).
- [ ] 실행 `backend/.venv/bin/python -m pytest backend/tests/segment/test_stopwords.py -q` → FAIL(모듈 없음).
- [ ] 구현: L2는 어휘 빈도 집계 전 `is_stopword` 제외(bk 비교 기존 대체), c-TF-IDF 상위 어휘 산출 후 거르고 부족분은 다음 순위로 채움, L3는 학습 어휘 그대로 · `keywords_json` 표시용만 거름.
- [ ] GREEN 같은 명령 → PASS. 묶음 ① 회귀 `pytest backend/tests/segment -q` PASS.

### T2 임베더 `input_type` · 필터 강제 검색 (D-251, AC-06)
- [ ] RED `tests/evidence/test_search.py`: `test_embed_default_document`(인자 없이 기존 호출 동작 동일), `test_voyage_passes_input_type`(가짜 클라이언트로 `input_type='query'` 전달 확인), `test_filtered_topk_requires_allow`(None → ValueError), `test_never_returns_outside_allow`(무작위 1,000건 · allow 50건 · 100회 → 결과 ⊂ allow), `test_bonus_reorders`(동점 근처에서 Core +0.05가 순위를 바꿈), `test_evidence_never_imports_cosine_topk`(`app/evidence/*.py` 소스에 `cosine_topk` 문자열은 `search.py`에만).
- [ ] FAIL 확인 → 구현 → PASS.

### T3 합성 픽스처 · 가짜 LLM 응답 · QA 확정 스크립트
- [ ] `tests/fixtures/evidence_synth.py`: `make_evidence_session(local_data_dir, **segment_kwargs) -> SynthSession` = `make_segment_session` + 6단계 실행(가짜) + 6-A/B/C 전부 확정(이름 = 초안 또는 'CLn 이름'). `QueryEmbedder`(가짜): 질의 문장에 픽스처 명사/토큰이 있으면 그 Persona · Context 방향 벡터, 없으면 해시 벡터 — 02-design 11절.
- [ ] 가짜 응답: `evidence.queries.json`(Context ID 자리표시를 코드가 채우는 템플릿 형식은 금지 — `FakeBackend(responses=…)` 헬퍼 `fake_evidence_backend(contexts)`가 실제 ID로 만든다), `evidence.tag.json`(문서 ID는 헬퍼가 채움, 인용은 원문 실재 문장), `evidence.novelty.json`.
- [ ] `make_segment_qa.py --confirm-all`: 6단계 실행 + 전부 확정까지 해서 화면 7 QA 바로 가능.
- [ ] 테스트 `tests/evidence/test_fixture.py`: `test_session_ready_for_stage7`(segment done · 확정 수 = 전체), `test_query_embedder_points_to_context`.

### T4 저장 · 태그 캐시 · 패키지 스키마
- [ ] RED `tests/evidence/test_store.py`: 표 6개 생성 · WAL, `reset` 뒤 행 0, `write_selected` 탭 교체, `snapshot` 일관성(쓰기 중 읽기 · 세대 섞임 없음), `TagCache` 버전 밖 경로(`llmcache/{sid}/{prepKey}/tag-{pver}.sqlite`)와 프롬프트 바꾸면 새 파일, `drop_known`, `EvidencePackage` 왕복(JSON → 모델 → JSON 키 동일, `schema` 별칭).
- [ ] FAIL → 구현 → PASS.

### T5 쿼리 생성 · 검증 (4.1, AC-06)
- [ ] RED `tests/evidence/test_queries.py`: `test_valid_output_saved`(Context마다 8키 · persona 3문장), `test_anchor_union_must_cover_contexts`(a), `test_empty_key_rejected`(b), `test_forbidden_words_rejected`(c, '사용자는' 포함 → 위반), `test_regenerates_once_with_reasons`(1차 위반 → 2차 프롬프트에 위반 목록 포함, 호출 2회), `test_fallback_after_second_failure`(해당 Context 8쿼리 = `"{Context 이름} {키워드 3개}"`, origin `fallback`, `failed`에 ID), `test_keywords_filtered_by_stopwords`(입력 키워드에 불용어 없음).
- [ ] FAIL → 구현(프롬프트 `prompts/queries.v1.md`: 입력 헤더 oneLiner, 본문 02-design 4.1) → PASS.

### T6 후보 검색 (4.2)
- [ ] RED `tests/evidence/test_candidates.py`: `test_allow_is_context_docs`(다른 Context 문서 0), `test_counter_no_core_bonus`, `test_core_bonus_applied`, `test_union_dedup_top_m`(8쿼리 × 15 → 중복 제거 → 50, relevance = 쿼리별 최댓값), `test_dims_hit_recorded`, `test_persona_query_allow_is_persona`, `test_queries_embedded_as_query`(임베더 호출 input_type 기록).
- [ ] FAIL → 구현 → PASS.

### T7 지연 태깅 · 인용 위치 · Known 판정 (4.3, D-212 · D-213)
- [ ] RED `tests/evidence/test_quotes.py`: 본문 · 제목 · 댓글 n 위치, 공백 · 줄바꿈 차이 정규화 일치, 못 찾음 → `verified: false` · start/end null, 같은 문장 두 번 → 첫 위치.
- [ ] RED `tests/evidence/test_tagging.py`: `test_batches_of_eight`(20건 → 3회), `test_cache_hit_no_llm`(두 번째 실행 호출 0), `test_input_truncation`(본문 1,500자 · 댓글 10개 × 300자 · KI 요약 200자), `test_situation_from_dims_when_present`(dims 있으면 LLM situation 무시, 매핑: state ← environment + task_goal, emotion ← internal_state, barrier ← resource_constraint), `test_dims_lazy_for_core_without_dims`(Core ∧ dims 없음 → 출력 context_dims를 dims 캐시에 `origin: lazy`로 저장), `test_known_judged_per_item`(문장형 KI 추가 → 캐시 문서 × 그 KI만 판정, 기존 KI 재호출 0), `test_concurrency_equal_results`(동시 4 vs 1 결과 동일), `test_irrelevant_reason_counts`.
- [ ] FAIL → 구현(프롬프트 `prompts/tag.v1.md`, 6차원 태그 출력 안 함) → PASS.

### T8 리랭킹 · 선택 (4.4, AC-07)
- [ ] RED `tests/evidence/test_rerank.py`: `test_quality_formula`(0.8 × (1 + 0.3 × 0.5) = 0.92), `test_dpp_avoids_duplicates`(같은 벡터 3개 중 1개만), `test_dpp_matches_bruteforce_small`(n=8, k=3 탐욕 결과가 정의대로 log det 증가 최대 순서), `test_known_not_penalized`(known_match 있어도 quality 같음), `test_coverage_supplement_once`(coverage 3/6 → 빠진 차원 쿼리로 15건 보충 1회, `coverage_supplements` = 1), `test_rare_fallback_only_when_below_two`(rare 1 · 후보 rare 남음 → 최저 quality 비rare ↔ 최고 rare 교체, rare 2면 미발동), `test_tag_probs_null_counts_zero`.
- [ ] FAIL → 구현 → PASS.

### T9 탭 · 새 발견 확장 · novelty (4.5 · 4.6, AC-07 · AC-08)
- [ ] RED `tests/evidence/test_tabs.py`: `test_new_excludes_handed_match_dup`(넘긴 doc · known_match ≠ none · 넘긴 원문과 코사인 0.96 → 제외, 0.94 → 남음), `test_expand_until_ten_max_three`(부족하면 50건씩 최대 3회, rounds 기록, 그래도 부족하면 있는 만큼), `test_excluded_count_message_value`, `test_refresh_new_zero_llm`(KI 추가 뒤 refresh-new 호출 수 0, 새 발견 결과 변경), `test_all_tab_known_badge`, `test_novelty_only_new_tab`(전체 탭 전용 문서 novelty null), `test_novelty_show_threshold`(high · very_high만 표시 플래그).
- [ ] FAIL → 구현(프롬프트 `prompts/novelty.v1.md`) → PASS.

### T10 조립 · 지표 · 패키지 · 보고서 (4.7 · 4.8, AC-09)
- [ ] RED `tests/evidence/test_assemble.py`: `test_counter_evidence_rule`(Counter 쿼리 문서 중 polarity ≤ 평균 − 0.3 상위 5), `test_rare_evidence_top5`, `test_undifferentiated_candidate`(rare 무리 cos ≥ 0.8 3건 → 플래그 + 원문 3건), `test_desire_support_top5`, `test_artifacts_normalized_and_filtered`(소문자 · 공백 제거 · 불용어 · 제품명 제외), `test_metrics`(importance = Σθ/Persona 문서 수 → min-max, satisfaction = KNU 평균(−1~1 → 0~1) → min-max, odi = I + max(I−S, 0), author_count = 문서 작성자 중복 제거 · 댓글 작성자 제외), `test_package_schema_and_fields`(근거마다 source · quote 위치 · novelty · known_match 존재, 모델 검증 통과), `test_stage7_report_fields`(4.8 항목 전부, 'A–C 일치율' 없음).
- [ ] FAIL → 구현 → PASS.

### T11 워커 · 이어 하기 · 동시성 · 버전 · 완료
- [ ] RED `tests/evidence/test_pipeline.py`: `test_runs_all_contexts`, `test_resume_skips_done_contexts`(중단 후 재실행 LLM 호출 = 남은 Context 몫만), `test_context_failure_isolated`(한 Context 예외 → 그 행 failed · 사유, 나머지 done, 세션 status는 `partial` — 아래 규칙), `test_all_llm_backend_failures_interrupt`(전부 backend → interrupted + LLM_REASON), `test_concurrency_1_vs_4_same_package`, `test_known_added_midrun_applies_to_pending`(완료 Context엔 knownChanged), `test_segment_rerun_marks_stale`, `test_stale_run_409_on_refresh`, `test_heartbeat_per_context`.
  - 실패 행 규칙: 실패 Context가 있으면 `status = 'done'`이 아니라 `'partial'`; 사용자가 "건너뛰고 진행"(skip)으로 모두 처리하면 `done`. 화면 "페르소나 만들기" 잠금(D-223)과 일치.
- [ ] RED `tests/context/test_versions_stage7.py`: `test_restart_from7_keeps_segment_confirmations`, `test_restart_from7_reuses_tag_cache`(LLM 0회), `test_restart_from6_deletes_evidence`, `test_completion_evidence_done_rules`(done ∧ not stale만 True), `test_compare_stage7_summary`.
- [ ] FAIL → 구현(`app/config.py`에 `evidence_llm_concurrency: int = 4`) → PASS.

### T12 API (설계 8절)
- [ ] RED `tests/evidence/test_api.py`: 표의 경로 전부 성공 · 오류 kind, `test_run_409_until_6c_confirmed`(문구 "6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요."), `test_context_not_ready_while_pending`, `test_readonly_version_rejects_writes`, `test_known_add_then_refresh_changes_new_tab`.
- [ ] FAIL → 구현(`app/main.py`에 라우터 등록) → PASS.

### T13 프론트 API · 타입 · 표시 로직
- [ ] `lib/api/evidence.ts` 함수(계약 표 1:1), `lib/types.ts` 타입, `components/evidence/evidenceView.ts`: `rowBadge(status)`(완료 · 진행 중 · 대기 · 실패), `canBuildPersona(status)`(전부 done 또는 skip), `locationLabel({field, idx})`('본문' · '제목' · '댓글 3'), `highlight(text, start, end)`, `excludedMessage(n)`("N건이 Known Insight와 같아 빠졌습니다").
- [ ] Vitest `evidenceView.test.ts` RED → GREEN.

### T14 화면 7 (`/pipeline/evidence`, 02-design 4.9 · D-223 · D-227)
- [ ] `EvidenceScreen`: 왼쪽 Persona 목록(클러스터별 · 상태 배지) → Context 목록(Coverage x/6 · 새 발견 n · ⚠ 미분화 후보), 오른쪽 `[전체 10 | 새 발견 10]` 탭(기본: Context 근거 = 새 발견), 쿼리 보기(8문장 · 실패 문구 "자동 쿼리 생성에 실패해 Context 이름과 키워드로 검색했습니다."), 반례 · 희소 접힘, Persona 근거 접힘. 실행 중 완료 행 열람 · 진행 "Context 12/31 · 태깅 호출 84회". 실패 행 [다시 시도] [건너뛰고 진행]. 주요 버튼 하나: 실행 전 "근거 탐색 실행", 완료 후 "페르소나 만들기"(묶음 ③ 전까지 `/pipeline/personas`로 이동만).
- [ ] `EvidenceCard`(SourceCard 확장): 인용 하이라이트 · 채널 배지 · 위치 · 차원 태그 · 밴드 · novelty · "Known Insight와 같은 내용" 배지 · [Known Insight에 추가].
- [ ] `StepBar` 7 경로 `/pipeline/evidence`, `completedThrough` evidenceDone → 7, 옛 세션(`prep.derivedRef` 없음)은 기존 표시.
- [ ] Vitest: 탭 전환, 실행 중 완료 행 열림 · 대기 행 잠김, KI 추가 → 재계산 버튼, 빈 상태 문구 3종(후보 0 · 새 발견 0 · 6-C 미확정), 1024px 가로 스크롤 없음(레이아웃 클래스 검사).

### T15 곁가지 UI
- [ ] 6-C `ContextLayer`: `undifferentiated_candidate` → Badge "새 Context 후보 — 원문 3건"(펼침, 생성 버튼 없음).
- [ ] `SegmentScreen` "근거 탐색 실행" → `/pipeline/evidence`로 이동 후 실행.
- [ ] 라벨링 화면 배너 "7단계에서 무관 판정 N건 — 4단계 재점검 참고"(N>0, `stage7.irrelevant` 사용).
- [ ] Vitest 각 1개.

### T16 통합 · 성능
- [ ] `test_integration.py::test_stage5_to_stage7_offline`: 합성 세션 → 6(가짜) → 전부 확정 → 7 → 패키지 검증 · `stage_7.json` · 외부 소켓 0 · 두 번째 실행 LLM 호출 0(캐시).
- [ ] `test_perf.py`(`-m perf`): Context 31 · 후보 50 기준 리랭킹 · 탭 계산 시간 기록(임계 없음, 보고서에 수치).

## Review Focus (테스트가 직접 다루지 않는 위험 → 담당 Task에 테스트 추가)

1. 인용이 댓글에 있는데 크롤 당시 댓글 순서가 바뀐 문서(재크롤) — T7 `test_comment_index_from_prepared_order`: 위치는 6단계 입력(prepared) 순서 기준.
2. Known Insight를 실행 중에 지움 — T9/T11 `test_known_deleted_midrun`: `drop_known` 후 그 KI 배지 · 제외가 즉시 사라짐, 오류 없음.
3. Context 문서가 50건보다 적음(문서 부족 Context) — T6 `test_small_context_returns_all`: 후보 = 전부, 선택 = min(10, n), 빈 탭 문구.
4. 태깅 응답이 요청에 없는 doc_id를 돌려줌 · 일부 누락 — T7 `test_tag_response_id_mismatch`: 모르는 ID 무시, 누락 문서만 다음 묶음에 1회 재시도, 그래도 없으면 태그 없음(`untagged`)으로 남기고 선택 후보에서 빼며 `stage_7.json` `untagged` 수로 센다.
5. 오래된 화면에서 skip · refresh — T12 `test_stale_ui_actions_409`.

## 검증 명령

```bash
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```
(`harness.config.json` 검증 명령과 같음. perf는 `-m perf`로 따로.)

## 브라우저 QA 계획

- 시작: 백엔드 `cd backend && STORAGE=local LOCAL_DATA_DIR=<scratch>/qa-data LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3320 .venv/bin/uvicorn app.main:app --port 8320`, 프론트 `NEXT_PUBLIC_API_URL=http://localhost:8320 NEXT_PUBLIC_INTERNAL_TOOLS=true node_modules/.bin/next dev frontend -p 3320`.
- 데이터: `backend/.venv/bin/python backend/tests/scripts/make_segment_qa.py <scratch>/qa-data --confirm-all`.

| ID | 시나리오 | 기대 |
|---|---|---|
| QA-E1 | 6-C 하나 미확정 상태로 `/pipeline/evidence` | 실행 버튼 비활성 + "6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요." |
| QA-E2 | 실행 → 진행 중 | 상단 "Context n/N · 태깅 호출 m회", 행 배지 완료 · 진행 중 · 대기, 완료 행 클릭하면 근거 카드 보임 |
| QA-E3 | 완료 Context 새 발견 탭 | 카드 ≤10, 인용 하이라이트 · 채널 · 위치(본문/댓글 n) · 차원 태그 · 밴드 · novelty, 쿼리 보기 8문장 |
| QA-E4 | 카드 [Known Insight에 추가] | 서랍에 추가(rag), 새 발견 탭에서 빠짐 + "N건이 Known Insight와 같아 빠졌습니다 → 전체 탭에서 보기", 전체 탭엔 "Known Insight와 같은 내용" 배지 |
| QA-E5 | 실행 중 KI 추가 → 완료 행 | "Known Insight가 바뀌었습니다 · 새 발견 다시 계산" → 누르면 갱신(LLM 호출 수 변화 없음, 내부 표시) |
| QA-E6 | 태깅 응답 하나 없앤 서버(묶음 ① QA-S8 방식)로 Context 실패 | 행 "실패" + [다시 시도] [건너뛰고 진행], 건너뛰면 "페르소나 만들기" 활성 |
| QA-E7 | 완료 후 사이드바 · 6-C · 라벨링 | 사이드바 "8. 근거 탐색 완료"(번호는 StepBar 순서), 6-C 미분화 후보 배지(픽스처에 1건), 라벨링 배너 "7단계에서 무관 판정 N건 — 4단계 재점검 참고" |
| QA-E8 | 버전 "7단계부터 다시" → v2 · 비교 | v2 6-C 확정값 유지 · 7단계 빈 화면, 비교 화면 7단계 표 · 멈춤 없음 |
| QA-E9 | 옛 세션 | 사이드바 · 기존 화면 그대로 |
| QA-R2 | 1024px | 가로 스크롤 없음 |
| QA-L2 | 실제 기본 LLM(`.env`) 백엔드로 Persona 1개(Context 2~3개)만 실행 | 체크리스트: 쿼리에 금지어 없음 · 1인칭 · 8키, 인용 verified 비율, relevant=false 사유 분포, novelty 분포, 소요 · 호출 수. 키가 없으면 "미실행(키 없음)" |

## 수용 기준 연결

| AC | Task · 테스트 | QA |
|---|---|---|
| AC-06 쿼리 8문장 · 검증 · 재생성 · 필터 | T2 `test_filtered_topk_requires_allow` · `test_evidence_never_imports_cosine_topk`, T5 전부, T6 `test_allow_is_context_docs` | QA-E3 쿼리 보기, QA-L2 |
| AC-07 quality × DPP · rare fallback · 탭 · 확장 | T8 · T9 | QA-E3 |
| AC-08 Known Insight로 넘기기 → 새 발견에서 빠짐(0.95) | T9 `test_new_excludes_handed_match_dup` · `test_refresh_new_zero_llm`, T12 | QA-E4 · E5 |
| AC-09 패키지 스키마 · 채널 · 인용 위치 · novelty · known_match | T4 · T10 `test_package_schema_and_fields` | QA-L2 |
| AC-14 오프라인 · 회귀 · 버전 · 읽기 전용 | T11 버전 테스트, T16, 전체 검증 명령 | QA-E8 · E9 |

## 되돌리기

- 기능 브랜치 `feature/dcx2-stage7`을 merge하지 않으면 영향 없음. merge 후 되돌리기: merge 커밋 revert. 데이터: `versions/vN/evidence/` · `llmcache/*/tag-*.sqlite` 삭제로 완전히 원상(6단계 결과 무관). 불용어(T1)는 `stopwords.py` 비우면 묶음 ① 동작과 같아짐(6단계 재실행 필요).

## 엔지니어링 리뷰 (2026-10-02, controller 자체 점검)

- **데이터 흐름:** segment.sqlite(확정값 · 밴드 · θ · dims) + 원문(6단계 입력) + 벡터 → 쿼리(Persona당 1회) → Context별 [필터 검색 → 태깅(캐시) → 선택 → 탭 → novelty] → package.json. 쓰기는 evidence.sqlite · tag 캐시 모두 워커 메인 스레드 한 곳(D-250).
- **실패 모드:** LLM 전체 장애 → interrupted · 이어서 진행 / Context 하나 실패 → partial(D-252) / 태깅 누락 → 1회 재시도 후 untagged(D-253) / 인용 못 찾음 → verified false(8단계 하향) / 6단계 재실행 → stale + 409 / 실행 중 KI 추가 · 삭제 → 대기 Context 반영 · 완료 Context 재계산 버튼.
- **성능:** 비용 대부분이 태깅. 동시 4개 · 버전 밖 캐시 · Context 체크포인트. 합성 세션 실제 LLM 예상 약 20분(QA-L2에서 실측 기록).
- **병렬 구현:** T1 · T2 · T3 동시, 이후 T5 ∥ T6, T7 ∥ T8, T12 ∥ T13, T14 ∥ T15. 공유 파일(`worker.py` · `versions.py` · `sessions.py`)은 T11 한 곳.
- **묶음 ③과의 충돌 지점:** ③도 `worker.py` · `versions.py` · `sessions.py` · `StepBar.tsx` · `completedThrough.ts`를 고친다. ②가 먼저 merge되고 ③ T17에서 rebase로 해결(③ D-301).
- **새 사용자 결정 없음.** 판단 D-252~D-255는 원장에 기록.
