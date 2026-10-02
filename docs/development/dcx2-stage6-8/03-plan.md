# DCX 2.0 6~8단계 · 묶음 ① (6단계 구획) · 구현 계획 + QA 계획

> 구현은 Codex(`codex:codex-rescue`, `--wait --fresh`, 쓰기)에 위임하고 Claude는 분해 · 위임 · 리뷰만 한다. Task마다 RED → GREEN → 리팩터링, 보고서는 `.superpowers/sdd/03-plan/task-<ID>-report.md`.

**목표:** 5단계 결과(Core + Supporting)를 1.0 방법으로 Cluster → Persona → Context 3층으로 나누고, 품질 · 신호 · 6.5 dims 표본을 계산해, 사람이 6-A · 6-B · 6-C 화면에서 이름 · Desire · Goal · Context를 확정하게 한다.
**범위:** 묶음 ①만(D-228). `emerging` · `lexical_surprise`는 묶음 ②로 미룬다(엔지니어링 리뷰 D1, D-229).
**설계와의 차이(엔지니어링 리뷰):** L3 Context 수는 02-design 3.4의 "2~4에서 선택" 대신 1.0처럼 **2~10에서 C_v 최대**로 고르고, 4개를 넘으면 `granularity_exceeded` 경고만 붙인다(D-235). 6-C 화면은 그 Persona에 "Context가 6개입니다(권장 2~4)" 배지를 보인다. 02-design 2.1 · 2.2 · 2.3(dims) · 3 · 6(6단계 부분) · 7(segment) · 8(segment) · 9 · 10(6-A/B/C) · 11(6) · 14(T-D1 · T-D4 · T-D5의 6단계 부분).
**기준 문서:** `01-brainstorm.md`(AC-01~05 · AC-14) · `02-design.md`(설계 · 디자인 리뷰) · `decision-log.md` D-201~D-228 · 목업 `mockups/index.html` s1 · s2 · s3 · s8.
**기술:** Python 3.12 FastAPI(`backend/.venv`, numpy 2.5 · scipy 1.18 · scikit-learn 1.9), 새 의존성 `gensim>=4.4`(numpy 2 호환 확인) · `networkx>=3.3`. Next.js + Vitest(`frontend`). SQLite.

## 전역 제약
- 0~2 · 3~5단계 계획의 전역 제약을 그대로 따른다(맥미니 로컬 전용, 키 값 비노출, 한국어 UI 문구 규칙, Person A 토큰, 화면당 파란 버튼 하나 D-137).
- 테스트는 네트워크 · 키 · codex 없이 돈다. 임베더 `EMBED_BACKEND=fake`, LLM `LLM_BACKEND=fake`(작업 이름별 `backend/tests/fixtures/llm/<task>.json`).
- LLM 호출은 `app.llm.registry.run_task(LLMTask(...))` + Pydantic 출력 스키마만(D-221). 작업 이름: `segment.cluster_name` · `segment.persona_draft` · `segment.context_draft` · `segment.dims`.
- 새 화면은 세션 통째 저장(`/save-session`)을 쓰지 않는다. 기능별 API + `PATCH /session`의 `drafts.segment`만(학습 `dcx-full-session-save`).
- 시드 고정(`params.SEED = 42`): 같은 입력 · 같은 파라미터 → 같은 ID · 같은 배정.
- 클러스터링 입력에 0단계 `targetScope`를 넣지 않는다. `targetScope`는 `segment.persona_draft` 프롬프트 힌트에만(D-210).
- 기존 백엔드 1,458개 · 프론트 테스트를 깨지 않는다. 옛 세션(`prep.derivedRef` 없음)은 기존 `services/clustering.py` 경로 · 화면을 열람 전용으로 유지.
- 잠정 파라미터는 모두 `app/segment/params.py`에 두고 `stage_6.json.params`에 그대로 남긴다(D-211).

## 파라미터 (`app/segment/params.py`, 02-design 3절 값 그대로)
```
SEED=42; WARD_SAMPLE=20000; K_RANGE=(3,8); KMEANS_FULL_MAX=100000; MINIBATCH=4096
CTFIDF_TOP=10; REPS=5
L2_VOCAB=300; L2_EDGE_MIN_DOC_RATIO=0.005; L2_RESOLUTIONS=(1.0,1.2,1.5,2.0); PERSONA_RANGE=(2,3); CENTRALITY_TOP=16; NETWORK_SHOW=60
L3_TOPICS=(2,10); CONTEXT_WARN_MAX=4; L3_MIN_DOCS=30; LDA_PASSES=10; DICT_NO_BELOW=3; DICT_NO_ABOVE=0.5
BAND_P=(50,90); COUNTER_SENT_GAP=0.2; COUNTER_DOC_SHARE=0.15
COHESION_MIN=0.6; BOUNDARY_MAX=0.15; ARI_MIN={'L1':0.7,'L2':0.6}; ARI_RESAMPLE={'L1':5,'L2':3}; RESAMPLE_FRAC=0.8; CHANNEL_SKEW=0.8
DIMS_PER_CONTEXT=100; DIMS_BATCH=10; DIMS_PHRASE_MAX=12; CODE_COS=0.85
DESIRE_SIMILAR=0.85; MIN_DOCS_WARN=300
```

## 파일 소유 · 의존 관계

| Task | 내용 | 의존 | 소유 파일(C 새로 · M 수정) |
|---|---|---|---|
| T1 | 합성 픽스처 · 가짜 LLM 응답 | — | C `backend/tests/fixtures/segment_synth.py` · C `backend/tests/fixtures/llm/segment.{cluster_name,persona_draft,context_draft,dims}.json` · C `backend/tests/segment/__init__.py` · C `backend/tests/segment/test_synth.py` |
| T2 | 파라미터 · 저장소 · 입력 적재 · 명사 캐시(R2) | T1 | C `backend/app/segment/__init__.py` · C `params.py` · C `store.py` · C `inputs.py` · M `backend/requirements.txt` · C `backend/tests/segment/test_store.py` · C `test_inputs.py` |
| T3 | L1 Cluster | T2 | C `backend/app/segment/l1.py` · C `ctfidf.py` · C `backend/tests/segment/test_l1.py` |
| T4 | L2 Persona | T2 · T3(`ctfidf`) | C `backend/app/segment/l2.py` · C `backend/tests/segment/test_l2.py` |
| T5 | L3 Context | T2 | C `backend/app/segment/l3.py` · C `backend/tests/segment/test_l3.py` |
| T6 | 품질 · 신호 · 감성사전 | T2 | C `backend/app/segment/quality.py` · C `signals.py` · C `backend/app/lexicon/__init__.py` · C `backend/app/lexicon/knu.py` · (기존) `backend/app/lexicon/knu_senti.json` · C `backend/tests/segment/test_quality.py` · C `test_signals.py` |
| T7 | 6.5 dims 표본 · 코드화 · 조합 | T2 | C `backend/app/segment/dims.py` · C `backend/app/segment/prompts/dims.v1.md` · C `backend/tests/segment/test_dims.py` |
| T8 | 초안 생성 · Desire 유사 | T2 | C `backend/app/segment/drafts.py` · C `backend/app/segment/prompts/{cluster_name,persona_draft,context_draft}.v1.md` · C `backend/tests/segment/test_drafts.py` |
| T9 | 워커 · `stage_6.json` · 버전 · stale | T3~T8 | C `backend/app/segment/pipeline.py` · M `backend/app/work/worker.py`(KINDS에 `segment` 1줄 + 함수) · M `backend/app/context/versions.py`(`_restart` 6~8 · `last_stage` 8) · C `backend/tests/segment/test_pipeline.py` · C `backend/tests/context/test_versions_stage6.py` |
| T10 | API · 확정 게이트 | T2 · T9 | C `backend/app/routers/segment.py` · M `backend/app/main.py`(include_router 1줄) · C `backend/tests/segment/test_api.py` |
| T11 | 5단계 `pred_entropy` 보정 | — | M `backend/app/model/export.py` · C `backend/tests/model/test_export_entropy.py` |
| T12 | 프론트 API · 타입 · 표시 로직 | T10(계약) | C `frontend/src/lib/api/segment.ts` · M `frontend/src/lib/types.ts`(Segment 타입만) · C `frontend/src/components/segment/segmentView.ts` · C `segmentView.test.ts` |
| T13 | 공용 컴포넌트 | — | C `frontend/src/components/segment/{LayerTabs,QualityBadges,ChannelBar,KSuggestChart}.tsx` · C `frontend/src/components/ds/ProvisionalBadge.tsx` · M `frontend/src/components/ds/index.ts`(export 1줄) · C `frontend/src/components/segment/components.test.ts` |
| T14 | 클러스터링 화면 6-A · 6-B · 6-C | T12 · T13 | M `frontend/src/app/pipeline/clustering/page.tsx`(새 세션 분기) · C `frontend/src/components/segment/{SegmentScreen,ClusterLayer,PersonaLayer,ContextLayer,WordNetwork}.tsx` · M `frontend/src/app/pipeline/clustering/page.test.ts` |
| T15 | 사이드바 · 완료 판정 | — | M `frontend/src/components/StepBar.tsx` · M `frontend/src/lib/logic/completedThrough.ts` · M `completedThrough.test.ts` |

