# 0단계 과제 유형 · 생각하는 페르소나 · 구현 계획 + QA 계획

> 구현은 Codex(`codex:codex-rescue`, `--wait --fresh`, 쓰기)에 위임하고 Claude는 분해 · 위임 · 리뷰만 한다. Task마다 RED → GREEN → 리팩터링, 보고서는 `.superpowers/sdd/03-plan/task-<ID>-report.md`.

**목표:** 0단계에 과제 유형(지표 개선형 / 탐색·기획형) 분기, 구조화된 핵심 지표, 선택형 · 직접 입력 포지셔닝, 생각하는 페르소나(디멘션 태그)를 넣고, 분석 목적 칩을 없애고, R1 프롬프트가 과제 유형에 따라 다른 지시를 받게 한다. 기존 세션은 그대로 동작한다.
**설계:** `02-design.md`(디자인 리뷰 D-315~D-321 포함) · 목업 `mockups/index.html` · 결정 `decision-log.md` D-301~D-321 · 기획 `01-brainstorm.md`(AC-03 · 06 · 07은 설계 머리말의 "기획과의 차이"대로 읽는다).
**기술:** Python 3.12 FastAPI · Pydantic v2(`backend/.venv`), Next.js + Vitest(`frontend`, `environment: node`, `src/**/*.test.ts`만). 새 의존성 없음.

## 전역 제약
- 맥미니 로컬 전용. 키 값 비노출. 한국어 UI 문구는 02-design 5.3 · 5.4 표의 글자 그대로.
- 테스트는 네트워크 · 키 없이 돈다(`LLM_BACKEND=fake`).
- **예전 세션 바이트 동일:** `taskMode`가 없고 `personaSeeds`가 없고 지표가 글자 목록이고 포지셔닝이 기본 선택지인 세션의 `render_context_md` 출력은 이 작업 전과 바이트 단위로 같아야 한다(AC-09). T1 첫 단계에서 만드는 골든 파일로 고정한다(F3).
- `schemaVersion`은 `1` 그대로. 새 필드는 모두 기본값을 둔다. 저장 데이터 일괄 변환 없음.
- `backend/app/context/versions.py`는 건드리지 않는다(6~8단계 브랜치가 수정 중, D-311).
- 백엔드 · 프론트의 기존 테스트를 깨지 않는다. 기존 테스트 기대값을 바꿔야 하면 그 이유를 Task 보고서에 쓴다(허용: `PROMPT_VERSION[1]` 값, `startForm.test.ts`의 빈 폼 기대값).
- 화면당 파란(primary) 버튼 하나(D-137): 0단계는 "키워드 생성 시작하기"만. 새 버튼은 모두 기본 · quiet.
- 색은 기존 토큰만(`--action`, `--action-soft`, `--line`, `--warning` 등). 새 CSS 변수 없음.

## Review Focus (테스트가 직접 다루지 않기 쉬운 입력 → 담당 Task에 테스트 추가)
1. **예전 세션을 PATCH `/context/{sid}`로 일부만 고침**(예: `oneLiner`만): `taskMode` 없음 → 예전 규칙 그대로 통과, md 바이트 동일 → T1 `test_patch_legacy_keeps_rules` · `test_legacy_bytes_identical`.
2. **같은 축에 기본 선택지와 직접 입력이 둘 다 옴**(화면 우회 · 오래된 임시 저장본) → 서버 422 → T1 `test_positioning_both_rejected`.
3. **페르소나 줄에 공백만 · 41자 · 같은 이름 반복 · 21번째** → 화면은 추가 거부, 서버는 422(공백 · 41자 · 21개) → T1 `test_persona_seed_limits`, T4 `addPersonaSeed` 테스트.
4. **예전 임시 저장본(localStorage `dcx_start_draft` · `drafts.start`)에 글자 지표 · `analysisGoal`** → 불러오면 구조 지표로 바뀌고 `analysisGoal`은 그대로 보존 → T4 `mergeStartForm` 테스트.
5. **지표 개선형으로 바꿨는데 예전 포지셔닝 값이 남음** → 접힌 영역이 펼쳐진 채 시작하고 md에도 나옴(지우지 않은 값) → T4 `positioningOpen` 테스트 · QA-S4.

## 파일 소유 · 의존 관계

| Task | 내용 | 의존 | 소유 파일(C 새로 · M 수정) |
|---|---|---|---|
| T1 | 모델 · 라벨 · 렌더링 · API 검증 · R1 뒤 변경 경고 | — | M `backend/app/context/models.py` · M `backend/app/context/labels.py` · M `backend/app/context/render.py` · M `backend/app/routers/context.py`(`_save_context` 경고 대상만, R2) · M `frontend/src/lib/contextLabels.ts` · C `backend/tests/context/fixtures/legacy_context.md` · C `backend/tests/context/test_models_task_mode.py` · C `backend/tests/context/test_render_task_mode.py` · C `backend/tests/context/test_api_task_mode.py` |
| T2 | (F3로 T1에 합침 — ID 비워 둠) | — | — |
| T3 | R1 프롬프트 분기 | T1 | C `backend/app/keywords/prompts/r1.v2.md` · M `backend/app/keywords/prompts.py` · M `backend/app/keywords/rounds.py`(`_inputs`만) · M `backend/tests/keywords/test_prompts.py` · C `backend/tests/keywords/test_task_focus.py` |
| T4 | 화면 타입 · 폼 로직 | — | M `frontend/src/lib/types.ts`(`ProjectContext`만) · M `frontend/src/lib/logic/startForm.ts` · M `frontend/src/lib/logic/startForm.test.ts` |
| T5 | `ChoiceCards` 부품 | — | C `frontend/src/components/ds/ChoiceCards.tsx` · M `frontend/src/components/ds/index.ts`(export 1줄) · C `frontend/src/components/ds/choiceCards.test.ts` · M `frontend/src/app/globals.css`(`.ds-cards` 규칙만) |
| T6 | 0단계 화면 · 버전 비교 이름 | T4 · T5(T1 라벨) | M `frontend/src/app/pipeline/start/page.tsx` · M `frontend/src/app/pipeline/compare/page.tsx`(`fieldNames` 1줄) |

- **웨이브:** 1차 T1 · T4 · T5 → 2차 T3 → 3차 T6.
- 같은 웨이브 안에 소유 파일 겹침 없음. `contextLabels.ts`는 T1만, `types.ts`는 T4만 수정.

## 계약

