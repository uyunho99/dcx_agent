# DCX 2.0 묶음 ③ (8단계 페르소나 · 인사이트 · 컨셉) · 구현 계획 + QA 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evidence Package 하나를 입력으로 Persona 카드(8-A~D) · 세션 전체 Opportunity Map · 인사이트(8-E) · 경험 디자인 컨셉(8-F)을 만들고, 채팅으로 다듬고 판을 되돌리며 확정한다. 모든 서술 칸은 근거 번호로 원문까지 따라가고 인식론 등급(관측 · 추론 · 추측)을 보인다.

**Architecture:** 새 패키지 `backend/app/persona/`(패키지 읽기 → 카드(Context 4개 묶음) → 등급 · 처방 · 제약 · 스코프 → 맵 · 트리 → 인사이트 · 컨셉 · 채팅 판)를 `persona` · `insight` 워커가 돈다. 결과는 `versions/vN/persona/*.json`. 7단계는 병행 개발 중이므로 가짜 Evidence Package 픽스처(D-301 · D-304)로 시험하고, 마지막 Task에서 ②에 합류한다.

**Tech Stack:** FastAPI · Pydantic v2 · NumPy · 기존 `app/llm` 레지스트리 · 세션 임베더 / Next.js 16 · SVG · Vitest.

**Spec:** [`02-design.md`](02-design.md) + [`../dcx2-stage6-8/02-design.md`](../dcx2-stage6-8/02-design.md) 2.4 · 2.5 · 5 · 6~11 · 14절. 결정: [`decision-log.md`](decision-log.md) D-301~ · 공통 원장 D-201~D-248.

## 전역 제약

- 구현은 모든 Task를 Codex(`codex:codex-rescue --wait --fresh`, 쓰기)가 TDD로 한다. controller가 확인 뒤 커밋.
- 테스트는 네트워크 · 키 없이 돈다. LLM은 `FakeBackend`(작업 이름별 `tests/fixtures/llm/{task}.json` 또는 `responses=`), 임베더는 가짜.
- LLM 호출은 `app/llm` 레지스트리 + 출력 스키마만. **LLM은 숫자를 쓰지 않는다**(지표 · 레이더 · 막대 · 근거 원문 · basis는 코드가 채움, 5.8).
- 0단계 `targetScope`는 `persona.card` · `persona.summary` 프롬프트에 넣지 않는다(D-210, 테스트로 고정). 사내 제약 · 핵심 지표 · 분석 목적은 처방 프롬프트에만.
- Persona 수 · 이름 · Desire · Goal은 6단계 확정값 그대로(AC-10). 8단계는 만들지 않는다.
- 화면 문구는 02-design 9절 그대로. 등급은 색만으로 구분하지 않는다(모양 + 글자). 파란 주요 버튼은 화면당 하나.
- 이 브랜치에는 `app/evidence/`가 없다. 7단계 산출물은 `versions/vN/evidence/package.json` 파일 계약으로만 읽는다(D-301).

## 파라미터 (`app/persona/params.py`)

```python
CARD_CHUNK = 4                       # D-302
TRACE_MIN = 0.5                      # 5.3 Traceable Support 하향 임계(잠정)
OBSERVED_FIELDS = ('state', 'barrier', 'usage_context')
INFERRED_FIELDS = ('emotion', 'jtbd', 'unmet_need')
S_LINE = 0.5                         # 5.5 가로 기준선
STAR_NOVELTY = ('high', 'very_high'); STAR_MIN = 2
RADAR_AXES = {'Computed': '맞춤형 서비스가 필요해', 'Connected': '실시간으로 직접 보고 싶어', 'Shared': '함께 즐기고 싶어'}
INSIGHT_RANGE = (3, 8)
CX_4D = ('정신적', '물리적', '문화적', '시스템')
PROVISIONAL = ('odi', 'persona_metrics', 'TRACE_MIN', 'RADAR_AXES')
```

## 파일 소유 · 의존 관계