- **웨이브:** 1차 T1 · T11 · T13 · T15 → 2차 T2 → 3차 T3 · T5 · T6 · T7 · T8 → 4차 T4 → 5차 T9 → 6차 T10 · T12 → 7차 T14.
- 겹침 점검: 같은 웨이브 안에 소유 파일 겹침 없음. `worker.py` · `versions.py` · `main.py`는 각 1개 Task만 수정.

## 계약

### Python 내부 인터페이스 (T2 · T3~T9)
```python
# app/segment/inputs.py
@dataclass
class SegmentInput:
    ids: list[str]                     # 대상 문서(0벡터 · 토큰 0개 제외)
    vectors: np.ndarray                # float16 [n × dim], L2 정규화(R6) — 계산 시 배치마다 float32
    tokens: dict[str, list[str]]       # 3단계 tokens/ (형태소 '형태/품사' 아님, 원형 문자열)
    nouns: dict[str, list[str]]        # 명사만(3단계 tokenPos에서 NN* — 없으면 tokenize(text, ('NNG','NNP')))
    docs: dict[str, dict]              # relevant.jsonl 행(title · body · comments · source · author_hash · date · evidence_level_pred · tagProbs …)
    report: dict                       # {relevant, zero_vector, no_tokens, truncated, by_channel}
def load_input(sid: str, version: str) -> SegmentInput

# app/segment/l1.py
def suggest_k(vectors, rng) -> dict          # {k, silhouette:{k:v}, inertia:{k:v}, dendrogram:[...30], sample:int}
def cluster(vectors, k, rng) -> tuple[np.ndarray, np.ndarray]   # (labels[n], centroids[k×dim])
# app/segment/ctfidf.py
def ctfidf(groups: dict[str, list[list[str]]], top: int) -> dict[str, list[str]]
# app/segment/l2.py
def personas(cluster_ids: list[str], nouns: dict, bk: str) -> PersonaResult  # assign:{doc_id: persona_index}, communities, centrality:[(word,score)×16], network:{nodes,edges}, flags, fallback_ratio
# app/segment/l3.py
def contexts(doc_ids, tokens, vectors_by_id) -> ContextResult  # assign, theta, theta_all, topic_words, scan:{k:{cv,perplexity}}, centroids, dist, band, flags
# app/segment/store.py  (segment/segment.sqlite, 02-design 2.2 테이블 그대로)
class SegmentStore: open(sid, version) · write_layers(...) · clusters() · personas(cluster_id=None) · contexts(persona_id=None) · docs(context_id=None, band=None, limit, offset) · confirm(layer, id, values) · confirm_contexts(persona_id, items) · add_request(...)
# app/segment/dims.py
def extract_sample(sid, version, store) -> dict        # stage_6.dims 부분
def combo_rarity(dims_by_doc, codes, combos) -> dict[str, float]   # 7단계 지연 추출도 재사용
```

### API (T10 ↔ T12)
| 메서드 · 경로 | 요청 | 응답 |
|---|---|---|
| `POST /segment/{sid}/run` | `{k?: int}` | `{runId}` · 5단계 결과 없음 409 "학습 단계에서 결과를 저장한 뒤 클러스터링을 실행하세요." · k 지정 시 확정값 삭제(본문 `confirmReset: true` 없으면 409 `confirm_required`) |
| `GET /segment/{sid}/status` | — | `{status, step: load\|L1\|L2\|L3\|quality\|dims\|drafts, progress, stage6?, confirm:{clusters:"3/5",personas:"0/12",contexts:"0/31"}, reason?}` |
| `GET /segment/{sid}/clusters` | — | `[{id, docs, nameDraft, name, confirmed, keywords, reps:[{docId, text, source, field, idx}], quality:{cohesion, boundary, ari, flags[]}, channels:{src:share}, channelSkew, requests[]}]` + `kSuggest` |
| `GET /segment/{sid}/personas?cluster=CL0` | — | `[{id, clusterId, docs, authors, nameDraft, name, desireDraft, desire, goalsDraft[], goals[], centrality:[[w,s]], network:{nodes,edges}, similar:[{id, score, desire}], reps, flags[], confirmed, hint?}]` (6-A 미확정 시 409 `locked`) |
| `GET /segment/{sid}/contexts?persona=CL0-P1` | — | `[{id, personaId, docs, nameDraft, name, actionDraft, action, keywords, dominantConstraint, dimsSummary, quality:{cohesion,npmi}, flags[], confirmed}]` + `emptyGoalConstraintRatio` (6-B 미확정 시 409 `locked`) |
| `PUT /segment/{sid}/clusters/{id}` | `{run, name, confirm: true}` | 저장 행 · `run`이 현재 실행과 다르면 409 `stale_run`(R8) |
| `PUT /segment/{sid}/personas/{id}` | `{run, name, desire, goals[1..3], confirm: true}` | 저장 행 · 앞 층 미확정 409 `locked` · 빈 Desire 422 |
| `PUT /segment/{sid}/contexts/{id}` | `{run, name, action, confirm: true}` | 저장 행 |
| `POST /segment/{sid}/personas/{id}/confirm-contexts` | `{run, contexts:[{id,name,action}]}` | 한 트랜잭션, 그 Persona 밖 ID 포함 시 422(D-224) |
| `POST /segment/{sid}/requests` | `{layer, id, kind: split\|merge, note}` | 저장 메모 |
| `GET /segment/{sid}/docs?context=&band=&offset=&limit=` | — | 원문 페이지 |
- **실행 세대(R8 · D13):** 6단계 실행마다 `run`(UUID)을 `session.segment.run`과 `segment.sqlite` `meta` 테이블에 기록하고 모든 목록 · 상태 응답에 포함. 확정 · 일괄 확정 요청과 `drafts.segment`의 `run`이 현재와 다르면 409 `stale_run` "다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요."(임시 저장은 버림).
- 쓰기 API는 읽기 전용 버전에서 409(기존 `assert_writable`). 오류 형식 `{status:"error", error:{kind, message}}`.
- `session.json.segment`(02-design 2.1)는 서버만 쓴다. `confirm` 문자열은 store 집계로 갱신.

### 완료 · 버전 (T9 ↔ T15)
- 6-C 전부 확정 시 `session.segment.status = "done"` · `completion.segmentDone = true` · `clear_stale(sid, v, 'stage6')`.
- `completedThrough`: `segmentDone`(없으면 옛 `clusters` 키 규칙 유지) → 6.

## Task별 단계

### T1 합성 픽스처 · 가짜 LLM 응답
- **RED:** `test_synth.py`
  - `test_synth_shapes` — `make_segment_session(tmp_path, clusters=5, personas=(2,3,2,3,2), contexts=(2,3,2,2,3,2,2,3,2,2,2,3)[:sum], docs_per_context=40, seed=0)` → 반환 `SynthSession(sid, version, expected: dict)`; `expected['k']==5`, 문서 수 = Context 수 × 40, 모든 문서에 `title/body/comments/source/author_hash/date/evidence_level_pred/tagProbs`.
  - `test_synth_vectors_separable` — 클러스터별 평균 코사인(같은 클러스터) ≥ 0.7, (다른 클러스터) ≤ 0.2.
  - `test_synth_vocab_structure` — 공동체마다 고유 명사 10개 · Context마다 고유 토큰 8개, 다른 공동체와 겹치지 않음.
  - `test_synth_session_readable_by_pipeline_inputs` — 세션 디렉터리에 `prep.derivedRef` 모듈(`docs/` · `tokens/` · `vectors/`)과 `training.exportRef`(relevant.jsonl)가 있다(기존 `test_integration_stage3_5.py`의 세션 생성 헬퍼 재사용).
- **GREEN:** 1024D 가우시안(클러스터 방향 + Persona 오프셋 + 잡음 σ=0.05) · 어휘 생성 · 채널 5종 · 날짜 · 가짜 LLM JSON 4종(스키마는 T7 · T8 출력 모델과 같게).
- 명령: `backend/.venv/bin/python -m pytest backend/tests/segment/test_synth.py -q`