### Python 모델 (T1 → T3)
```python
# backend/app/context/models.py
class TaskMode(str, Enum): metric = "metric"; explore = "explore"
class PersonaDimension(str, Enum): social = "social"; taste = "taste"; movement = "movement"; bio = "bio"
class KeyMetric(BaseModel): name: str; source: str = ""; item: str = ""
class Positioning(BaseModel):
    price: Price | None = None; market: Market | None = None   # "" → None (before 검증기)
    priceText: str = ""; marketText: str = ""                 # strip; 각 최대 40자
class PersonaSeed(BaseModel): text: str; dimension: PersonaDimension | None = None   # strip 후 1~40자
class PersonaSeeds(BaseModel): items: list[PersonaSeed] = []; exploreBeyond: bool = True   # items 최대 20
class ProjectContext(BaseModel):
    # 기존 필드 순서 유지, 아래만 바뀜
    taskMode: TaskMode | None = None
    analysisGoal: ChoiceWithNote[AnalysisGoal] | None = None   # before 검증기: choice가 ""이면 None (F1)
    keyMetrics: list[KeyMetric] = []        # before 검증기: str 항목 → {"name": str}
    positioning: Positioning = Positioning()
    personaSeeds: PersonaSeeds | None = None
```
필수 규칙(`model_validator(mode="after")`, 02-design 2.2):
- `taskMode is None` → `analysisGoal` 있음 · 이름 있는 지표 ≥ 1 · `price`와 `market`이 둘 다 기본 선택지(Enum)
- `metric` → 이름 있는 지표 ≥ 1
- `explore` → 추가 필수 없음
- 모든 경우: 같은 축에 `price`와 `priceText`(또는 `market`과 `marketText`)가 둘 다 있으면 오류

라벨(`labels.py`, `contextLabels.ts` 같은 순서 · 같은 글자):
```
"taskMode": {"metric": "지표 개선형", "explore": "탐색·기획형"}
"personaDimensions": {"social": "사회적 외부 페르소나", "taste": "개인 취향·활동", "movement": "신체 외부 동선", "bio": "내부 바이오"}
```

### 프롬프트 (T3)
`RoundInputs.task_mode: str | None = None`(마지막 필드). `TASK_FOCUS`는 02-design 4절 글자 그대로. `PROMPT_VERSION = {1: "r1.v2", 2: "r2.v1", 3: "r3.v1", 4: "r4.v1"}`.

### 화면 로직 (T4 → T6)
```ts
// frontend/src/lib/types.ts — ProjectContext 변경분
taskMode?: "metric" | "explore" | "";
analysisGoal?: { choice: string; note: string } | null;
keyMetrics: { name: string; source: string; item: string }[];
positioning: { price: string; market: string; priceText: string; marketText: string };
personaSeeds?: { items: { text: string; dimension: string | null }[]; exploreBeyond: boolean } | null;

// frontend/src/lib/logic/startForm.ts
export type ResearchTemplate = { id: string; title: string; text: string };
export const PERSONA_LIMIT = 20; export const SEED_MAX = 40;
export const emptyStartForm: ProjectContext;            // taskMode "explore", analysisGoal 키 없음, personaSeeds {items: [], exploreBeyond: true}, positioning 네 값 ""
export function mergeStartForm(loaded: unknown): ProjectContext;   // 기존 + 글자 지표 → {name, source:"", item:""}; analysisGoal은 choice가 있으면 보존, choice가 ""이면 null (F1)
export function isPreTaskModeContext(saved: unknown): boolean;     // 서버 원본이 객체이고 taskMode가 없거나 null이면 true (D-315 배너, F4 · F7)
export function validateStartForm(f: ProjectContext): { valid: boolean; errors: Partial<Record<"bk"|"oneLiner"|"researchQuestion"|"projectType"|"keyMetrics"|"channels", string>> };
export function researchTemplates(mode: "metric" | "explore", bk: string): ResearchTemplate[];   // 02-design 5.3 표 글자 · id 그대로
export function toggleChoice(current: string, value: string): string;          // 같으면 "", 다르면 value
export function choosePositionPreset(p: Positioning, axis: "price"|"market", value: string): Positioning;  // 프리셋 토글 + 그 축 Text 비움
export function setPositionText(p: Positioning, axis: "price"|"market", text: string): Positioning;       // trim, 40자 자름, 그 축 프리셋 비움
export function positioningOpen(f: ProjectContext): boolean;      // metric일 때 값이 하나라도 있으면 true; explore면 항상 true
export function addPersonaSeed(items: Seed[], text: string): { items: Seed[]; reason?: "empty" | "duplicate" | "limit" };
export function missingDimensions(items: Seed[]): ("social"|"taste"|"movement"|"bio")[];   // 순서 고정
```
오류 문구: `keyMetrics` → "지표를 하나 이상 추가하세요."(metric일 때만), 나머지는 page.tsx 기존 문구 그대로("제품명을 입력하세요." 등, `projectType` → "하나를 선택하세요.", `channels` → "채널을 하나 이상 선택하세요.").

### `ChoiceCards` (T5 → T6)
```ts
export type ChoiceCard = { value: string; title: string; description: string };
export type ChoiceCardsProps = { label: string; labelledBy?: string; describedBy?: string; options: ChoiceCard[]; value: string; onChange: (v: string) => void };
export function ChoiceCards(props: ChoiceCardsProps): JSX.Element;
export function cardKeyTarget(key: string, index: number, count: number): number | null;   // ArrowLeft/Up −1, ArrowRight/Down +1 (순환), Home 0, End count−1, 그 외 null
```

## Task별 단계

### T1 모델 · 라벨 · 렌더링 · API 검증
- [ ] **골든 먼저(F3)** 코드를 바꾸기 전에, 이 Task 시작 커밋의 코드로 `test_render.py::make_context()`를 렌더해 `backend/tests/context/fixtures/legacy_context.md`에 저장한다(known=`["두 번째 발견","첫 번째 발견"]`). 저장 명령과 sha256을 보고서에 남긴다.
- [ ] **RED** `test_models_task_mode.py` (기존 `test_models.py::context_data()`를 import해 씀)
  - `test_legacy_rules_unchanged` — `taskMode` 없음 + `keyMetrics: []` → 오류, + `analysisGoal` 삭제 → 오류, + `positioning: {}` → 오류, 원본 그대로 → 통과 · `ctx.keyMetrics == [KeyMetric(name="사용 편의성")]`.
  - `test_metric_requires_metric_only` — `taskMode="metric"`, `analysisGoal` 삭제, `positioning` 삭제, `keyMetrics=[{"name":"환자경험 점수","source":"보건복지부 환자경험평가","item":"수납 대기 시간이 적절했다"}]` → 통과. `keyMetrics=[{"name":"  "}]` → 오류.
  - `test_explore_requires_nothing_extra` — `taskMode="explore"`, 지표 · 포지셔닝 · 분석 목적 모두 없음 → 통과.
  - `test_positioning_blank_and_custom` — `{"price":"","market":""}` → 둘 다 None. `{"priceText":"  중상가 · 구독형 "}` → `"중상가 · 구독형"`. 41자 `priceText` → 오류.
  - `test_positioning_both_rejected` — `{"price":"premium","priceText":"중상가"}` → 오류(explore에서도).
  - `test_mixed_metric_items` — `["편의성", {"name":"만족도","source":"사내"}]` → 두 `KeyMetric`.
  - `test_persona_seed_limits` — `{"items":[{"text":" 초진 보호자 ","dimension":"social"},{"text":"간병인"}]}` → strip, 두 번째 dimension None, `exploreBeyond is True`. 공백만 · 41자 · 21개 · `dimension:"invalid"` → 각각 오류.
  - `test_unknown_task_mode_rejected` — `taskMode="other"` → 오류.
  - `test_empty_goal_is_none` (F1) — `analysisGoal={"choice":"","note":""}` + `taskMode="explore"` → 통과, `ctx.analysisGoal is None`. `taskMode` 없음 + 같은 값 → 오류(예전 규칙은 분석 목적 필수).
  - `test_null_task_mode_is_legacy` (F4) — `taskMode=None`을 명시해도 예전 규칙(지표 · 분석 목적 · 포지셔닝 필수).
  - 기존 `test_labels_parity.py` · `test_render.py::test_labels_cover_every_enum`이 새 Enum 두 개를 포함해 통과.