| Task | 소유 파일 | 의존 | 병렬 |
|---|---|---|---|
| T1 픽스처 · 읽기 모델 · 가짜 응답 | `tests/fixtures/evidence_package.py`, `app/persona/{__init__,package}.py`, `tests/fixtures/llm/persona.*.json` · `insight.*.json`, `tests/scripts/make_persona_qa.py`, `tests/persona/test_package.py` | – | – |
| T2 params · 저장 · 판 | `app/persona/{params,store}.py`, `tests/persona/test_store.py` | T1 | T3 · T4 |
| T3 등급 | `app/persona/grade.py`, `tests/persona/test_grade.py` | T1 | T2 · T4 |
| T4 맵 · 트리 | `app/persona/{opportunity,tree}.py`, `tests/persona/test_opportunity.py` · `test_tree.py` | T1 | T2 · T3 |
| T5 카드 생성 | `app/persona/cards.py` · `prompts/{card,summary}.v1.md`, `tests/persona/test_cards.py` | T2 · T3 | T6 |
| T6 처방 · 제약 · 스코프 | `app/persona/prescribe.py` · `prompts/{prescribe,constraint_check,scope}.v1.md`, `tests/persona/test_prescribe.py` | T2 | T5 |
| T7 persona 워커 · 버전 · 완료 | `app/persona/pipeline.py`, `app/work/worker.py`, `app/context/versions.py`, `app/routers/sessions.py`, `tests/persona/test_pipeline.py`, `tests/context/test_versions_stage8.py` | T4 · T5 · T6 | – |
| T8 인사이트 8-E | `app/persona/insights.py` · `radar.py` · `prompts/derive.v1.md`, `tests/persona/test_insights.py` · `test_radar.py` | T2 · T4 | T9 |
| T9 컨셉 8-F | `app/persona/concepts.py` · `prompts/concept.v1.md`, `tests/persona/test_concepts.py` | T2 · T6 | T8 |
| T10 채팅 · 판 · insight 워커 | `app/persona/{chat,insight_pipeline}.py` · `prompts/edit.v1.md`, `tests/persona/test_chat.py` | T8 · T9 · T7 | – |
| T11 API · 추천 | `app/routers/stage8.py`, `app/routers/known.py`, `app/known/{store,models}.py`, `app/main.py`, `tests/persona/test_api.py`, `tests/known/test_suggestions.py` | T7 · T10 | T12 |
| T12 프론트 API · 로직 | `lib/api/{persona,insight}.ts`, `lib/types.ts`, `components/persona/personaView.ts`, 테스트 | T11 계약 | T11 · T13 |
| T13 공용 컴포넌트 | `components/persona/{GradeMark,ProvisionalBadge,CCMTable,OpportunityMap,ContextTable,HierarchyTree,Radar,OpportunityBars,JourneyTable,RevisionList}.tsx`, 테스트 | T12 | – |
| T14 페르소나 화면 | `components/persona/PersonaScreen.tsx`, `app/pipeline/personas/page.tsx`(분기), 테스트 | T13 | T15 |
| T15 인사이트 화면 · 경로 · 서랍 | `components/persona/InsightScreen.tsx`, `app/pipeline/insights/page.tsx`(생성), `app/insights/page.tsx`(이동 안내/리다이렉트), `components/StepBar.tsx`, `lib/logic/completedThrough.ts`, `components/known/KnownInsightsDrawer.tsx`, 테스트 | T13 | T14 |
| T16 통합 | `tests/persona/test_integration.py` | T11 | – |
| T17 ② 합류(보류) | `app/persona/package.py`, `tests/persona/test_package_contract.py` | ② 완료 | – |

## 계약

### Python 내부 인터페이스