### T2 파라미터 · 저장소 · 입력 적재
- **RED (명사 캐시, R2):** `test_inputs.py::test_nouns_cached_next_to_derived` — 첫 `load_input`이 `derived/{sid}/{collectionId}/{prepKey}/nouns/part-*.jsonl`(`{doc_id, nouns[]}`)를 `store.atomic_write`로 쓰고, 두 번째 호출(새 버전 포함)은 Kiwi 호출 0회(`prep.tokens._kiwi` monkeypatch 카운터). 중간에 끊긴 부분 파일(manifest 없음)은 무시하고 다시 만든다.
- **RED:** `test_store.py` — 2.2 테이블 생성 · `write_layers` 왕복 · `confirm`이 `*_draft` 보존 · `confirm_contexts` 한 트랜잭션(중간 실패 시 전부 롤백) · `clusters()` 정렬 `CL0..`.
  `test_inputs.py::test_channel_from_derived_not_export` (Codex #1) — relevant.jsonl 행의 `source`는 판정 출처(`agreed|human|model`, `export.py:59`)로 덮어써져 있으므로, 채널(`source`)·`author_hash`·`comments`·`date`는 `derived/…/docs/`의 같은 `doc_id` 행에서 가져온다. 합성 픽스처의 export 행 `source`를 `agreed`로 두고 채널 분포가 수집 채널로 나오는지 확인. `SegmentInput.docs[doc_id]['judge_source']`에 판정 출처를 따로 둔다.
  `test_inputs.py` — 합성 세션 → `load_input` 문서 수 = 기대 − 0벡터 2 − 토큰 0개 1(픽스처에 일부러 넣음) · `report.truncated` = 본문+댓글 2,000자 초과 문서 수 · `by_channel` 합 = 대상 수 · 벡터 정규화.
- **GREEN:** 위 계약. `requirements.txt`에 `gensim>=4.4`, `networkx>=3.3` 추가.
- 명령: `… -m pytest backend/tests/segment/test_store.py backend/tests/segment/test_inputs.py -q`

### T3 L1 Cluster
- **RED:** `test_l1.py`
  - `test_suggest_k_finds_five` — 합성 → `suggest_k(...)['k']==5`, `silhouette` 키 3~8.
  - `test_ward_uses_sample_cap` — n=30,000 합성 → `sample==20000`.
  - `test_cluster_deterministic` — 같은 시드 두 번 → 같은 labels.
  - `test_minibatch_above_threshold` — `KMEANS_FULL_MAX`를 monkeypatch로 100 → MiniBatchKMeans `partial_fit` 경로(배치 4,096마다 float32 변환) 사용.
  - `test_large_input_streams`(R6) — 합성 20만 건 float16 입력, partial_fit 경로 결과 군집 수 = 기대 k, `tracemalloc` 최대 사용량을 보고서에 기록.
  - `test_ctfidf_distinguishes` — 클러스터별 상위 10에 그 클러스터 고유 명사가 7개 이상, 공통어 "에어컨" 미포함.
  - `test_ids_ordered_by_size` — ID `CL0`이 가장 큰 클러스터(크기 내림차순 재번호).
- **GREEN:** `scipy.cluster.hierarchy.linkage(method='ward')`(표본, 상위 30 병합 저장) · sklearn `KMeans`/`MiniBatchKMeans` · `silhouette_score`(표본).
- 명령: `… -m pytest backend/tests/segment/test_l1.py -q`

### T4 L2 Persona
- **RED:** `test_l2.py`
  - `test_communities_match_personas` — 합성 클러스터마다 공동체 = 기대 Persona 수(2 또는 3), 배정 정확도 ≥ 0.9.
  - `test_merge_when_more_than_three` — 공동체 5개 입력 → 엣지 가중합 최대 이웃으로 병합해 3개.
  - `test_resolution_raise_when_one` — 단일 공동체 입력 → resolution 1.2 · 1.5 · 2.0 순서로 시도, 끝까지 1개면 `flags=['few_communities']`.
  - `test_fallback_assignment` — 공동체 어휘가 하나도 없는 문서 → 가장 큰 Persona, `fallback_ratio` 계산.
  - `test_centrality_top16_normalized` — 길이 16, 최댓값 1.0, `bk`(제품명) 제외.
  - `test_network_view_limit` — `network.nodes` ≤ 60.
  - `test_empty_graph_single_persona` (Codex #5) — 엣지 제거 뒤 그래프가 비거나 공동체끼리 연결이 없으면: 빈 그래프 → Persona 1개 + `few_communities`, 연결 없는 작은 공동체 병합 대상이 없으면 문서 수가 가장 큰 공동체에 병합.
- **GREEN:** 문서빈도 상위 300 · 동시출현 가중 그래프 · `networkx.community.louvain_communities(seed=SEED)` · `eigenvector_centrality_numpy` · 배정 = 겹치는 어휘 centrality 합 최대(D-220).
- 명령: `… -m pytest backend/tests/segment/test_l2.py -q`

### T5 L3 Context
- **RED:** `test_l3.py`
  - `test_topic_count_by_cv` — 합성 Persona(Context 3개) → 2~10을 모두 학습해 C_v 최대인 3을 선택, `scan`에 2~10 cv · perplexity(R5 · D-235).
  - `test_granularity_warning` — C_v 최대가 6인 합성 Persona → Context 6개 생성 + `flags=['granularity_exceeded']`(나누지 않거나 합치지 않음).
  - `test_l3_perf`(`perf` 마커, 기본 검증 제외) — 합성 2만 건 Persona의 L3 소요 시간을 보고서에 기록.
  - `test_assignment_argmax_theta` — 모든 문서가 정확히 하나의 Context(`theta`=최대 확률).
  - `test_few_docs_single_context` — 문서 29건 → Context 1개, `flags=['few_docs']`, LDA 미호출.
  - `test_centroid_and_bands` — 센트로이드 = 배정 벡터 평균(정규화) · `dist_centroid=1-cos` · Context 안 P50/P90으로 core/fringe/edge 비율 ≈ 0.5/0.4/0.1.
  - `test_counter_flag` — 감성 평균이 Persona보다 0.2 이상 낮고 문서 비중 15% 미만인 Context → `counter_context`(감성은 인자로 주입).
  - `test_deterministic` — 같은 입력 두 번 → 같은 배정.
  - `test_empty_dictionary_single_context` (Codex #5) — 문서 30건 이상이어도 `no_below/no_above` 뒤 사전이 비면 LDA 미호출, Context 1개 + `few_docs`. 배정 문서가 0건인 토픽은 제거하고 번호를 다시 매긴다(`C1..`).
- **GREEN:** gensim `Dictionary(no_below=3, no_above=0.5)` · `LdaModel(passes=10, random_state=SEED)` · `CoherenceModel(coherence='c_v')`.
- 명령: `… -m pytest backend/tests/segment/test_l3.py -q`

### T6 품질 · 신호 · 감성사전
- **RED:** `test_quality.py` — cohesion(평균 코사인) · boundary(음수 실루엣 비율) · ARI 재표집(L1 5회 · L2 3회, 80%) · NPMI(손 계산 3어휘 말뭉치와 일치) · 채널 80% 편중 플래그 · 배지 임계(0.6 · 15% · 0.7/0.6).
  `test_signals.py` — `pred_entropy`는 export 값을 그대로 복사(T11, 재계산 없음) · KNU 감성(사전 항목 "좋다"=+, "짜증"=− 포함 문장 부호 확인, 사전에 없는 토큰만 → 0).
- **GREEN:** KNU 감성사전은 이미 커밋된 `backend/app/lexicon/knu_senti.json`(KnuSentiLex `SentiWord_info.json` 원본, 14,854항목 `[{word, word_root, polarity:"-2".."2"}]`, R1)을 읽는다. 로더 `lexicon.knu.polarity(tokens: list[str]) -> float` = 일치 항목 polarity 평균 ÷ 2(−1~1), 일치 0개면 0.0. 형태소 원형(`word_root`)과 토큰을 대조한다. 네트워크 접근 금지.
- 명령: `… -m pytest backend/tests/segment/test_quality.py backend/tests/segment/test_signals.py -q`

### T7 6.5 dims 표본 · 코드화 · 조합
- **RED:** `test_dims.py`
  - `test_sample_cap_per_context` — Context당 Core θ 상위 최대 100건만 LLM에 보냄(가짜 백엔드 호출 수 = ceil(표본/10)).
  - `test_cache_hit_no_llm` — 두 번째 실행 LLM 0회(`llmcache/{sid}/{prepKey}/dims-{pver}.sqlite`).
  - `test_batch_id_integrity` (Codex #7) — 응답 `doc_id`가 요청 집합과 일대일이 아니면(누락 · 중복 · 요청 밖) 그 배치는 캐시에 쓰지 않고 1회 재요청, 다시 실패하면 해당 문서를 `dims_failed`로 기록(캐시 없음). 키가 있고 값이 null = "관측 없음", 문서 행 자체 누락 = 실패로 구분.
  - `test_phrase_rules` — 12자 초과 문구는 자르지 않고 `null` 처리 + 건수 기록, 관측 없음 → null.
  - `test_code_normalization` — 가짜 임베더에서 같은 문구 변형(공백 · 조사 차이)이 한 코드, 코사인 0.85 미만은 다른 코드.
  - `test_combo_rarity_monotonic` — 희소 쌍 문서 > 흔한 쌍 문서, 값 0~1, 표본 밖 문서도 같은 표로 계산.
  - `test_summary` — `dominant_constraint` = 최빈 resource_constraint 코드 대표 문구 · 목적 · 제약 빈 비율 · Act 불일치 건수(sem.act ≥ 0.5 ∧ activity_response null 또는 그 역).
- **GREEN:** 출력 스키마 `DimsOut{items:[{doc_id, environment, internal_state, task_goal, activity_response, resource_constraint}]}`(각 `str|None`).
- 명령: `… -m pytest backend/tests/segment/test_dims.py -q`

### T8 초안 생성 · Desire 유사
- **RED:** `test_drafts.py`
  - `test_cluster_name_draft` · `test_persona_draft_fields` (이름 · Desire 1문장 · Goal 1~3) · `test_context_draft_fields` — 가짜 LLM 응답이 `*_draft`에 저장.
  - `test_persona_prompt_has_target_scope_hint_only` — `segment.persona_draft` 첨부에 `targetScope` 있음, `segment.cluster_name` · `segment.context_draft`에는 없음(D-210).
  - `test_draft_failure_leaves_empty` — 백엔드 실패 → 초안 빈칸 + `flags`에 `draft_failed`, 파이프라인 계속.
  - `test_desire_similarity_cross_cluster_only` — 다른 클러스터 Persona 간 코사인 ≥ 0.85만 `similar`에 기록, 같은 클러스터는 기록 안 함.
- 명령: `… -m pytest backend/tests/segment/test_drafts.py -q`

### T9 워커 · `stage_6.json` · 버전 · stale
- **RED:** `test_pipeline.py`
  - `test_end_to_end_synth` — 합성 세션에서 `segment` 워커 실행 → `segment.sqlite` 행 수, ID 형식 `CL\d+` · `CL\d+-P\d+` · `CL\d+-P\d+-C\d+`, 모든 대상 문서 Context 1개(AC-01), `stage_6.json` 02-design 3.9 키 전부(AC-05), `params` 기록, 외부 HTTP 0회.
  - `test_resume_skips_done_steps` — L2 뒤 중단(stop) → 재시작 시 L1 재계산 없음(체크포인트) · LLM 호출 중복 없음.
  - `test_heartbeat_each_persona` — L3 · drafts 중 Persona마다 heartbeat(학습 `bg-job-stale-window`).
  - `test_rerun_with_k_resets_confirmations` — k 지정 재실행 → 확정값 · L2 · L3 삭제.
  - `test_few_docs_warning` — 대상 212건 → k=3 고정, `stage_6.json.warnings`에 문구 키.
  `test_versions_stage6.py`
  - `test_restart_from_3_4_5_6_invalidates_segment` (R3 · D11) — 6단계 확정까지 끝난 세션에서 3 · 4 · 5 · 6부터 다시 각각 → 새 버전에 `segment/` 없음, `session.segment.status=='stale'`, `completion.segmentDone` · `drafts.segment` 없음, `stale.stage6~8`, 이전 버전은 그대로. `llmcache/` · `nouns/` 파일 유지.
  - `test_restart_stage7_keeps_segment` · `test_restart_stage8_keeps_segment` — `segment/` · 확정값 유지.
  - `test_llmcache_reused_across_versions` — 새 버전 6단계 재실행 시 dims LLM 0회.
  - `test_segment_worker_blocks_new_version` — 실행 중 버전 만들기 409.
  - `test_clear_stale_on_done` — 6-C 전부 확정 → `stale.stage6` 삭제, 다른 stale 유지.
  - **회귀(R3, CRITICAL)** `test_restart_stage3_4_5_unchanged` — 3 · 4 · 5단계부터 다시 각각: `stage_3.json`/`stage_5.json` 삭제 규칙 · `prep.status='stale'` · 라벨 재시작(`restartMessage` 문구 포함) · `training={'status':'stale'}`가 변경 전과 같다. 의도된 차이는 `stale`에 `stage7` · `stage8`이 추가되는 것뿐.
- **GREEN:** `pipeline.run(context)` 단계 순서 load → L1 → L2 → L3 → quality → dims → drafts, 각 끝에 체크포인트 파일 `segment/checkpoint.json`. `versions._restart`에 6 · 7 · 8 처리, `last_stage` 기본 8.
- 명령: `… -m pytest backend/tests/segment/test_pipeline.py backend/tests/context/test_versions_stage6.py -q`

### T10 API · 확정 게이트
- **RED:** `test_api.py` — `test_stale_run_rejected`(k 재실행 뒤 이전 `run`으로 확정 · 일괄 확정 → 409 `stale_run`, 값 저장 안 됨) · 위 API 표의 모든 행(성공 · 409 `locked` · 422 · 읽기 전용 409 · `confirm_required`) · 6-A 전부 확정 전 `GET /personas` 409 · `confirm-contexts`가 다른 Persona ID에 422 · 6-C 전부 확정 → `status.confirm.contexts == "31/31"` 형식 · `session.segment.status=="done"`.
- 명령: `… -m pytest backend/tests/segment/test_api.py -q`

### T11 5단계 `pred_entropy` 보정
- **RED:** `test_export_entropy.py` (Codex #2 반영) — 라벨 경로(agreed) 행의 `tagProbs`는 확정 0/1이라 그대로 쓰면 엔트로피가 0이다(`export.py:54`). 대신 태그별 소프트 확률 = (Jev 확률 `votes.jev.probs[tag]` + GPT 0/1) / 2(D-130 소프트 라벨 공식)로 `rule.grade_probs` → 엔트로피. 두 라벨러가 엇갈린 문서 > 0, 일치 문서 = 0 근처(손 계산 값), Jev 투표가 없으면 0, 사람 라벨 0, 모델 경로 기존 값 그대로. `tagProbs` 필드 자체는 바꾸지 않는다(하위 호환). 기존 내보내기 테스트 유지. T6 `pred_entropy`는 이 export 값을 그대로 읽는다(재계산하지 않음).
- 명령: `… -m pytest backend/tests/model -q`

### T12 프론트 API · 타입 · 표시 로직
- **RED:** `segmentView.test.ts` — `layerState(status)` → 탭 잠금 · 진행 문자열(6-A "3/5 확정", 잠김 사유 "6-A 확정 후") · `qualityBadges(q)` 임계(0.6 · 15% · 0.7) · `bulkConfirmWarning(contexts)` → "반례 1개 포함"(D-224) · `canStartEvidence(status)` · API 오류 `locked` · `confirm_required` · `stale_run` 문구 매핑, 임시 저장의 `run`이 다르면 버림.
- **GREEN:** `lib/api/segment.ts`(계약 표 그대로, 기존 `lib/api/train.ts` 패턴) · `types.ts`에 Segment 타입.
- 명령: `npm --prefix frontend test -- segmentView`

### T13 공용 컴포넌트
- **RED:** `components.test.ts` — `LayerTabs` 잠긴 탭 `aria-disabled` + 사유 툴팁 · `aria-current="step"`; `QualityBadges` 경고 배지 글자 포함; `ChannelBar` 80% 이상 "한 채널 편중"; `ProvisionalBadge` 텍스트 "잠정"; `KSuggestChart` `aria-label`에 k별 실루엣 값.
- 명령: `npm --prefix frontend test -- components`

### T14 클러스터링 화면 6-A · 6-B · 6-C
- **RED:** `clustering/page.test.ts`에 추가 — 새 세션(`prep.derivedRef` 있음) → `SegmentScreen`, 옛 세션 → 기존 화면; 실행 전 "클러스터링 실행"(primary 하나); 실행 중 단계 진행(목업 s8 "6단계 · 실행 중"); 6-A 이름 확정 → 진행 "4/5"; 전부 확정 전 6-B 탭 잠금; 6-B Desire 빈칸 확정 버튼 비활성; 유사 배지 문구 "클러스터가 달라 합치지 않고 기록만 남깁니다."; 6-C "이 Persona의 Context 모두 확정" + 반례 경고; 전부 확정 시 "근거 탐색 실행"은 묶음 ② 전이므로 비활성 + 툴팁 "다음 묶음에서 열립니다"; Context 4개 초과 Persona에 배지 "Context가 6개입니다(권장 2~4)"(D-235); k 바꿔 다시 나누기 확인 대화상자 문구 "이름 · Desire · Context 확정이 모두 지워집니다."; 저장 실패 시 입력 유지.
- **GREEN:** 목업 s1~s3 구조 · `StageVersion stage="stage6"`로 감싸기(버전 배너 · 6단계부터 다시) · `drafts.segment` 임시 저장 · 6-B 어휘 네트워크는 기존 `SNAGraph`(force) 재사용 → `WordNetwork`.
- 명령: `npm --prefix frontend test -- clustering`

### T15 사이드바 · 완료 판정
- **RED (회귀, R3, CRITICAL):** `StepBar` 단계 키 — 옛 키 `clustering` · `cluster-*` → 6(클러스터링), `persona` · `persona-*` · `embed-*` · `done` → 8(페르소나), 새 키 `evidence*` → 7 · `insight*` → 9. 기존 `prep-` · `label-` · `train-` 접두 규칙 그대로.
- **RED:** `completedThrough.test.ts` — `completion.segmentDone=true` → 6, 옛 `clusters` 키 규칙 유지; StepBar 단계 목록 = 시작 · 키워드 · 크롤링 · 전처리 · 라벨링 · 학습 · 클러스터링 · 근거 탐색 · 페르소나 · 인사이트(D-219), "임베딩" 표시 없음, 근거 탐색 이후 링크는 묶음 ②·③ 전까지 `/pipeline/clustering`에 안내 문구(경로 없음 → 비활성).
- 명령: `npm --prefix frontend test -- completedThrough`

## Review Focus (테스트가 직접 다루지 않는 위험 → 담당 Task에 테스트 추가)
1. **실데이터 규모(31만~100만):** Ward · 실루엣 표본 상한이 지켜지는가 → T3 `test_ward_uses_sample_cap`, T6 boundary도 표본(`test_boundary_uses_sample`).
2. **한 클러스터에 문서가 극단적으로 몰림(예: 90%):** L2 · L3가 시간 안에 끝나고 다른 클러스터가 비지 않는가 → T9 `test_skewed_cluster_completes`(합성 비율 0.9).
3. **빈 · 짧은 문서, 댓글만 있는 유튜브 문서:** 명사 0개 문서의 L2 배정(fallback) → T4 `test_fallback_assignment`, 토큰 0개 제외 → T2.
4. **LLM 응답이 스키마는 맞지만 내용 이상(Desire 3문장, Goal 5개):** 저장 전 잘라내기 → T8 `test_persona_draft_clamps`(Desire 첫 문장 · Goal 앞 3개).
5. **확정 중 동시 편집(두 탭):** 같은 Persona를 두 번 확정 → 마지막 값, `confirm_contexts`는 트랜잭션 → T2 `test_confirm_last_write_wins`.

## 검증 명령
```
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend test
```

## 브라우저 QA 계획
- 데이터: `backend/tests/fixtures/segment_synth.py`의 `make_segment_session`을 QA 임시 폴더에 실행하는 스크립트 `backend/tests/scripts/make_segment_qa.py`(T1에 포함)로 5단계 완료 세션 1개 생성(문서 약 1,200건, LG 에어컨 어휘).
- 시작: 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=<QA 임시 폴더> LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3310 .venv/bin/uvicorn app.main:app --port 8310`, 프론트 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8310 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3310`
- 테스트 URL: `http://localhost:3310/pipeline/clustering` (뷰포트 1360×900, 1024×768)

| ID | 시나리오 | 기대 | AC |
|---|---|---|---|
| QA-S1 | 5단계 완료 세션에서 클러스터링 실행 | 단계별 진행 → 6-A 열림, 클러스터 5개 · 품질 배지 · 채널 막대 · k 근거 차트 | AC-01 · AC-02 |
| QA-S2 | 6-A 이름 4/5만 확정 후 6-B 탭 | 잠김 + 사유 | AC-03 |
| QA-S3 | 6-A 전부 확정 → 6-B Desire · Goal 확정 | 어휘 네트워크 · centrality · 초안 힌트 문구 · 유사 배지 | AC-03 |
| QA-S4 | 6-C Persona 단위 일괄 확정(반례 포함 Persona) | 경고 배지 → 확정, 진행 숫자 갱신 | AC-04 · D-224 |
| QA-S5 | 6-C 전부 확정 | 사이드바 클러스터링 완료 체크, 목적 · 제약 빈 비율 표시 | AC-04 · AC-05 |
| QA-S6 | k를 4로 바꿔 다시 나누기 | 확인 대화상자 → 재실행 → 확정 초기화 | 3.2 |
| QA-S7 | "6단계부터 다시" 새 버전 → 이전 버전 열기 | 새 버전은 빈 확정에서 시작, 이전 버전 클러스터링 경로는 기존 규칙대로 안내 카드 "6단계의 저장된 결과를 확인합니다"(R7 · D12) | D-209 · AC-14 |
| QA-S8 | 가짜 LLM 응답 제거 후 실행 | "초안을 만들지 못했습니다. 직접 입력하세요." · 빈 입력칸 | 9절 |
| QA-S9 | 옛 세션(3단계 구버전) 열기 | 기존 클러스터링 화면 그대로 | AC-14 |
| QA-R | 1024×768 6-A · 6-B · 6-C | 가로 스크롤 없음, 키보드로 탭 · 확정 버튼 이동 | 10절 |
| QA-L1 | (R4) 백엔드를 실제 기본 LLM 설정(`LLM_BACKEND` 미지정, 키는 사용자 `.env`)으로 다시 띄워 합성 세션 6단계 실행 — 호출 약 30회 | 체크리스트를 QA 보고서에 기록: 클러스터 이름 15자 이내 · Desire 1문장 · Goal 1~3 · dims 12자 이내 · 관측 없는 칸 null · 금지어 없음. 키가 없으면 "미실행(키 없음)" | AC-03 · AC-04 |

## 수용 기준 연결
| AC | Task · 근거 |
|---|---|
| 01 | T2 · T3 · T4 · T5 · T9 `test_end_to_end_synth` · QA-S1 |
| 02 | T6 · T13 · T14 · QA-S1 |
| 03 | T8 · T10 · T14 · QA-S2 · QA-S3 |
| 04 | T7 · T10 · T14 · QA-S4 · QA-S5 |
| 05 | T7 · T9 `stage_6.json` · QA-S5 |
| 14 | 전체 검증 명령 · T9 버전 테스트 · QA-S7 · QA-S9 |

## 되돌리기
- main 머지 커밋을 `git revert -m 1 <merge>`로 되돌린다. 데이터 변경은 버전 폴더의 새 `segment/` 디렉터리와 `llmcache/`(둘 다 이전 코드가 읽지 않음), `session.json`의 `segment` · `completion.segmentDone` 키(이전 코드가 무시)뿐이다. `export.py`의 `pred_entropy` 변경은 새 내보내기에만 적용되고 이전 값을 읽는 코드가 없다.

## Decision ledger (plan-eng-review, 2026-10-02)

### Scope record
feature answers: D1 = A(emerging · lexical_surprise를 묶음 ②로, 사용자 답 2026-10-02); structure: D2 = A Original arrangement(사용자 답 2026-10-02); accepted scope: Task 15개 유지, T6에서 두 신호 제외(signals.py = pred_entropy + KNU 감성만); pending remedies: none.

### R1: KNU 감성사전 파일 확보
Finding: 1, P1, confidence 8/10, 03-plan.md T6 "KNU 감성사전은 공개 사전(KnuSentiLex) JSON을 … 저장", reviewer Claude(Section 1)
Plan baseline: T6가 사전 파일을 저장소에 넣는다고만 적음(출처 · 확보 방법 미정)
Runtime evidence: 저장소에 KNU 관련 파일 0건(`grep -rl KNU backend/app` 결과 없음). Codex 작업 환경의 네트워크 가능 여부는 미확인.
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 사전 확보 | 미정 | 지금 Claude가 GitHub KnuSentiLex의 `SentiWord_info.json`을 받아 `backend/app/lexicon/knu_senti.json`으로 커밋(사용자 허락 필요), T6는 로더 · 변환만 | Codex가 T6 구현 중 직접 다운로드 |
Question D3:
D3 — KNU 감성사전 파일을 누가 어떻게 가져올까요? (A: Claude가 지금 GitHub에서 받아 저장소에 커밋 / B: Codex가 구현 중 다운로드)
Header: D3 감성사전
Options:
A) 지금 받아 커밋 (recommended)
Claude가 GitHub KnuSentiLex의 SentiWord_info.json(약 1~2MB)을 내려받아 backend/app/lexicon/knu_senti.json으로 계획 브랜치에 커밋. T6는 로더만.
B) Codex가 구현 중 다운로드
T6 위임 때 Codex가 받음. 네트워크가 막혀 있으면 T6가 멈춤.

State: approved
Actual answer: A) 지금 받아 커밋 (사용자 답 2026-10-02, D3)
Accepted scope: Claude가 KnuSentiLex `SentiWord_info.json`(1,183,690바이트, 14,854항목, polarity 분포 −2:4,799 · −1:5,030 · 0:154 · 1:2,269 · 2:2,602 확인)을 `backend/app/lexicon/knu_senti.json`으로 계획 브랜치에 커밋. T6는 로더만, 네트워크 없음.
History: —

### R2: 명사 재분석 결과 캐시
Finding: 2, P2, confidence 8/10, backend/app/prep/config.py:23 `tokenPos: list[str] = Field(default_factory=lambda: ['NNG', 'NNP', 'VV', 'VA', 'XR'])` + 03-plan T2 `nouns` "없으면 tokenize(text, ('NNG','NNP'))", reviewer Claude(Section 2)
Plan baseline: T2 `load_input`이 실행마다 명사를 다시 뽑음(캐시 없음)
Runtime evidence: 3단계 tokens/는 품사 없이 형태만 저장(`prep/tokens.py` `token.form`). 명사 분리는 재분석 필요. 31만 건 Kiwi 재분석 시간은 미측정.
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 명사 토큰 | 실행마다 재분석 | 첫 실행 때 `derived/{sid}/{collectionId}/{prepKey}/nouns/part-*.jsonl`로 저장 · 이후 재사용(3단계 모듈 옆, 버전 밖) | 실행마다 재분석(현행 계획) |
Question D4:
D4 — 명사 재분석 결과를 3단계 모듈 옆에 저장해 재사용할까요?
Header: D4 명사 캐시
Options:
A) 3단계 모듈 옆에 저장 (recommended)
첫 6단계 실행 때 명사 토큰을 derived/…/nouns/에 쓰고 이후 버전 · 재실행은 읽기만. 테스트: 두 번째 실행 Kiwi 호출 0회.
B) 매번 재분석
코드 단순, 6단계 재실행마다 Kiwi 분석 시간 반복.