- [ ] **RED** `test_api_task_mode.py` (`client` 픽스처, `test_api.py`의 `CTX`)
  - `test_post_metric_without_positioning` · `test_post_explore_minimal` → 201, `load_session(sid)['projectContext']['taskMode']` 값 확인.
  - `test_post_metric_without_metric_is_422` → 422.
  - `test_patch_legacy_keeps_rules` — `CTX`로 만든 세션에 `PATCH /context/{sid}` `{"oneLiner":"바뀜"}` → 200. `{"keyMetrics":[]}` → 422(`validation`). 저장된 세션(이제 `taskMode: null`)에 다시 `PATCH` `{"oneLiner":"또"}` → 200, md가 골든과 같은 형식(과제 유형 줄 없음).
  - `test_warnings_after_r1` (R2) — 세션에 `keywordRounds['1']`을 넣은 뒤 PUT으로 `taskMode` · `keyMetrics` · `personaSeeds` · `researchQuestion`을 각각 바꾸면 `warnings`에 `taskMode_changed_after_r1` · `keyMetrics_changed_after_r1` · `personaSeeds_changed_after_r1` · `researchQuestion_changed_after_r1`. 같은 값으로 다시 저장 → 경고 없음. R1 없으면 경고 없음. 예전 세션의 글자 지표를 같은 이름의 구조 지표로 저장하는 것은 "바뀜"이 아니다(비교는 `ProjectContext`로 정규화한 값끼리).

#### T1 계속 — 렌더링 (F3로 옛 T2 내용을 여기로)
- [ ] **RED** `test_render_task_mode.py`
  - `test_legacy_bytes_identical` — `render_context_md(make_context(), ["두 번째 발견","첫 번째 발견"]).encode() == fixtures/legacy_context.md 바이트`.
  - `test_metric_render` — 아산 예시(`taskMode=metric`, `analysisGoal` 없음, 포지셔닝 없음, 지표 1개 출처 · 문항 있음, 페르소나 3개 태그 social · social · bio): 아래 줄이 모두 있고 순서가 맞다.
    `- 과제 유형: 지표 개선형 — 외부·사내 평가 지표를 올리는 과제. 지표가 떨어지는 순간을 우선 탐색`(제품명 바로 다음 줄) · `- 핵심 지표 (방향 지시자, 측정값 아님): 환자경험 점수 (출처: 보건복지부 환자경험평가 · 문항: 수납 대기 시간이 적절했다)` · `## 생각하는 페르소나 · 디멘션` · `- 초진 보호자 (사회적 외부 페르소나)` · `- 아직 적지 않은 디멘션: 개인 취향·활동, 신체 외부 동선` · `디멘션: 사회적 외부 페르소나 · 개인 취향·활동 · 신체 외부 동선 · 내부 바이오` · `예시는 출발점일 뿐이다. 네 디멘션 각각에서 예시와 비슷한 페르소나에 머물지 말고, 예시와 다른 페르소나와 맥락을 우선 발굴할 것`. 그리고 `"분석 목표"`, `"가격 포지셔닝"`, `"시장 포지셔닝"`, `"None"`이 없다. 페르소나 섹션은 `## 0-B` 앞.
  - `test_explore_custom_positioning` — `priceText="중상가 · 구독형"`, `market="new"` → `- 가격 포지셔닝: 중상가 · 구독형` · `- 시장 포지셔닝: 신규 진입자`, 과제 유형 줄 `탐색·기획형 — 아직 드러나지 않은 맥락과 기회를 찾는 과제. 넓게 탐색`.
  - `test_metric_partial_details` — 출처만 → `이름 (출처: X)`, 문항만 → `이름 (문항: Y)`, 둘 다 없음 → `이름`.
  - `test_persona_empty_and_off` — `items=[]` → 목록 자리 `- 없음`, "아직 적지 않은 디멘션" 줄 없음, 디멘션 줄 · 지시 줄 있음. `exploreBeyond=False` → 마지막 줄 `예시는 참고 시드이며 제약이 아니다. 범위 밖 발견도 배제하지 말 것`. 네 디멘션 모두 태그 → "아직 적지 않은" 줄 없음. 태그 없는 줄 → `- 응급실 재방문자`.
- [ ] 실패 확인: `backend/.venv/bin/python -m pytest backend/tests/context/test_models_task_mode.py backend/tests/context/test_api_task_mode.py backend/tests/context/test_render_task_mode.py -q` → `test_legacy_bytes_identical`만 PASS, 나머지 FAIL.
- [ ] **GREEN** 계약대로 `models.py` · `labels.py` · `contextLabels.ts` · `render.py` · `routers/context.py`(경고 대상 추가, R2). `render.py`의 기존 줄 문구("- 프로젝트 유형:", "- 분석 목표:" 등)는 바꾸지 않는다(D-312). `analysisGoal`이 있을 때만 "- 분석 목표:" 줄.
- [ ] 통과 확인: `backend/.venv/bin/python -m pytest backend/tests/context backend/tests/known backend/tests/test_integration_stage0_2.py -q` → PASS.

### T3 R1 프롬프트 분기
- [ ] **RED** `test_task_focus.py` (기존 `test_prompts.py::state` 픽스처 방식 재사용)
  - `test_r1_metric_focus` · `test_r1_explore_focus` — `replace(state, task_mode=…)` → R1 instructions에 `TASK_FOCUS[…]` 전체 글자 포함, 그 줄이 `발산 톤:` 줄 바로 다음.
  - `test_r1_no_mode_blank` — `task_mode=None` 또는 `"other"` → "과제 유형:" 글자 없음. `r1.v2` 지시에서 `{task_focus}` 줄을 지운 글자 == `r1.v1.md`를 같은 값으로 포맷한 글자(버전 줄 제외).
  - `test_other_rounds_untouched` — n=2,3,4 지시에 "과제 유형:" 없음.
  - `test_rounds_pass_task_mode` — `rounds._inputs`가 `projectContext.taskMode="metric"` 세션에서 `RoundInputs.task_mode == "metric"`, 없으면 `None`(기존 `test_rounds_api.py`의 세션 준비 방식 사용).