```python
# app/persona/package.py (T1) — 2.4 읽기 검증(필수 키만, 나머지 허용)
class Package(BaseModel): schema_: str = Field(alias='schema'); version: str; params: dict; personas: list[PersonaBlock]
def load_package(sid: str, version: str) -> Package          # 없으면 PackageMissing
def evidence_index(block: PersonaBlock) -> dict[str, EvidenceRef]   # 'E1'… Persona 전체 번호, context_id · role 포함

# tests/fixtures/evidence_package.py (T1, D-304)
def make_package(*, personas=4, contexts=(3, 3, 3, 2), big_persona_contexts: int | None = None, seed=42) -> dict
    # 구역 A~F 각 ≥1, ★ 조건 Context 2, counter_context 1, verified False 인용 섞음, 근거 0건 Context 1
def write_session_with_package(local_data_dir, **kw) -> SynthSession   # segment 확정값 + package.json 버전 폴더에

# app/persona/store.py (T2) — versions/vN/persona/
class PersonaStore:
    @classmethod
    def open(cls, sid, version) -> 'PersonaStore'
    def read(self, name: str) -> dict | None                 # cards · map · tree · insights · concepts · stage_8
    def write(self, name: str, data: dict) -> None           # 임시 파일 → os.replace
    def new_revision(self, name: str, items, *, by: str, message: str | None) -> int   # history 유지
    def revert(self, name: str, revision: int) -> int        # 그 판을 새 판으로 복사
    def append_chat(self, row: dict) -> None

# app/persona/grade.py (T3)
def grade_field(field: str, cites: list[str], refs: dict[str, EvidenceRef]) -> Literal['observed','inferred','speculated']
def traceable_support(fields: dict[str, dict], refs) -> float
def grade_card(card: dict, refs) -> dict      # {context_id: {field: grade}} + 하향 적용 + trace[]

# app/persona/opportunity.py (T4)
def baselines(points: list[tuple[float, float]]) -> dict     # {s_line: 0.5, diag1: ((0, S평균),(1,1)), diag2: ((I평균,0),(1,1))}
def zone(i: float, s: float, base: dict) -> Literal['A','B','C','D','E','F']   # 선 위 정확히 → 위쪽(D-307)
def star(context: dict, odi_mean: float) -> bool
def build_map(package: Package) -> dict        # map.json: points[{context_id, persona_id, cluster_id, i, s, odi, zone, star, counter, shape, tone}], base, legend
# app/persona/tree.py
def build_tree(package, product: str) -> dict   # 제품 → Cluster → Persona → Context, size = doc_count

# app/persona/cards.py (T5)
def generate_card(sid, block: PersonaBlock, *, run_task) -> CardResult   # chunk ≤4 → persona.card, 다음 persona.summary; failed on 2 schema failures in any call
# app/persona/prescribe.py (T6)
def prescribe(sid, card_summary, project_context, *, run_task) -> dict    # {direction, target_metric, contribution, journey_hypothesis, constraint: [{constraint, verdict, reason}], blocked: bool, represcribed: bool}
def scope_check(sid, card_summary, project_context, *, run_task) -> dict  # {verdict: in|outside, reason}

# app/persona/insights.py · radar.py (T8)
def derive(sid, version, *, run_task, embedder) -> int      # 새 판 번호
def radar(context_centroids: dict[str, np.ndarray], weights: dict[str, int], axes_vecs: np.ndarray) -> dict  # 원값 + 백분위
def opportunity_bars(insights, odi_by_context) -> dict      # {bars, mean, targets}
# app/persona/concepts.py (T9)
def make_concept(sid, version, insight_id, *, run_task) -> dict
# app/persona/chat.py (T10)
def edit(sid, version, target: str, message: str, *, run_task) -> dict   # {ok, revision | reason}
```

### API (T11 ↔ T12)