State: approved
Actual answer: A) 3단계 모듈 옆에 저장 (사용자 답 2026-10-02, D4)
Accepted scope: T2 `load_input`이 명사 토큰을 `derived/…/nouns/`에 원자적으로 한 번 쓰고 이후 재사용, 테스트 `test_nouns_cached_next_to_derived`(두 번째 실행 Kiwi 0회 · 부분 파일 무시).
History: —

### R3: 버전 재시작 · 사이드바 회귀 계약 (CRITICAL)
Finding: 3, P1, confidence 9/10, backend/app/context/versions.py:183 `last_stage = max([6, int(restart_from[5:])] + …)` · frontend/src/components/StepBar.tsx `persona: 7, "persona-start": 7, … "embed-start": 7, "embed-check": 7, done: 7`, reviewer Claude(Section 3)
Plan baseline: T9가 `_restart`에 6~8 처리 · `last_stage` 기본 8, T15가 STEPS 10개로 변경. 기존 동작 보존 테스트 없음.
Runtime evidence: 현재 `_restart`는 3 · 4 · 5단계만 처리, stale은 restart~6. STEP_MAP index 7 = 페르소나(STEPS 8개 기준).
Reopened: Codex outside voice #3(confidence 8/10) — R3의 "의도된 변경은 stale stage7 · stage8 추가뿐"은 6단계까지 완료한 세션에서 3~5단계부터 다시 할 때 `segment/` · `completion.segmentDone` · `session.segment` · `drafts.segment`도 무효화해야 한다는 필요와 충돌. 출발점이 6단계 완료 세션인 경우가 테스트에 없음.
Comparison grid:
| 선택 | 현재(R3 승인) | A | B |
|---|---|---|---|
| 0~5단계 재시작 기존 결과 | 보존 | 보존(그대로) | 보존(그대로) |
| 6단계 산출물 무효화(3~6단계부터 다시) | 정해지지 않음(stale만) | 새 버전에서 `segment/` 삭제 · `session.segment`={status:'stale'} · `completion.segmentDone` 삭제 · `drafts.segment` 삭제 · `llmcache/`는 유지 | stale 표시만(파일 · 완료 표시 남음) |
| 회귀 테스트 출발점 | 0~5단계까지 완료 세션 | 6단계까지 완료(확정 포함)한 세션에서 3 · 4 · 5 · 6부터 다시 + k 재실행 각각 | 현행 |
| 옛 단계 키 매핑 | 승인됨(R3) | 그대로 | 그대로 |
Question D11:
D11 — (R3 다시 열기) 3~6단계부터 다시 할 때 6단계 결과(segment · 완료 표시 · 임시 저장)도 새 버전에서 지울까요?
Header: D11 재시작 무효화
Options:
A) 6단계 결과도 무효화 (recommended)
3~6단계부터 다시 → 새 버전에서 segment/ 삭제, segment 상태 stale, segmentDone · drafts.segment 삭제(LLM 캐시는 유지). 0~5단계 기존 결과 보존은 그대로. 6단계 완료 세션을 출발점으로 하는 회귀 테스트 추가.
B) stale 표시만
파일과 완료 표시가 남고 배너만 뜸. 새 버전 사이드바에 클러스터링 완료 체크가 남을 수 있음.