- [ ] **RED(기존 수정)** `test_prompts.py::test_four_distinct_templates`의 기대값을 `{1: "r1.v2", …}`로, `test_templates_loaded_at_call_time_and_strict`의 파일 이름을 `r1.v2.md`로.
- [ ] 실패 확인: `… -m pytest backend/tests/keywords/test_task_focus.py backend/tests/keywords/test_prompts.py -q` → FAIL.
- [ ] **GREEN** `r1.v2.md` = `r1.v1.md` 복사 + `발산 톤: {tone}` 다음 줄 `{task_focus}`. `prompts.py`에 `TASK_FOCUS` · `task_mode` · `"task_focus": TASK_FOCUS.get(state.task_mode or "", "") if n == 1 else ""`. `rounds._inputs`에 `task_mode=ctx.get('taskMode')`.
- [ ] 통과 확인: `… -m pytest backend/tests/keywords -q` → PASS(`test_no_role_sentence_no_domain_examples` 포함).

### T4 화면 타입 · 폼 로직
- [ ] **RED** `startForm.test.ts` (기존 3개 테스트는 새 빈 폼 기대값에 맞게 고침, 이유를 보고서에)
  - `emptyStartForm` — `taskMode === "explore"`, `"analysisGoal" in emptyStartForm === false`, `personaSeeds` = `{items: [], exploreBeyond: true}`, `positioning` = 네 값 `""`.
  - `mergeStartForm` — `{keyMetrics: ["편의성"], analysisGoal: {choice: "needs", note: "x"}}` → `keyMetrics == [{name:"편의성",source:"",item:""}]`, `analysisGoal` 그대로. `taskMode` 없음 → `"explore"`. `positioning: {price:"premium"}` → 나머지 `""`.
  - `isPreTaskModeContext` — `{bk:"a"}` → true, `{taskMode:null}` → true(F4), `{taskMode:"metric"}` → false, `null` → false.
  - `mergeStartForm({analysisGoal:{choice:"",note:""}})` → `analysisGoal === null`(F1), 이 결과로 `validateStartForm` valid.
  - `validateStartForm` — explore 최소 입력(bk · oneLiner · 질문 · projectType · channels) → valid. metric + 지표 0개 → `errors.keyMetrics === "지표를 하나 이상 추가하세요."`. metric + `{name:" "}`만 → 같은 오류. explore + 지표 0 · 포지셔닝 빈 값 → valid. `analysisGoal` 없어도 valid.
  - `researchTemplates` — `("explore","세라젬 모듈러 주택")` → id `["1","2","3","4"]`, 4번 text `"세라젬 모듈러 주택과 관련해 사람들이 아직 말하지 않은 생활 속 맥락과 필요는 무엇인가?"`. `("metric","서울아산병원")` → id `["m1","m2","m3"]`, m1 text `"서울아산병원을 이용하는 사람들은 어느 단계, 어느 순간에 막히거나 기다리는가?"`. bk `""` → "제품" 사용. 1~3번 text는 현재 page.tsx 문구와 같다.
  - `toggleChoice("premium","premium") === ""`, `toggleChoice("","value") === "value"`.
  - `choosePositionPreset({price:"",priceText:"중상가",…},"price","premium")` → `price "premium"`, `priceText ""`. `setPositionText({price:"premium",…},"price","  중상가 · 구독형 ")` → `price ""`, `priceText "중상가 · 구독형"`. 45자 → 40자.
  - `positioningOpen` — metric + 빈 값 → false, metric + `market:"new"` → true, explore → true.
  - `addPersonaSeed` — `" 초진 보호자 "` → 추가(trim, dimension null). `"초진  보호자"`(공백 차이) → `reason "duplicate"`. `"   "` → `"empty"`. 20개 상태 → `"limit"`. 45자 → 40자로 잘라 추가.
  - `missingDimensions([{text:"a",dimension:"social"},{text:"b",dimension:"bio"}])` → `["taste","movement"]`, `[]` → 네 개 모두.
- [ ] 실패 확인: `npm --prefix frontend test -- src/lib/logic/startForm.test.ts` → FAIL.
- [ ] **GREEN** 계약대로. 템플릿 1~3 문구는 page.tsx에서 옮겨 오고 page.tsx는 T6에서 이 함수를 쓴다.
- [ ] 통과 확인: `npm --prefix frontend test` → PASS.

### T5 `ChoiceCards` 부품
- [ ] **RED** `choiceCards.test.ts` — `cardKeyTarget("ArrowRight",1,2) === 0`, `("ArrowLeft",0,2) === 1`, `("ArrowDown",0,2) === 1`, `("Home",1,2) === 0`, `("End",0,2) === 1`, `("Enter",0,2) === null`.
- [ ] 실패 확인: `npm --prefix frontend test -- src/components/ds/choiceCards.test.ts` → FAIL.
- [ ] **GREEN** `ChoiceCards.tsx`: `<div role="radiogroup" class="ds-cards">` 안에 `<button type="button" role="radio" aria-checked>` 카드(제목 `ds-t-label` 굵게 · 설명 `ds-t-caption`), 고른 카드만 `tabIndex=0`(아무것도 안 골랐으면 첫 카드), 키 이동은 `cardKeyTarget` → `onChange` + 포커스 이동. `globals.css`에 `.ds-cards`(2열 grid, gap 12px, 768px 미만 1열) · `.ds-card-opt`(테두리 `--line`, 반경 `--r-card`, 패딩 14px 16px, 최소 높이 64px, `[aria-checked=true]` → 테두리 `--action` · 배경 `--action-soft`, `:focus-visible` 기존 포커스 규칙). `ds/index.ts`에 export.
- [ ] 통과 확인: `npm --prefix frontend test` · `npm --prefix frontend run lint` → PASS.