| 메서드 · 경로 | 응답 | 오류 kind |
|---|---|---|
| `POST /persona/{sid}/run?version=` `{fresh?, personas?}` | `{runId}` | `evidence_required`(409, package 없음) · `running` · `locked` |
| `GET /persona/{sid}/status` | `{status, run, progress, personas: [{id, status, error}], stage8?}` | – |
| `GET /persona/{sid}/cards` · `/cards/{id}` | 카드 + 등급 + trace + 처방 + scope | `not_ready` |
| `POST /persona/{sid}/cards/{id}/retry` `{run}` | status | `stale_run` |
| `GET /persona/{sid}/map` · `/tree` | map.json · tree.json | `not_ready` |
| `POST /insight/{sid}/run` `{mode: 'derive'\|'concept', target?}` | `{runId}` | `persona_required` |
| `GET /insight/{sid}` | `{insights: {revision, items, history[]}, concepts: {…}, bars, radar}` | – |
| `POST /insight/{sid}/concept/{id}` | `{runId}` | – |
| `POST /insight/{sid}/chat` `{target: 'insights'\|'concept:{id}', message}` | `{ok: true, revision}` 또는 `{ok: false, message: '요청을 반영하지 못했습니다. 다르게 말해 주세요.'}` | – |
| `POST /insight/{sid}/revert` `{target, revision}` | `{revision}` | `not_found` |
| `PUT /insight/{sid}/confirm` `{ids: []}` | `{confirmed}` | – |
| `GET /known/{sid}/suggestions` | `{items: [{sessionId, insightId, title, painPoint}]}` | – |
| `POST /known/{sid}` 에 `from: 'prev_session'` 허용(추천 추가 전용) | 기존 | – |

### 완료 · 버전 (T7 · T10 ↔ T15)

- `session.persona = {status, run, progress, savedAt}`, `session.insight = {status, revision, confirmed: [], savedAt}`.
- `_completion`: `personaDone`(persona.status done ∧ 'stage8' ∉ stale) → completedThrough 8, `insightDone`(insights.json 판 ≥1 ∧ not stale) → 인사이트 단계(9).
- 7단계 결과가 바뀌면(package `run` ≠ cards.json `package_run`) persona stale. versions `_restart` ≤8: 이미 `persona/` 삭제 — `completion.personaDone/insightDone` 제거 추가.

## Task별 단계

### T1 가짜 Evidence Package · 읽기 모델 · 가짜 응답 · QA 데이터 (D-301 · D-304)
- [ ] RED `tests/persona/test_package.py`: `test_fixture_has_all_zones`(A~F 각 ≥1, opportunity.zone은 T4 전이므로 기대 좌표로 확인), `test_fixture_star_two`, `test_fixture_counter_and_unverified`, `test_fixture_zero_evidence_context`, `test_big_persona_ten_contexts`, `test_load_package_validates_required`(필수 키 빠지면 오류, 모르는 키 허용), `test_evidence_index_renumbers_persona_wide`.
- [ ] 가짜 응답 헬퍼 `fake_persona_backend(package)`: card · summary · prescribe · constraint_check · scope · derive · concept · edit — 근거 번호 · context_id를 실제 픽스처 값으로.
- [ ] `tests/scripts/make_persona_qa.py LOCAL_DATA_DIR`: 합성 세션(segment 확정) + package.json → 화면 QA 바로 가능.
- [ ] FAIL → 구현 → PASS.

### T2 params · 저장 · 판
- [ ] RED `tests/persona/test_store.py`: 원자적 쓰기(쓰기 중 예외 → 이전 파일 유지), `new_revision` history 누적, `revert`가 새 판 생성(덮어쓰기 아님) · history에 `by: 'revert'`, chat.jsonl 추가.
- [ ] FAIL → 구현 → PASS.

### T3 인식론 등급 (5.3, D-213)
- [ ] RED `tests/persona/test_grade.py`: 매개변수 표 — (state, [verified E] → observed), (state, [unverified E] → inferred), (emotion, [verified] → inferred), (barrier, [] → speculated), (state, ['E99' 없음] → speculated), (intent → 항상 speculated), traceable_support 0.4 → 그 Context 필드 한 단계 하향(observed → inferred, inferred → speculated), null 칸은 등급 없음.
- [ ] FAIL → 구현 → PASS.