State: approved
Actual answer: A) 6단계 결과도 무효화 (사용자 답 2026-10-02, D11). 이전 답 D5=A 유지.
Accepted scope: 0~5단계 재시작 보존 · 옛 단계 키 매핑(D5) + 3~6단계부터 다시 시 새 버전에서 `segment/` 삭제 · `session.segment={status:'stale'}` · `completion.segmentDone` · `drafts.segment` 삭제, `llmcache/` · `derived/…/nouns/` 유지. 회귀 테스트 출발점 = 6단계 확정까지 끝난 세션(3 · 4 · 5 · 6부터 다시 + k 재실행).
History: R3 1차 — Comparison grid:
  | 선택 | 현재 | A | B |
  |---|---|---|---|
  | 0~5단계 재시작 | 테스트 없음(이번 변경 기준) | 그대로 보존: stage_3/5.json 삭제 · prep stale · 라벨 재시작 · training stale. 의도된 변경은 stale 표시가 stage8까지 늘어나는 것뿐 | 계획대로(별도 계약 없음) |
  | 옛 세션 단계 키 | persona/embed/done → 7(페르소나) | clustering 계열 → 6, persona · embed · done → 8(페르소나), 새 키 evidence → 7 · insight → 9 | 계획대로 |
  | 테스트 | — | `test_versions_stage6.py::test_restart_stage3_4_5_unchanged`(3 · 4 · 5부터 다시 각각, 기존 결과 그대로 + stale에 stage6~8) · `completedThrough.test.ts`/`StepBar` 테스트 `old step keys map to 페르소나` | 없음 |
  Question D5:
  D5 — 0~5단계 버전 재시작과 옛 세션 사이드바 표시를 회귀 테스트로 고정할까요?
  Header: D5 회귀 계약
  Options:
  A) 회귀 계약 추가 (recommended)
  0~5단계 재시작 결과 그대로(의도된 변경은 stale이 stage8까지만), 옛 단계 키 persona·embed·done → 페르소나(8). 테스트 2묶음 추가(T9 · T15).
  B) 계획대로
  별도 회귀 테스트 없이 진행.
  
  State: approved
  Actual answer: A) 회귀 계약 추가 (사용자 답 2026-10-02, D5)
  Accepted scope: T9 `test_restart_stage3_4_5_unchanged` · T15 옛 단계 키 매핑 테스트(persona · embed · done → 8, clustering 계열 → 6, evidence → 7, insight → 9). 의도된 변경은 stale stage7 · stage8 추가뿐.
  History: —