### T6 0단계 화면 · 버전 비교 이름
- [ ] **화면 작성** `start/page.tsx` (02-design 5.1 배치 · 5.2 동작 · 5.4 문구 · 5.6 접근성 그대로, 목업 s1~s3 참고)
  - 맨 위 과제 유형 카드(`ChoiceCards`, 요약 줄 D-316) → 0-A(제품명 · 한줄 정의 → 프로젝트 성격(전체 폭) → 리서치 질문(`researchTemplates(form.taskMode, form.bk)`) → 핵심 지표(지표명 · 출처 · 관련 설문 문항 3칸 + "지표 추가하기", 지표명 빈 값이면 버튼 비활성) → 사내 제약 · 포지셔닝 → 수집 채널 · 이미 아는 것) → 생각하는 페르소나 카드 → 0-B(변경 없음).
  - 분석 목적 칩 · 보충 설명 칸 삭제. `single()` 헬퍼는 `projectType`만.
  - 포지셔닝: 축마다 `ChoiceChips` 단일 + `toggleChoice`/`choosePositionPreset`, "+ 직접 입력"(quiet) → `Input` + "추가하기" → `setPositionText`, 직접 입력 칩은 글자 + ✕(`aria-label="가격대 직접 입력 지우기"`/`"시장 위치 직접 입력 지우기"`). metric이면 `<details open={positioningOpen(form)}>`.
  - 페르소나: 입력 칸 + "추가하기"(`addPersonaSeed`, reason별 안내: limit → "20개까지 적을 수 있습니다.", duplicate · empty → 안내 없이 무시), 줄마다 이름 · 태그 칩 4개(`ChoiceChips` 단일, 라벨 `"{text} 디멘션"`, 짧은 이름 "사회적 외부" · "취향·활동" · "동선" · "바이오", `toggleChoice`로 해제) · "삭제하기"(quiet), 1개 이상이면 "아직 안 적은 관점: …"/"네 관점이 모두 있습니다.", `Checkbox` "예시와 다른 페르소나를 우선 발굴".
  - 기존 세션 배너: `getVersionContext` 응답의 원본 `projectContext`로 `isPreTaskModeContext` → `Banner tone="info"`(5.4 문구), 저장 성공 후 `setReturned` 갱신으로 사라짐.
  - 검증: `valid`를 `validateStartForm(form).valid`로 바꾸고, 각 칸의 오류 문구 · `aria-invalid`는 `errors`에서. 핵심 지표 그룹은 metric일 때만 오류.
  - 미리보기 `preview()`를 3장 md 형식(과제 유형 줄 · 지표 출처/문항 · 포지셔닝 값 있을 때만 · 생각하는 페르소나 섹션 · 분석 목적은 값 있을 때만)으로.
  - R1 뒤 변경 안내(R2): `putContext` 응답의 `warnings`가 하나라도 있으면 `Banner tone="info"` "R1 키워드는 바뀌기 전 입력으로 만들었습니다. 새 입력을 반영하려면 새 버전을 만들어 0단계부터 다시 시작하세요." 다음 저장(경고 없음) 또는 세션 전환 때 사라짐.
  - `compare/page.tsx` `fieldNames`에 `taskMode:'과제 유형'`, `personaSeeds:'생각하는 페르소나'`.
- [ ] 확인: `npm --prefix frontend run lint` · `npm --prefix frontend run build` · `npm --prefix frontend test` → PASS. 화면 동작은 브라우저 QA(QA-S1~S9)로 확인.

## 검증 명령
```
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend test
```

## 브라우저 QA 계획
- 사용자가 띄운 서버(3310 · 8310 · 3311 · 8311)는 끄지 않는다. QA는 **8312 · 3312**를 쓴다.
- 데이터: 빈 QA 폴더 `/private/tmp/dcx-stage0-qa`. 기존 세션은 시작 후 `curl -X POST localhost:8312/context`에 예전 형태 JSON(`test_api.py`의 `CTX`와 같은 모양: `analysisGoal` 있음, 글자 지표, `taskMode` 없음)으로 하나 만든다. 이렇게 만든 세션은 저장 시 `taskMode: null`이 되므로(F4) 키 없음 상태도 보려면 세션 폴더 `session.json`에서 `taskMode` 키를 지운 사본을 하나 더 둔다.
- 시작: 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=/private/tmp/dcx-stage0-qa LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3312 .venv/bin/uvicorn app.main:app --port 8312`, 프론트 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8312 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3312`
- 테스트 URL: `http://localhost:3312/pipeline/start` (뷰포트 1360×900, 375×812)

| ID | 시나리오 | 기대 | AC |
|---|---|---|---|
| QA-S1 | 새 프로젝트 열기 | 과제 유형 카드 2개 중 탐색·기획형 선택, 요약 "핵심 지표 선택", 분석 목적 칩 없음, 프로젝트 성격이 리서치 질문 위 | AC-01 · D-317 · D-318 |
| QA-S2 | 아산: 지표 개선형 → 템플릿 m1 → 지표 1개(출처 · 문항) → 페르소나 3개(태그 2종) → 저장 | 템플릿 3개 문구 · 요약 "핵심 지표 필수" · 포지셔닝 접힘 · "아직 안 적은 관점" 줄 · 저장 성공 · 세션 폴더 project_context.md가 02-design 3절 형식(분석 목표 · 포지셔닝 줄 없음) | AC-02 · 04 · 05 · 07 |
| QA-S3 | 아산: 지표를 지우고 저장 | "지표를 하나 이상 추가하세요." · 그 칸으로 스크롤 · 포커스 | AC-02 |
| QA-S4 | 세라젬: 탐색·기획형 → 템플릿 4 → 가격대 직접 입력 "중상가 · 구독형" · 시장 위치 "신규 진입자" → 다시 눌러 해제 → 다시 선택 → 저장 | 직접 입력 칩 ✕ · 해제 동작 · 지표 없이 저장 · md `- 가격 포지셔닝: 중상가 · 구독형` | D-319 · AC-03(변경) |
| QA-S5 | 세라젬에서 지표 개선형으로 바꿨다가 되돌리기 | 입력값 유지, 템플릿 버튼만 바뀜, 포지셔닝 값이 있으면 접힌 영역이 펼쳐진 채 | 5.2 |
| QA-S6 | 페르소나 21번째 추가 · 같은 이름 · 공백 | 21번째에서 "20개까지 적을 수 있습니다.", 중복 · 공백은 추가 안 됨 | 5.2 |
| QA-S7 | 예전 세션 열기 → 아무것도 안 바꾸고 상태 확인 → 저장 | 정보 배너 문구(5.4) · 탐색·기획형 선택 · 지표 2개 이름만 보임 · 저장 후 배너 사라짐 · md에 과제 유형 줄 추가 · "분석 목표" 줄 유지 | D-315 · AC-09 |
| QA-S8 | 아산 세션에서 "키워드 생성 시작하기" | 키워드 화면으로 이동, R1 실행 오류 없음(가짜 LLM) | AC-08 |
| QA-S9 | 버전 비교(stage0)에서 과제 유형 바꾼 두 버전 | "과제 유형" · "생각하는 페르소나" 이름으로 표시 | AC-10 |
| QA-S10 | 아산 세션 R1 생성 후 0단계로 돌아가 과제 유형을 바꿔 저장 | R1 뒤 변경 안내 배너(R2 문구), 저장은 됨, 같은 값으로 다시 저장하면 배너 없음 | R2 |
| QA-R | 375×812에서 S2 화면 | 카드 1열 · 지표 3칸 세로 · 페르소나 태그 칩 둘째 줄 · 가로 스크롤 없음 · 키보드로 과제 유형 화살표 이동 · 탭 순서 위→아래 | 5.6 |
| QA-L1 | (키가 있을 때만) 백엔드를 `LLM_BACKEND` 미지정(사용자 `.env`)으로 8312에 다시 띄워 아산 · 세라젬 세션 R1 각 1회 | 두 결과의 키워드 상위 20개를 QA 보고서에 나란히 기록(제품 · 질문이 달라 과제 유형 효과만 분리한 비교는 아님을 함께 적음, R3). 아산은 대기 · 수납 · 이동 같은 "막히는 순간" 단어 비중, 세라젬은 생활 상황 · 대체 행동 단어 비중을 눈으로 비교. 키가 없으면 "미실행(키 없음)" | 이번 주 목표 "두 버전 동작" |