### T4 Opportunity Map · 트리 (5.5, D-225 · D-307)
- [ ] RED `tests/persona/test_opportunity.py`: `test_zone_table`(대표 점 6개 → A~F), `test_boundary_goes_upper`(S = 0.5 정확히 → 위쪽, 사선 위 정확히 → Overserved), `test_star_rule`(novelty high 2건 ∧ odi ≥ 평균 → ★, 1건 → 없음), `test_shapes_and_tones`(클러스터 5종 모양 · 6번째부터 원 + 라벨, Persona 명도 3단계), `test_counter_hollow`.
- [ ] RED `test_tree.py`: 3층 구조 · size = doc_count.
- [ ] FAIL → 구현 → PASS.

### T5 카드 생성 (5.2, D-302 · D-210)
- [ ] RED `tests/persona/test_cards.py`: `test_chunks_of_four`(Context 10 → card 3회 + summary 1회), `test_cite_renumbered`(묶음 안 E1 → Persona 번호, 원래 근거 가리킴), `test_action_from_6c_not_generated`, `test_dims_situation_refined_only`(situation_origin dims → 원값 유지 범위), `test_target_scope_not_in_prompt`(프롬프트 문자열에 targetScope 값 없음), `test_desire_goal_equal_6b`(AC-10), `test_schema_fail_twice_marks_failed`(다른 Persona 계속), `test_null_when_no_evidence`(근거 0건 Context 칸 null), `test_sensitivity_ordinal_only`(상/중/하/null 외 거부).
- [ ] FAIL → 구현 → PASS.

### T6 처방 · 제약 · 스코프 (5.4)
- [ ] RED `tests/persona/test_prescribe.py`: `test_violation_represcribe_once`(1차 violates → 이유 붙여 재처방 1회), `test_blocked_after_second_violation`(문구 "사내 제약 '의료적 효과 표현 금지'를 지키는 처방을 만들지 못했습니다."), `test_review_not_blocking`, `test_scope_outside_future`, `test_scope_separate_call`(카드 호출과 다른 작업 이름 · 프롬프트에 카드 생성 지시 없음).
- [ ] FAIL → 구현 → PASS.

### T7 persona 워커 · 이어 하기 · 버전 · 완료
- [ ] RED `tests/persona/test_pipeline.py`: 전부 생성 → cards/map/tree/stage_8 저장, `test_resume_skips_done_personas`, `test_one_persona_failure_isolated`(문구 "이 페르소나 카드를 만들지 못했습니다." + retry), `test_all_backend_failures_interrupt`, `test_package_changed_marks_stale`, `test_stale_run_409`, `test_stage8_report_fields`(5.10 항목).
- [ ] RED `tests/context/test_versions_stage8.py`: 8부터 다시 = persona만 삭제(segment · evidence 유지), 6 · 7부터도 persona 삭제, completion 키 제거, `compare(stage8)` 요약.
- [ ] FAIL → 구현 → PASS.

### T8 인사이트 8-E (5.6)
- [ ] RED `tests/persona/test_insights.py`: 3~8개 아니면 1회 재생성 후 실패 문구 "인사이트를 만들지 못했습니다. 다시 시도하세요.", `test_known_badge`(known_ki_id → 배지), `test_bars_mean_and_targets`(평균선 이상만 8-F 기본 대상), `test_llm_numbers_ignored`(응답에 숫자 필드가 있어도 코드 값 사용), `test_confirm_sets_session`.
- [ ] RED `test_radar.py`: 가중 평균 · 백분위 · 축 문장 임베딩 `input_type` 지원 시 'query'(임베더가 인자를 받지 않으면 기본 호출 — ② 합류 전 호환).
- [ ] FAIL → 구현 → PASS.

### T9 컨셉 8-F (5.7)
- [ ] RED `tests/persona/test_concepts.py`: `test_profile_always_speculated`, `test_basis_filled_by_code`("근거 45건 · 작성자 26명에서 종합" 형식, 숫자는 패키지에서), `test_pain_points_from_package`(원문 · 채널 · 위치 · Context ID 코드 채움), `test_asis_context_validation_regen_once`, `test_cx4d_distribution`, `test_constraint_check_reused`.
- [ ] FAIL → 구현 → PASS.