### R4: LLM 프롬프트 품질 확인 깊이 (EVAL)
Finding: 4, P2, confidence 7/10, 03-plan 전역 제약 "LLM `LLM_BACKEND=fake`" · T7 · T8 프롬프트 4종(`segment.*`), reviewer Claude(Section 3)
Plan baseline: 모든 테스트 · 브라우저 QA가 가짜 LLM 응답. 실제 모델 출력 품질(관측된 것만 추출, 12자 문구, Desire 1문장)은 검증하지 않음.
Runtime evidence: 가짜 백엔드는 고정 JSON만 반환(`app/llm/fake.py`). 실제 키 사용 가능 여부 미확인.
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 실제 LLM 확인 | 없음 | 브라우저 QA에 QA-L1 추가: 실제 백엔드(설정된 기본 LLM)로 합성 세션 1개를 돌려 초안 3종 · dims 1 Context(호출 약 30회)를 사람이 읽고 체크리스트(Desire 1문장 · Goal ≤3 · dims 12자 · 관측 없는 칸 null) 기록. 키가 없으면 "미실행" 기록 | 가짜만, 실제 품질은 UAT에서 |
Question D6:
D6 — 실제 LLM으로 6단계 프롬프트 품질을 QA에서 한 번 확인할까요?
Header: D6 실제 LLM
Options:
A) QA-L1 추가 (recommended)
브라우저 QA 때 실제 LLM으로 약 30회 호출해 초안 · dims 출력을 체크리스트로 확인. 키 없으면 미실행 기록.
B) 가짜만
QA는 가짜 응답만, 실제 품질은 UAT에서 사용자가 확인.

State: approved
Actual answer: A) QA-L1 추가 (사용자 답 2026-10-02, D6)
Accepted scope: 브라우저 QA 시나리오 QA-L1(실제 LLM 약 30회, 체크리스트 기록, 키 없으면 미실행 기록). 자동 테스트는 그대로 가짜 LLM.
History: —