## 수용 기준 연결
| AC | Task · 근거 |
|---|---|
| 01 | T5 · T6 · QA-S1 |
| 02 | T1 `test_metric_requires_metric_only` · T1 `test_metric_render` · T4 `validateStartForm` · QA-S2 · S3 |
| 03(D-319로 변경) | T1 `test_explore_requires_nothing_extra` · `test_positioning_*` · T1 `test_explore_custom_positioning` · T4 포지셔닝 함수 · QA-S4 |
| 04 | T1 `test_mixed_metric_items` · T1 `test_metric_partial_details` · QA-S2 |
| 05 | T4 `researchTemplates` · QA-S2 · S4 |
| 06(D-317로 폐기) | 분석 목적 칩 없음: T4 · T6 · QA-S1 |
| 07(D-320으로 변경) | T1 `test_persona_seed_limits` · T1 `test_persona_empty_and_off` · T4 페르소나 함수 · QA-S2 · S6 |
| 08 | T3 전체 · QA-S8 · QA-L1 |
| 09 | T1 `test_legacy_rules_unchanged` · `test_patch_legacy_keeps_rules` · T1 `test_legacy_bytes_identical` · T4 `mergeStartForm` · QA-S7 |
| 10 | T1 라벨 parity · T6 compare · QA-S9 |

## 되돌리기
- **머지 전 백업(F5):** 머지 직전에 데이터 폴더를 통째로 복사한다(예: `cp -a data data.bak-stage0-task-mode-$(date +%Y%m%d)`). 사용자가 다른 `LOCAL_DATA_DIR`(예: `data/asan-demo`)을 쓰면 그 폴더도 같은 방식으로.
- **되돌리기:** main 머지 커밋을 `git revert -m 1 <merge>`로 되돌리고, 머지 뒤 0단계를 저장한 세션이 있으면 백업 폴더의 같은 세션 폴더로 교체한다. 새 형식(구조 지표 · `priceText` · `personaSeeds` · `taskMode: null`)은 이전 모델(`keyMetrics: list[str]`, 포지셔닝 필수)이 읽지 못해 422가 나므로 "새 버전 만들기"로는 복구되지 않는다(데이터를 그대로 복사함, `versions.py:174`). 머지 뒤 0단계를 저장하지 않은 예전 세션은 영향이 없다.

## Decision ledger (plan-eng-review, 2026-10-02)

### Scope record
feature answers: 변경 없음(기능 축소 제안 없음); structure: A Original arrangement (D1 답변 "Original arrangement"); accepted scope: 계획의 T1~T6 파일 구성 그대로(`ChoiceCards`는 `components/ds` 공용 부품); pending remedies: R2 · R3

### 리뷰 발견 (Codex 바깥 의견 + Claude 확인)
| # | 심각도 | 확신 | 위치 | 내용 | 처리 |
|---|---|---|---|---|---|
| F1 | P1 | 9 | `frontend/src/lib/logic/startForm.ts:5` `analysisGoal: {choice: "", note: ""}` · `backend/app/context/models.py:81` `analysisGoal: ChoiceWithNote[AnalysisGoal]` | 예전 빈 임시 저장본의 `analysisGoal.choice == ""`가 보존되면 칸이 없어진 화면에서 고칠 수 없는데 서버는 Enum 오류로 422 → 저장 불가 | 승인된 D-317("저장된 값 보존")의 구현 보정: 선택값이 빈 `analysisGoal`은 화면(`mergeStartForm`) · 서버(before 검증기) 모두 `None`으로. 질문 없음 |
| F2 | P1 | 8 | `backend/app/routers/context.py:91-95` (`oneLiner` · `researchQuestion`만 경고) · 화면은 `warnings`를 표시하지 않음 | R1 생성 뒤 과제 유형 · 지표 · 페르소나를 바꾸면 R1 결과는 예전 입력 기준인데 아무 표시가 없음 | **R2 — 질문** |
| F3 | P1 | 9 | `backend/app/context/store.py:140-146` 저장마다 렌더 · `render.py:37-41` (`_items(ctx.keyMetrics)`, `ctx.analysisGoal.choice`) | T1만 끝나면 렌더가 깨져 저장 API가 실패하고, T2 시작 커밋에서는 골든을 만들 수 없음 | 순서 보정: 골든 생성을 T1 첫 단계로, 렌더 변경을 T1에 합침(T2 삭제). 파일 구성은 그대로. 질문 없음 |
| F4 | P2 | 9 | `backend/app/routers/context.py:58` `ctx.model_dump(mode='json')` | 업그레이드 뒤 저장된 예전 세션은 `taskMode: null`로 저장됨. "키 없음"만 예전으로 보면 배너 · 규칙이 어긋남 | D-315 · D-302 구현 보정: 키 없음과 `null` 모두 예전 세션. 질문 없음 |
| F5 | P2 | 8 | `03-plan.md` 되돌리기 · `backend/app/context/versions.py:174` 새 버전은 데이터 복사 | "새 버전으로 다시 만들기"로는 되돌린 코드에서 열 수 없음 | 되돌리기 절차를 "머지 전 `data/` 백업 → 되돌릴 때 복원"으로 교체. 질문 없음 |
| F6 | P2 | 8 | `03-plan.md` QA-L1 · `backend/app/llm/fake.py:17` 가짜 응답은 작업 이름으로만 고름 | 아산 · 세라젬을 비교하면 제품 · 질문 · 지표가 모두 달라 과제 유형 효과를 볼 수 없음 | **R3 — 질문** |
| F7 | P3 | 8 | `frontend/src/app/pipeline/start/page.tsx:59` `const legacy = !!store.sid && store.sd?.schemaVersion !== 2;` | 이미 "legacy"(구버전 세션)라는 이름이 있어 새 판정 함수 이름이 헷갈림 | 이름 정정: `isPreTaskModeContext` → `isPreTaskModeContext`. 질문 없음 |
| F8 | P3 | 9 | `backend/app/context/versions.py:245-246` 키별 값 비교 | 다시 저장한 예전 세션은 버전 비교에서 `keyMetrics`에 더해 `positioning`(`priceText`·`marketText` 추가)도 "바뀜"으로 보임 | D-311(설계 승인)의 범위 안. 기록만 |