### T10 채팅 수정 · 판 · insight 워커 (5.8, D-208)
- [ ] RED `tests/persona/test_chat.py`: 유효 수정 → 새 판 + history(by chat, message), `test_invalid_schema_keeps_revision`(문구), `test_bad_cite_rejected`(없는 근거 번호), `test_codes_recomputed_after_edit`(레이더 · 막대 다시 계산), `test_revert_creates_revision`, `test_chat_jsonl_appended`, insight 워커 derive/concept 모드 · 이어 하기.
- [ ] FAIL → 구현 → PASS.

### T11 API · 이전 세션 추천 (설계 8절, D-305 · D-217)
- [ ] RED `tests/persona/test_api.py`: 표의 경로 전부 · 오류 kind, `test_run_409_without_package`(문구 "근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다."), 읽기 전용 버전 쓰기 거부.
- [ ] RED `tests/known/test_suggestions.py`: 같은 bk 다른 세션 확정 인사이트가 suggestions에 보임 · 다른 bk 안 보임 · `initialize` 뒤에도 Known 목록에 자동으로 없음 · `POST /known` `from: prev_session`으로만 추가.
- [ ] FAIL → 구현 → PASS.

### T12 프론트 API · 타입 · 로직
- [ ] `lib/api/persona.ts` · `insight.ts`(계약 1:1), 타입, `personaView.ts`: `gradeLabel`('관측' · '추론' · '추측' + 모양 id), `sortContexts(rows, key, dir)`, `foldColumns(n)`(≤4 → 1단, 5~8 → 2단 4열, 9~10 → 2단 5열), `zoneName`(A Exciting … F At-risk), `cxCounts`.
- [ ] Vitest RED → GREEN.

### T13 공용 컴포넌트 (02-design 10절)
- [ ] `GradeMark`(●▲✕ 모양 + 글자, 색 보조), `ProvisionalBadge`("잠정"), `CCMTable`(2단 접기 · 칸 버튼 Enter/Space · `aria-expanded` · 근거 펼침), `OpportunityMap`(SVG `role=img` + aria-label 구역별 수, 모양 · 명도 · 선택만 파랑 · 범례 칩 토글 · ★), `ContextTable`(정렬 · 포커스/호버 ↔ 점 강조 · "카드 열기"), `HierarchyTree`, `Radar`, `OpportunityBars`(평균선), `JourneyTable`(AS-IS · TO-BE ⚪ 처방 · 4D-CX 분포), `RevisionList`(판 보기 · "이 판으로 되돌리기").
- [ ] Vitest 컴포넌트별 렌더 · 키보드 · 접근성 속성.

### T14 페르소나 화면 (5.9, D-222 · D-227 · D-303)
- [ ] `/pipeline/personas`: `prep.derivedRef` 있으면 `PersonaScreen`, 없으면 기존 화면. `[전체 맵 | Persona 카드]`(전체 맵 먼저), 왼쪽 Persona 목록(클러스터별 · FUTURE · 상태 배지), 헤더(근거 n건 · 작성자 n명 · Context n개), 탭 8-A CCM · 8-B 수렴("의도 ≠ 행동" 고정 문구) · 8-C 속성 · 8-D 처방(제약 ✓ ⚠ · 차단 문구) · 구조 트리. 패키지 없음 → "근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다." + [근거 탐색으로]. 주요 버튼: "페르소나 만들기" → 완료 후 "인사이트 도출".
- [ ] Vitest: 두 보기 전환 · 점 클릭 → 카드 · 표 정렬 · 실패 Persona 다시 만들기 · 옛 세션 분기.