### R5: L3 토픽 수 참고 점수 범위
Finding: 5, P1, confidence 8/10, 03-plan T5 "`test_topic_count_by_cv` … `scan`에 2~10 cv · perplexity" · params `L3_SCAN=(2,10); LDA_PASSES=10`, reviewer Claude(Section 4)
Plan baseline: 선택은 2~4, 참고용 스캔은 Persona 전체 문서로 2~10(LDA 9개 + C_v).
Runtime evidence: 미측정. 참고 점수 한 점마다 그 토픽 수로 LDA를 한 번 학습해야 함(그리기 비용이 아니라 학습 비용).
Comparison grid:
| 선택 | 현재 | A | B | C |
|---|---|---|---|---|
| 선택용 LDA(2~4) | 전체 문서 | 전체 문서 그대로 | 전체 문서 그대로 | 전체 문서 그대로 |
| 참고 점수 5~10 | 전체 문서로 계산 | 계산하지 않음(참고 그래프 = 2·3·4 점수만, 추가 비용 0) | Persona당 최대 5,000건 표본으로 계산 | 전체 문서로 계산 |
| 성능 테스트 | 없음 | `perf` 마커: 합성 2만 건 Persona L3 시간 기록 | 같음 | 같음 |
Question D9:
D9 — (다시 질문) 참고 그래프를 실제로 계산하는 2·3·4개 점수만 보여 주고, 5~10개 계산은 빼도 될까요?
Header: D9 참고 범위
Options:
A) 2~4만 표시 (recommended)
배정에 쓰는 2·3·4개 점수(어차피 계산)만 그래프로. 5~10개 학습 없음, 추가 시간 0. 설계 3.4 "2~10 표시"와 다름.
B) 5~10은 표본 5,000건
5~10개 참고 점수를 Persona당 최대 5,000건으로 학습해 표시.
C) 5~10도 전체 문서
설계 문구 그대로, 큰 Persona에서 수십 분~수 시간.

State: approved
Actual answer: (질문을 다시 짠 D9) B) 1.0처럼 2~10에서 선택 (사용자 답 2026-10-02)
Accepted scope: L3는 Persona마다 토픽 수 2~10을 모두 학습해 C_v 최대를 선택(동점이면 작은 수). 4개 초과 시 `granularity_exceeded` 경고(6-C 배지)만, 자동 병합 없음. `perf` 테스트로 시간 기록. 02-design 3.4와의 차이로 기록(D-235).
History: D9 최종 질문은 '선택 범위' 자체로 다시 짬(A 2~4 선택 · B 1.0처럼 2~10 선택 · C 2~10 계산 + 2~4 선택). D7(1차) 답 "무슨 말인지 모르겠어" → D8(쉬운 설명) 답 "어차피 모든 데이터 사용하지 않는데 왜 5000건이나 표본으로? 그래프는 페르소나/컨텍스트 단위로 찍히는데" → 참고 점수 계산 비용(점마다 LDA 학습)을 설명하고 '5~10 계산 제외' 선택지를 추가해 D9로 다시 질문.

### R6: 대규모(100만 건) 벡터 메모리
Finding: 6, P2, confidence 7/10, 03-plan T2 `vectors: np.ndarray  # float32 [n × dim], L2 정규화`, reviewer Claude(Section 4)
Plan baseline: 대상 벡터 전체를 float32로 한 번에 적재, 10만 건 초과 시 MiniBatchKMeans.
Runtime evidence: 맥미니 메모리 16GB(`sysctl hw.memsize`). 3단계 벡터는 float16 샤드(`vectors/shard-*.f16`). 31만 건 float32 ≈ 1.3GB, 100만 건 ≈ 4GB + sklearn 사본.
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 벡터 적재 | 전체 float32 | 전체를 float16으로 보관(100만 건 ≈ 2GB), 계산은 MiniBatchKMeans `partial_fit` 배치(4,096)마다 float32 변환 · 실루엣/Ward는 표본만 float32 | 계획대로 전체 float32 |
| 시험 | 없음 | `test_large_input_streams`(합성 20만 건, `KMEANS_FULL_MAX` 낮춰 partial_fit 경로 · 결과가 전체 적재와 같은 군집 수 · `tracemalloc` 최대 사용량 기록) | 없음 |
Question D10:
D10 — 100만 건 대비로 벡터를 float16으로 들고 배치마다 변환할까요?
Header: D10 메모리
Options:
A) float16 + 배치 변환 (recommended)
전체 벡터는 float16으로 보관, K-means는 partial_fit 배치마다 float32. 31만 건에서도 같은 결과, 100만 건에서 메모리 약 절반.
B) 계획대로
전체 float32. 31만 건은 문제없고 100만 건에서 16GB 부족 위험.

State: approved
Actual answer: A) float16 + 배치 변환 (사용자 답 2026-10-02, D10)
Accepted scope: T2 `SegmentInput.vectors` float16 보관, T3 대규모 경로 MiniBatchKMeans `partial_fit` 배치(4,096) float32 변환 · 실루엣/Ward 표본만 float32, 테스트 `test_large_input_streams`.
History: —

### R7: 이전 버전에서 6단계 확정값 열람
Finding: 7, P2, confidence 9/10, frontend/src/components/versions/StageVersion.tsx:69 `{view.readonly ? <><h1 …>{index}단계의 저장된 결과를 확인합니다</h1><Card><p>이 버전의 결과 파일과 저장 시각은 버전 비교에서 확인하세요.</p></Card></> : children}`, reviewer Codex outside voice #4 (Claude 확인)
Plan baseline: T14가 `StageVersion stage="stage6"`로 감싼다고만 적음. QA-S7은 "이전 버전 읽기 전용 · stale 배너" 확인.
Runtime evidence: 3단계 이후 경로는 읽기 전용 버전에서 화면 대신 안내 카드(3~5단계와 같은 기존 규칙, 주석 "Never mount their live editors in history mode").
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 이전 버전 6단계 화면 | 안내 카드(기존 규칙) | 기존 규칙 그대로(안내 카드 + 버전 비교) · QA-S7은 안내 카드 확인으로 정정 | 6단계만 읽기 전용 뷰 추가: `GET /segment/{sid}?version=vN`으로 클러스터 · Persona · Context 확정값 목록(편집 불가) |
| 작업 | — | 문구 확인 테스트 1개 | API 버전 파라미터 + 읽기 전용 목록 컴포넌트 + 테스트(human ~1d / CC ~30min) |
Question D12:
D12 — 이전 버전에서 6단계 확정값(클러스터 이름 · Desire 등)을 화면으로 볼 수 있어야 할까요?
Header: D12 이전 버전
Options:
A) 기존 규칙 그대로 (recommended)
3~5단계처럼 안내 카드 + 버전 비교. QA-S7을 안내 카드 확인으로 정정.
B) 6단계 읽기 전용 뷰 추가
이전 버전의 클러스터 · Persona · Context 확정값을 편집 불가 목록으로 보여 줌.

State: approved
Actual answer: A) 기존 규칙 그대로 (사용자 답 2026-10-02, D12)
Accepted scope: 이전 버전 6단계는 기존 `VersionRouteBoundary` 안내 카드 + 버전 비교. 새 코드 없음, QA-S7 정정.
History: —

### R8: 재분할 뒤 오래된 화면의 확정 차단
Finding: 8, P1, confidence 8/10, 03-plan 계약 표 `PUT /segment/{sid}/personas/{id}` 요청 `{name, desire, goals[1..3], confirm: true}`(실행 세대 없음), reviewer Codex outside voice #6 (Claude 확인: ID는 `CL\d+-P\d+`로 재분할 뒤 재사용됨, 같은 버전이라 `assert_writable` 통과)
Plan baseline: 확정 요청은 ID만으로 대상을 찾음.
Runtime evidence: 제안 코드(미구현). 기존 3~5단계 API에도 세대 토큰 패턴은 없음(미확인 범위: `labeling_v2` 제출은 doc_id 기준).
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 실행 세대 | 없음 | 6단계 실행마다 `segmentRun`(UUID)을 `session.segment.run`과 `segment.sqlite`에 기록, 목록 응답에 포함 | 없음 |
| 확정 · 일괄 확정 · 임시 저장 | ID만 | 요청에 `run` 필수, 현재 값과 다르면 409 `stale_run` "다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요." · `drafts.segment`에도 run 저장, 다르면 버림 | ID만 |
| 테스트 | — | `test_api.py::test_stale_run_rejected`(재실행 뒤 이전 run 확정 409) · 프론트 409 문구 | — |
Question D13:
D13 — 다시 나눈 뒤 이전 화면에서 누른 확정을 막을까요?
Header: D13 세대 확인
Options:
A) 실행 세대로 막기 (recommended)
6단계 실행마다 run ID를 붙이고, 확정 · 일괄 확정 · 임시 저장 요청의 run이 현재와 다르면 409와 새로고침 안내. 테스트 추가.
B) ID만으로 저장
오래된 화면의 확정이 새 Persona에 덮어쓰일 수 있음.

State: approved
Actual answer: A) 실행 세대로 막기 (사용자 답 2026-10-02, D13)
Accepted scope: `run` UUID를 실행마다 기록 · 응답에 포함, 확정 · 일괄 확정 · 임시 저장에서 불일치 시 409 `stale_run`(문구 고정), 테스트 `test_stale_run_rejected` + 프론트 문구 매핑.
History: —