### R2: R1 생성 뒤 과제 유형 · 지표 · 페르소나 · 질문을 바꿨을 때
Finding: F2 (P1, 8/10, `backend/app/routers/context.py:91-95`, Codex)
Plan baseline: 원래 계획에 없음. 지금 동작은 `oneLiner` · `researchQuestion` 변경 시 서버 `warnings`만 돌려주고 화면은 표시하지 않음
Runtime evidence: `_save_context`가 `warnings.append(field + '_changed_after_r1')`; `frontend/src`에 `changed_after_r1` 사용처 없음(grep 0건)
Comparison grid:
| 항목 | 지금 | A 안내 | B 막기 | C 그대로 |
|---|---|---|---|---|
| 경고 대상 | oneLiner · researchQuestion | + taskMode · keyMetrics · personaSeeds | 같음 | 지금 그대로 |
| 화면 표시 | 없음 | 저장 후 정보 배너 | 과제 유형 카드 잠금 + 안내 | 없음 |
| 저장 허용 | 허용 | 허용 | 과제 유형만 거부(409) | 허용 |
Question D2: R1 생성 뒤 0단계를 고쳤을 때 (A 저장 후 안내 배너 · B 과제 유형 잠금 · C 그대로)
Header: R1 뒤 변경
State: approved
Actual answer: A 저장 후 안내 배너 (D2 답변, 2026-10-02)
Accepted scope: 서버 `_save_context` 경고 대상에 `taskMode` · `keyMetrics` · `personaSeeds` 추가(기존 `oneLiner` · `researchQuestion` 유지, 경고 이름 `<field>_changed_after_r1`). 화면은 저장 응답의 `warnings`가 하나라도 있으면 정보 배너 "R1 키워드는 바뀌기 전 입력으로 만들었습니다. 새 입력을 반영하려면 새 버전을 만들어 0단계부터 다시 시작하세요." 저장은 막지 않음. 테스트: T1 API 테스트 + T6 화면 · QA-S10

### R3: QA-L1 실제 LLM 확인 방식
Finding: F6 (P2, 8/10, QA-L1, Codex)
Plan baseline: 아산 · 세라젬 R1 각 1회, 상위 20개 눈으로 비교(키 있을 때만)
Runtime evidence: 가짜 LLM은 입력과 무관(`fake.py:17`)
Comparison grid:
| 항목 | 지금 | A 같은 입력 · 두 유형 · 두 제품 | B 아산만 두 유형 | C 원래대로 |
|---|---|---|---|---|
| 실행 | 아산 1 · 세라젬 1 | 4회 | 2회 | 2회 |
| 판정 기준 | 눈으로 비교 | 상위 30개 겹침 비율(80%↑ = 효과 약함) + 한쪽에만 나온 단어 | A와 같음 | 눈으로 비교 |
Question D3: QA-L1 실제 LLM 확인 방식 (A 4회 · B 아산 2회 · C 원래대로)
Header: LLM 확인
State: approved
Actual answer: C 원래 계획대로 (D3 답변, 2026-10-02)
Accepted scope: QA-L1 변경 없음. 보고서에 "제품 · 질문이 달라 과제 유형 효과만 분리한 비교는 아님"을 한 줄로 적는다(사실 기록, 범위 변화 없음).

Approval readiness: PASS — Scope record(D1 "Original arrangement") · R2(D2 "A 저장 후 안내 배너") · R3(D3 "C 원래 계획대로"). F1 · F3 · F4 · F5 · F7은 승인된 설계(D-317 · D-315 · D-302)와 계획 실행 가능성을 위한 보정으로 별도 질문 없음, F8은 D-311 범위 기록.

## 엔지니어링 리뷰 결과 (plan-eng-review, 2026-10-02)

### 데이터 흐름
```
[start/page.tsx] ──form──► validateStartForm ─(valid)─► POST/PUT /context ─► ProjectContext.model_validate
      ▲  mergeStartForm(서버 원본 · 임시 저장본)                 │  (before: 글자 지표→구조, ""→None, 빈 goal→None)
      │  isPreTaskModeContext → 정보 배너                       │  (after: taskMode별 필수 규칙)
      │                                                         ▼
      └──── warnings(R1 뒤 변경) ◄── _save_context ─► store._update_locked ─► render_context_md ─► project_context.md
                                                                                             │
                                                         rounds._inputs(task_mode) ─► build_round_task(r1.v2 + TASK_FOCUS)
```

### 섹션별 발견
- **1 아키텍처:** F3(순서 · 렌더 결합), F5(되돌리기). 둘 다 보정 반영. 경계는 0단계 모듈 + R1 입력으로 한정, `versions.py` 미변경 유지.
- **2 코드 품질:** F1(빈 분석 목적 저장 불가), F4(`taskMode: null`), F7(이름 충돌). 보정 반영. 공용 코드 추출 제안 없음(`ChoiceCards`는 D-321로 승인된 새 부품, 키 이동 규칙만 `ChoiceChips`와 같게).
- **3 테스트:** 아래 커버리지 그림. R2 테스트 추가. QA-L1은 R3대로.
- **4 성능:** 문제 없음. 렌더는 저장마다 1회, 페르소나 최대 20개 · 지표 수 제한 없음(현실적으로 수 개).