### T15 인사이트 화면 · 경로 · 서랍 추천 (5.9, D-305 · D-306)
- [ ] `/pipeline/insights`: 왼쪽 2/3 인사이트 카드(제목 · pain point · Context 칩 · 레이더 · Known 배지 · 확정 체크) + 막대, 선택 → 8-F(🔴 합성값 · Pain Points · JOURNEY · 4D-CX · 제약), 오른쪽 1/3 채팅(대상 선택) · 판 목록. 기존 `/insights` → `/pipeline/insights` 리다이렉트, 옛 세션은 그 경로에서 기존 화면.
- [ ] `StepBar` 근거 탐색 경로는 ②가 채움 — 여기선 "인사이트" 경로 `/pipeline/insights`, completedThrough personaDone → 8 · insightDone → 9.
- [ ] `KnownInsightsDrawer` 접힌 "이전 세션 추천" 구역 + [추가].
- [ ] Vitest: 채팅 실패 문구 · 판 되돌리기 · 확정 · 추천 추가.

### T16 통합
- [ ] `test_integration.py::test_package_to_insights_offline`: 픽스처 세션 → persona 워커 → insight derive → concept 1개 → chat 1회 → revert, 외부 소켓 0, stage_8.json 항목.

### T17 ② 합류 (보류, D-301)
- [ ] ②가 merge되면: 이 브랜치를 ② 위로 rebase, `load_package`가 `app.evidence.package.EvidencePackage`로 검증, `test_package_contract.py`: ② 합성 통합 테스트 출력 ↔ 픽스처 키 집합 동일. ② 미완이면 이 Task는 UAT 보고서에 "보류"로.

## Review Focus

1. Persona 이름 · Desire를 6단계에서 나중에 바꾼 버전(8단계는 옛 패키지) — T7 `test_package_changed_marks_stale`에 "6단계 확정값만 바뀐 경우"도 stale.
2. Context 열 10개 CCM이 1024px에서 넘침 — T13 `test_ccm_ten_columns_fold_no_overflow`.
3. 인사이트 채팅이 이전 판의 context_ids를 없는 ID로 바꿈 — T10 `test_edit_unknown_context_rejected`.
4. 같은 bk 이전 세션이 많아 추천이 수십 개 — T11 `test_suggestions_limit_recent_20`(최근 20개, 같은 제목 중복 제거).
5. 맵 점이 같은 좌표에 겹침 — T13 `test_overlapping_points_table_lists_all`(표에는 모두, SVG는 겹침 그대로 + 개수 툴팁).

## 검증 명령

```bash
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

## 브라우저 QA 계획

- 시작(② QA와 동시에 돌 수 있게 포트 분리): 백엔드 `cd backend && STORAGE=local LOCAL_DATA_DIR=<scratch>/qa-data-8 LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3321 .venv/bin/uvicorn app.main:app --port 8321`, 프론트 `NEXT_PUBLIC_API_URL=http://localhost:8321 NEXT_PUBLIC_INTERNAL_TOOLS=true node_modules/.bin/next dev frontend -p 3321`.
- 데이터: `backend/.venv/bin/python backend/tests/scripts/make_persona_qa.py <scratch>/qa-data-8`.