Approval readiness: PASS — R1(D3=A) · R2(D4=A) · R3(D5=A, 다시 열어 D11=A) · R4(D6=A) · R5(D9=B) · R6(D10=A) · R7(D12=A) · R8(D13=A), 범위 D1=A · D2=A. Codex 사실 정정 #1 · #2 · #5 · #7은 승인된 설계 계약(채널 = 수집 `source`, pred_entropy = 두 라벨러 엇갈림, few_* 플래그 규칙, dims 정합성)의 구현 보정으로 반영(새 정책 없음).

## 엔지니어링 리뷰 결과 (plan-eng-review, 2026-10-02)

### 데이터 흐름
```
relevant.jsonl ──(doc_id)──┐        derived/docs ── 채널 · 작성자 · 댓글 · 날짜(Codex #1)
derived vectors(f16) ──────┼─ load_input ──┬─ L1 Ward(표본 2만)/K-means(partial_fit f16→f32 배치) ─ ctfidf
derived tokens ────────────┘   nouns/ 캐시  ├─ L2 명사망 Louvain(빈 그래프→Persona 1) ─ centrality 16
                                            └─ L3 LDA 2~10 C_v 최대(>4 경고, 빈 사전→Context 1) ─ 센트로이드 · 밴드
quality(cohesion · boundary · ARI · NPMI · 채널) · KNU 감성 · pred_entropy(export 값) ──┐
dims 표본(LLM, 배치 ID 정합성, llmcache) · 초안(LLM) ──────────────────────────────────┴─ segment.sqlite(+run) · stage_6.json
API(run 세대 확인) ── 6-A → 6-B → 6-C 확정 ── segmentDone · clear_stale(stage6)
```

### NOT in scope
- `emerging` · `lexical_surprise` — 묶음 ②에서 쓰는 곳 옆에 구현(D-229).
- 이전 버전 6단계 읽기 전용 뷰 — 기존 안내 카드 + 버전 비교(D-238).
- 7 · 8단계 화면 · API · Evidence Package — 묶음 ② · ③(D-228). 사이드바에는 비활성 링크만.
- 클러스터 분리 · 병합 실행 — 요청 메모만(설계 3.5).

### What already exists (재사용)
- `app/vectors/store.VectorStore`(f16 샤드 · `get` · `iter_shards`), `app/prep/tokens.tokenize`(Kiwi), `app/known/filter.read_export` 경로 검증, `app/llm/registry.run_task` + `fake.py`, `app/work/worker` Context/heartbeat · `runner.start`, `app/context/versions` · `stale.clear_stale`, `store.atomic_write` · `locked`, 프론트 `components/ds/*` · `SNAGraph` · `StageVersion`/`VersionRouteBoundary` · `usePolling` · `lib/api/train.ts` 패턴.

### Failure modes
| 경로 | 현실적 실패 | 테스트 | 처리 | 사용자에게 |
|---|---|---|---|---|
| load_input | export `source`가 판정 출처라 채널 오표시 | `test_channel_from_derived_not_export` | derived 조인 | 정상 채널 분포 |
| L1 대규모 | 100만 건 메모리 부족 | `test_large_input_streams` | f16 + partial_fit | 진행 표시 |
| L2 | 빈 그래프 · 고립 공동체 | `test_empty_graph_single_persona` | Persona 1 + 플래그 | 6-B 안내 문구 |
| L3 | 빈 사전 · 빈 토픽 · 6개 이상 | `test_empty_dictionary_single_context` · `test_granularity_warning` | Context 1 / 재번호 / 경고 | 6-C 배지 |
| dims | 응답 ID 누락 · 중복 | `test_batch_id_integrity` | 재요청 1회 후 `dims_failed` | stage_6.json 건수 |
| 초안 | LLM 실패 · 형식 초과 | `test_draft_failure_leaves_empty` · `test_persona_draft_clamps` | 빈칸 · 자르기 | "초안을 만들지 못했습니다" |
| 확정 | 재분할 뒤 오래된 탭 | `test_stale_run_rejected` | 409 `stale_run` | 새로고침 안내 |
| 버전 | 4단계부터 다시 뒤 옛 확정 잔존 | `test_restart_from_3_4_5_6_invalidates_segment` | segment 무효화 | 6단계 다시 실행 |
| 워커 | 중단 · 재시작 | `test_resume_skips_done_steps` | 체크포인트 | "이어서 진행" |
- 테스트 · 처리 · 안내가 모두 없는 조용한 실패: 없음(critical gap 0).

### Worktree parallelization strategy
| Step | Modules touched | Depends on |
|---|---|---|
| 픽스처 · 회귀 대비 | backend/tests/fixtures, backend/app/model | — |
| 세그먼트 코어 | backend/app/segment, backend/app/lexicon | 픽스처 |
| 워커 · 버전 · API | backend/app/work, backend/app/context, backend/app/routers | 세그먼트 코어 |
| 프론트 컴포넌트 · 사이드바 | frontend/src/components, frontend/src/lib/logic | — |
| 프론트 화면 | frontend/src/app/pipeline/clustering, frontend/src/lib/api | API 계약 |
- Lane A: 픽스처 → 세그먼트 코어 → 워커 · 버전 · API (backend 순차). Lane B: 프론트 컴포넌트 · 사이드바(T13 · T15) 독립. Lane C: 프론트 화면(T12 · T14)은 API 계약(이 문서) 확정 후 시작 가능, 통합 확인은 T10 뒤.
- 실행 순서: A와 B를 함께 시작, A의 T10 완료 후 C의 통합 테스트. 같은 worktree 안 Codex 위임(하네스 규칙)이며 파일 소유가 겹치지 않는다.

### Implementation Tasks (리뷰에서 나온 추가 작업, 위 Task에 반영됨)
- [x] **E1 (P1, human ~15min / CC ~2min)** — lexicon — KNU 사전 파일 커밋 (R1) · Files: `backend/app/lexicon/knu_senti.json`
- [ ] **E2 (P2, human ~2h / CC ~10min)** — segment.inputs — 명사 캐시 (R2) · Verify: `test_nouns_cached_next_to_derived`
- [ ] **E3 (P1, human ~3h / CC ~10min)** — versions · StepBar — 회귀 계약 + 6단계 무효화 (R3) · Verify: `test_restart_stage3_4_5_unchanged` · `test_restart_from_3_4_5_6_invalidates_segment` · 옛 단계 키 테스트
- [ ] **E4 (P2, human ~30min / CC ~5min)** — QA — 실제 LLM 확인 QA-L1 (R4)
- [ ] **E5 (P1, human ~2h / CC ~10min)** — segment.l3 — 2~10 C_v 선택 · 경고 · perf (R5)
- [ ] **E6 (P2, human ~4h / CC ~15min)** — segment.inputs/l1 — f16 + partial_fit (R6)
- [ ] **E7 (P1, human ~3h / CC ~10min)** — segment API · 화면 — 실행 세대 409 (R8)
- [ ] **E8 (P1, human ~3h / CC ~15min)** — segment.inputs · model/export — 채널 조인 · pred_entropy 소프트 확률 (Codex #1 · #2)
- [ ] **E9 (P1, human ~2h / CC ~10min)** — segment.l2/l3/dims — 빈 그래프 · 빈 사전 · dims ID 정합성 (Codex #5 · #7)

### Completion summary
- Step 0: Scope Challenge — scope reduced per recommendation(D1: 신호 2종 ②로), 구성 유지(D2)
- Architecture Review: 1 issue found(R1)
- Code Quality Review: 1 issue found(R2)
- Test Review: diagram produced, 3 gaps identified(R3 회귀 2 · R4 EVAL 1)
- Performance Review: 2 issues found(R5 · R6)
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 0 items proposed to user(저장소에 TODOS.md 없음, 미룬 항목은 결정 기록)
- Failure modes: 0 critical gaps flagged
- Unresolved decisions: 0 in this review
- Outside voice: codex, completed — 7 findings(사실 정정 4건 반영, 결정 3건 D11 · D12 · D13)
- Parallelization: 3 lanes, 2 parallel / 1 sequential
- Lake Score: 8/8 coverage choices chose the complete option(D3 · D4 · D5 · D6 · D10 · D11 · D13 complete, D9 사용자 선택 B는 범위 선택이라 제외, D12 A=8/10 기존 규칙 선택)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | `codex exec` (plan-eng-review outside voice) | Independent 2nd opinion | 1 | completed | 7 findings, 7 resolved(4 정정 · 3 결정) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open (mapped) | 13 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR (FULL) | score: 6/10 → 8/10, 6 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex · plan-review · completed · 7 findings(P1 6 · P2 1), 모두 검증 후 반영.
- **CROSS-MODEL:** Claude 리뷰(6건)와 Codex(7건)는 겹치지 않음 — Codex는 실제 export 데이터 손실 · 버전 무효화 · 동시 편집을 추가로 찾음.
- **VERDICT:** DESIGN CLEARED. ENG — 발견 13건 모두 결정 · 계획 반영(남은 결정 0), 상태값은 규칙상 issues_open(해결된 발견도 집계). 계획 승인 요청 가능.

NO UNRESOLVED DECISIONS