### 테스트 커버리지 그림
```
CODE PATHS                                              USER FLOWS
[+] models.ProjectContext                               [+] 0단계 새 프로젝트 (QA-S1 · S2 · S4)
  ├── [★★★] 예전 규칙 · null 규칙 — T1                     ├── [★★★] 지표 개선형 저장 · 오류 · 스크롤 — QA-S2 · S3
  ├── [★★★] metric · explore 규칙 — T1                    ├── [★★★] 포지셔닝 직접 입력 · 해제 — QA-S4
  ├── [★★★] 포지셔닝 ""→None · 직접 입력 · 둘 다 거부 — T1  └── [★★ ] 페르소나 한도 · 중복 — QA-S6
  ├── [★★★] 지표 글자/구조 혼합 · 빈 이름 — T1            [+] 예전 세션 (QA-S7)
  ├── [★★★] 페르소나 strip · 40자 · 20개 · 잘못된 태그 — T1   ├── [★★★] 배너 · 미리 선택 · 저장 후 사라짐
  └── [★★★] 빈 분석 목적 → None — T1 (F1)                    └── [★★★] 키 없음 · null 두 상태 (F4)
[+] render_context_md                                   [+] R1 뒤 변경 (QA-S10, R2)
  ├── [★★★] 예전 세션 바이트 동일(골든) — T1                 └── [★★★] 경고 · 배너 · 같은 값 재저장 시 없음
  ├── [★★★] 과제 유형 · 지표 표기 · 포지셔닝 생략/직접 입력 — T1
  └── [★★★] 페르소나 빈 목록 · 태그 없음 · 체크 OFF — T1
[+] _save_context 경고 (R2)                             [+] 반응형 · 키보드 (QA-R)
  └── [★★★] 네 필드 · 같은 값 · R1 없음 · 정규화 비교 — T1
[+] build_round_task / rounds._inputs
  ├── [★★★] metric · explore · None · 모르는 값 — T3
  ├── [★★★] v1과 같은 본문(포커스 줄 제외) — T3 (회귀)
  └── [★★ ] R2~R4 영향 없음 — T3
[+] startForm.ts 순수 함수 — [★★★] T4 전 함수
[+] ChoiceCards 키 이동 — [★★★] T5 (렌더링은 [→E2E] QA-S1 · QA-R)

LLM: [→EVAL] R1 지시 변경 — QA-L1(키 있을 때, R3: 원래 방식)
COVERAGE: 계획된 코드 경로 전부 테스트 지정 · 화면 동작은 브라우저 QA
```
회귀 계약(REGRESSION RULE): 예전 세션 md 바이트 동일 · 예전 필수 규칙 · R1 v1 본문 유지 · 기존 0단계 흐름(세션 열기 · 임시 저장 · 구버전 세션 배너)은 기존 테스트 + QA-S7로 보호. 승인된 기획 AC-09 · D-302가 이 계약이다.

### 실패 모드
| 경로 | 현실적 실패 | 테스트 · 처리 | 사용자에게 보임 |
|---|---|---|---|
| 예전 임시 저장본 불러오기 | 빈 분석 목적으로 저장 불가 | T1 · T4 (F1) | 고쳐짐 |
| 예전 세션 다시 저장 | `taskMode: null`을 새 세션으로 오판 | T1 · T4 (F4) | 배너 정상 |
| R1 뒤 과제 유형 변경 | 키워드가 예전 지시 기준 | T1 경고 · T6 배너 (R2) | 배너 |
| 화면 우회 저장 | 같은 축 프리셋 + 직접 입력 | T1 422 | 기존 오류 배너 |
| 되돌리기 | 새 형식 세션을 이전 코드가 못 읽음 | 백업 · 복원 절차 (F5) | 절차 따름 |
비판적 공백(테스트 · 처리 · 표시 모두 없음): 0개.

### NOT in scope
- 기대 산출물(P1), 화면 밀도(P2): 기획에서 backlog.
- 버전 비교의 글자 → 구조 차이 정리(F8 · D-311): `versions.py`를 6~8단계 브랜치가 고치는 중.
- QA-L1의 같은 입력 두 유형 비교: 사용자 선택 R3 = C.

### What already exists (재사용)
`ProjectContext` 검증 · `_save_context` 경고 · `store._update_locked` 렌더 · `RoundInputs`/`build_round_task` 템플릿 포맷 · `mergeDefaults` · `ChoiceChips` 키 규칙 · `Banner` · `Checkbox` · `popoverKeyAction` · `josa()` · 기존 `test_labels_parity` · `test_labels_cover_every_enum`.

### 병렬화
| 단계 | 모듈 | 의존 |
|---|---|---|
| T1 | backend/app/context · backend/app/routers · frontend/src/lib(contextLabels) | — |
| T4 | frontend/src/lib(types · logic) | — |
| T5 | frontend/src/components/ds · globals.css | — |
| T3 | backend/app/keywords | T1 |
| T6 | frontend/src/app/pipeline | T1 · T4 · T5 |
Lane A: T1 → T3 / Lane B: T4 / Lane C: T5 → 셋이 끝나면 T6. 충돌: `frontend/src/lib`는 T1(contextLabels.ts) · T4(types.ts · startForm.ts)가 서로 다른 파일만 수정.

## Implementation Tasks
리뷰 발견에서 나온 작업(계획 T1~T6 안에 반영됨).
- [ ] **E1 (P1, human: ~1h / CC: ~10min)** — context — 골든을 먼저 만들고 렌더 변경을 T1에 합친다 (F3) · 확인: `pytest backend/tests/context -q`
- [ ] **E2 (P1, human: ~1h / CC: ~10min)** — context · startForm — 빈 분석 목적을 None/null로 (F1) · 확인: T1 `test_empty_goal_is_none`, T4 mergeStartForm
- [ ] **E3 (P1, human: ~2h / CC: ~15min)** — context router · start page — R1 뒤 변경 경고 확대 + 배너 (R2) · 확인: T1 `test_warnings_after_r1`, QA-S10
- [ ] **E4 (P2, human: ~30min / CC: ~5min)** — startForm — `isPreTaskModeContext`가 null도 예전으로 (F4 · F7) · 확인: T4
- [ ] **E5 (P2, human: ~15min / CC: ~2min)** — 되돌리기 — 머지 전 데이터 백업 절차 (F5) · 확인: 머지 체크리스트

### Completion summary
- Step 0: Scope Challenge — scope accepted as-is (D1 Original arrangement)
- Architecture Review: 2 issues found (F3 · F5)
- Code Quality Review: 3 issues found (F1 · F4 · F7)
- Test Review: diagram produced, 2 gaps identified (F2 · F6)
- Performance Review: 0 issues found
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 0 items proposed (기존 backlog 처리 그대로)
- Failure modes: 0 critical gaps flagged
- Unresolved decisions: 0 in this review
- Outside voice: codex, completed (6 findings, 모두 반영 또는 사용자 결정)
- Parallelization: 3 lanes, 3 parallel / 2 sequential
- Lake Score: 0/1 (R3에서 사용자가 C 선택)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | codex via `/plan-eng-review` | Independent 2nd opinion | 1 | completed | 6 findings (P1 3 · P2 3), 4 반영 · 2 사용자 결정 |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 8 issues, 0 critical gaps (모두 처리, 미결 0) |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 6/10 → 8/10, 6 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex · plan-review 단계 · completed · 6 findings(F1 · F2 · F3 · F4 · F5 · F6). design 단계 외부 의견은 skipped.
- **CROSS-MODEL:** Claude가 따로 찾은 F7 · F8(이름 충돌 · 버전 비교 소음)과 Codex의 F4(null 저장)가 같은 원인(`model_dump`가 기본값을 저장)에서 겹침. 나머지는 Codex 단독 발견을 Claude가 코드로 확인.
- **VERDICT:** DESIGN CLEARED. ENG 발견 8건 모두 처리(보정 반영 6 · 사용자 결정 2), 구현 진행 가능. 대시보드 상태는 발견이 있었으므로 issues_open.

NO UNRESOLVED DECISIONS