| ID | 시나리오 | 기대 |
|---|---|---|
| QA-P1 | 패키지 없는 세션 `/pipeline/personas` | "근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다." + [근거 탐색으로] |
| QA-P2 | 페르소나 만들기 → 전체 맵 | 점 모양 · 명도 · ★ 2 · 반례 속 빈 점, 범례 칩 토글, 맵 아래 표 정렬 · 행 포커스 ↔ 점 강조 |
| QA-P3 | 점 클릭 → Persona 카드 8-A | Desire · Goal = 6-B 값, CCM 칸 등급(모양 + 글자), 칸 Enter로 근거 펼침, 미확인 인용 칸 툴팁 "인용 문장을 원문에서 찾지 못해 추론으로 낮췄습니다." |
| QA-P4 | Context 10개 Persona | CCM 2단 접기, 1024px 가로 스크롤 없음 |
| QA-P5 | 8-B · 8-C · 8-D | "의도 ≠ 행동" 문구, 속성 null 칸 "근거 부족", 처방 차단 문구(픽스처 위반 Persona), FUTURE 배지 |
| QA-P6 | 카드 실패 Persona | "이 페르소나 카드를 만들지 못했습니다. [다시 만들기]" |
| QA-I1 | 인사이트 도출 | 카드 3~8 · 레이더 · 막대 평균선 · Known 배지 |
| QA-I2 | 8-F 컨셉 | 🔴 합성값 배지 · Pain Points 원문 · 채널 · 위치 · JOURNEY · 4D-CX 분포 |
| QA-I3 | 채팅 수정 · 실패 · 되돌리기 | 새 판 하이라이트, 실패 문구, "이 판으로 되돌리기" |
| QA-I4 | 확정 → 같은 bk 새 세션 서랍 | "이전 세션 추천"에만 보임 · [추가]해야 들어감 |
| QA-V | 8부터 다시 · 옛 세션 · `/insights` 이동 | 카드 비움 · 6/7 유지, 옛 세션 기존 화면, `/insights` → `/pipeline/insights` |
| QA-K | 키보드 · 낭독기 | 맵 표 · CCM 칸 · 탭 전환 키보드만으로 |
| QA-L3 | 실제 기본 LLM으로 Persona 1개 카드 + 인사이트 | 체크리스트: cite가 실제 근거 번호 · 등급 분포 · null 속성 · 처방 제약 동작 · 금지 표현 없음. 키 없으면 "미실행(키 없음)" |

## 수용 기준 연결

| AC | Task · 테스트 | QA |
|---|---|---|
| AC-10 6단계 확정값 그대로 · 근거 인용 · 반례 동반 | T5 `test_desire_goal_equal_6b` · `test_cite_renumbered` | QA-P3 |
| AC-11 인식론 등급 · Traceable 하향 · null 허용 | T3 · T5 | QA-P3 · P5 |
| AC-12 처방 제약 · 스코프 FUTURE · 맵 구역 · ★ | T4 · T6 | QA-P2 · P5 |
| AC-13 인사이트 · 컨셉 · 채팅 수정 · 되돌리기 · 확정 | T8~T10 | QA-I1~I4 |
| AC-14 오프라인 · 회귀 · 버전 · 옛 세션 | T7 버전 · T16 · 검증 명령 | QA-V |

## 되돌리기

- `feature/dcx2-stage8`을 merge하지 않으면 영향 없음. merge 뒤: merge 커밋 revert, 데이터는 `versions/vN/persona/` 삭제로 원상. `/insights` 리다이렉트는 revert로 복구.

## 엔지니어링 리뷰 (2026-10-02, controller 자체 점검)

- **데이터 흐름:** package.json(7) + segment.sqlite(확정값 · 센트로이드) + projectContext → 카드(Context 4개 묶음 → 요약) → 등급(코드) → 처방 · 제약 · 스코프 → map · tree → 인사이트(판) → 컨셉(판) → 채팅 수정(판) · 되돌리기. LLM이 쓴 숫자는 버리고 코드 값으로 다시 채운다.
- **실패 모드:** 카드 스키마 2회 불량 → 그 Persona만 실패 · 다시 만들기 / 처방 제약 위반 지속 → 차단 문구 / 인사이트 개수 범위 밖 → 1회 재생성 후 실패 문구 / 채팅 수정 불량 → 현재 판 유지 / 7단계 결과 변경 → stale + 409.
- **병렬 구현:** T2 ∥ T3 ∥ T4, T5 ∥ T6, T8 ∥ T9, T11 ∥ T12, T14 ∥ T15. 공유 파일(`worker.py` · `versions.py` · `sessions.py`)은 T7 한 곳.
- **묶음 ②와의 충돌 지점:** 두 브랜치 모두 `worker.py` · `versions.py` · `sessions.py` · `StepBar.tsx` · `completedThrough.ts`를 고친다. ②가 먼저 merge, ③은 T17 rebase에서 해결(D-308).
- **새 사용자 결정 없음.** 판단 D-308은 원장에 기록.
