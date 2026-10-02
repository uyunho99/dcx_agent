# SDD ledger — plan: docs/development/dcx2-stage0-task-mode/03-plan.md

Baseline: 4ec7719 · backend 1458 passed · frontend 318 passed · lint · build OK
Executor: codex (codex:codex-rescue --wait --fresh, write)

## Preflight scan
| 대상 | 생산 → 소비 | 결과 |
|---|---|---|
| T1 ↔ T3 | T1 `ProjectContext.taskMode` 저장 → T3 `rounds._inputs`가 `ctx.get('taskMode')`(dict) 소비 | 일치 |
| T1 ↔ T4 | T1 `contextLabels.ts`(taskMode · personaDimensions) ↔ T4 `types.ts` · `startForm.ts` | 파일 겹침 없음, 값 이름 일치 |
| T1 ↔ T6 | T1 `_save_context` warnings(`<field>_changed_after_r1`) → T6 배너(warnings 길이만 봄) | 일치 |
| T4 ↔ T6 | `validateStartForm` · `researchTemplates` · `isPreTaskModeContext` · 포지셔닝/페르소나 함수 → page.tsx | 이름 일치(F7 정정 반영) |
| T5 ↔ T6 | `ChoiceCards` props(label · labelledBy · describedBy · options · value · onChange) → page.tsx | 일치 |
| T1 자체 | 골든 먼저 → RED → GREEN, 파일 표에 render.py · routers/context.py 포함 | 일치 |
| T3 자체 | 기존 test_prompts 기대값 변경 허용(전역 제약) | 일치 |
| T4 자체 | 빈 폼 기대값 변경 허용(전역 제약), analysisGoal 키 없음 vs F1 null | 일치 |
| T5 자체 | node 환경 vitest → 키 함수만 단위 테스트, 렌더는 QA | 일치 |
| T6 자체 | 화면 테스트 없음(vitest .test.ts만) → lint · build · QA로 확인 | 일치 |
Ruling: 실행 순서는 T1 → T4 → T5 → T3 → T6 (SDD는 구현 병렬 금지) — 계획의 웨이브 의존 관계를 지킴 — 틀려도 시간만 더 듦.
Ruling: Codex 샌드박스가 worktree git 메타데이터(dcx_agent/.git/worktrees/...)에 쓸 수 없어 커밋은 Main Claude가 Codex 변경을 그대로 stage·commit한다. 이후 Task는 Codex에게 커밋하지 말라고 지시 — 커밋은 구현이 아니고 diff는 Codex 산출물 그대로 — 틀리면 커밋 작성자 표기만 다름.

Task T1: implemented by codex (agent a64cc430d418d09bf), BASE 4ec7719, commit c240a7c by controller; review package review-4ec7719..c240a7c.diff
Task T1: minor (deferred): test_api_task_mode 잘못된 이전 맥락 fallback이 keyMetrics 경고를 기대값으로 고정
Task T1: minor (deferred): KeyMetric.source/item 공백 strip · 길이 제한 없음 → "(출처:  )" 가능
Task T1: minor (deferred): 빈 글자 지표가 있던 저장 세션은 이제 거부됨(가능성 낮음)
Task T1: minor (deferred): PersonaSeed.text 줄바꿈 허용 → md 제목 주입 가능(기존 자유 입력과 같은 성질)
Task T1: minor (deferred): test_metric_render 섹션 인접성 단언 없음
Task T1: ⚠️ golden 선생성 — 보고서 1절 명령 · sha256 fca9a707… 확인, 커밋 전 코드로 생성(controller 확인)
Task T1: complete (commits 4ec7719..c240a7c, review clean)
Task T4: implemented by codex (agent a1daea47e32e1676c), BASE c240a7c, commit 6fc04e7 by controller. build는 page.tsx 타입 오류로 실패 예상(T6에서 해결)
Ruling: 사용자 요청("동시에 개발")으로 파일이 겹치지 않는 T5(frontend/src/components/ds · globals.css)와 T3(backend/app/keywords)를 Codex에 병렬 위임, T4 리뷰도 동시에 — SDD의 "구현 병렬 금지"보다 사용자 지시가 우선, 소유 파일 서로소 — 틀리면 커밋 분리만 수작업. Claude 직접 구현은 하네스 훅이 차단하므로 하지 않음.
Task T4: minor (deferred): 저장된 personaSeeds.items 형태 정규화 없음(비문자 text면 중복 검사에서 예외 가능)
Task T4: minor (deferred): setPositionText("")도 그 축 프리셋을 비움
Task T4: minor (deferred): 20개 상태에서 중복이면 limit 대신 duplicate(순서 미고정)
Task T4: minor (deferred): startForm.test.ts 빈 줄 2개
Task T4: complete (commits c240a7c..6fc04e7, review clean)
Task T5: implemented by codex (agent af27de425b97a1272), BASE 6fc04e7, commit ca4d699 by controller (T3 미커밋 변경과 분리해 T5 파일만 stage)
Task T3: implemented by codex (agent a8c62e8119b56a64c), BASE ca4d699, commit 0d509ac by controller
Task T5: review → Important 1: 계약 이탈(옵션 필드 label↔title, props aria-labelledby/aria-describedby↔labelledBy/describedBy, label 선택↔필수). Minor: @media(width<768px) 범위 문법, className 끝 공백
Ruling: T5 인터페이스 정렬은 진행 중인 T6 결과를 본 뒤 한 방향으로 맞춘다(T6이 쓴 이름 기준으로 T5 수정 또는 계획 기준으로 둘 다) — T6과 동시 수정 충돌 방지 — 틀리면 수정 1회 추가
Task T3: minor (deferred): test_task_focus가 test_prompts의 state 픽스처를 직접 import(conftest로 옮기면 깔끔)
Task T3: minor (deferred): test_task_focus가 채널 규칙 · "없음." 문구를 하드코딩
Task T3: minor (deferred): pytest 경고 PydanticDeprecatedSince20(app/config.py:12, 기존)
Task T3: complete (commits ca4d699..0d509ac, review clean)
Task T6: implemented by codex (agent a05dfd0d50f504329), BASE 0d509ac, commit a87b1f2 by controller. Codex 샌드박스에서 Turbopack 빌드 멈춤, webpack 빌드 통과
Ruling: T5 Important(인터페이스 이탈)는 코드가 아니라 계획 계약을 실제 구현에 맞춰 고친다 — ChoiceCards props는 aria-labelledby/aria-describedby/aria-label 직접 전달, 옵션은 {value, label, description}. T6이 이미 이 이름으로 작성됐고 React 관례와 같음 — 틀리면 이름 변경 1회
Task T5: complete (commits 6fc04e7..ca4d699, Important 1건은 계약 수정 ruling으로 해소, minor 2 deferred)
Task T5: minor (deferred): @media(width < 768px) 범위 문법(다른 곳은 max-width)
Task T5: minor (deferred): className 미지정 시 끝 공백
Controller: 기본 Turbopack 빌드는 샌드박스 밖에서 통과(a87b1f2) — 멈춤은 Codex 샌드박스 한정
Task T6: review → Important 1: 지표 개선형 포지셔닝 <details open>이 매 렌더 positioningOpen을 따라가 값을 지우면 저절로 닫힘(5.2는 시작 상태만 규정)
Task T6: minor (deferred): ChoiceChips Home/End가 이미 고른 칩이면 toggle로 해제됨
Task T6: minor (deferred): "+ 직접 입력" 상자를 빈 채로 닫을 수 없음
Task T6: minor (deferred): 서버 임시 저장본이 metric인데 예전 세션 배너는 "탐색·기획형으로 표시" 문구
Task T6: minor (deferred): 페르소나 줄 key가 seed.text(서버 중복 데이터 시 충돌)
Task T6: minor (deferred): 과제 유형 전환 시 입력 중인 직접 입력 글자 사라짐(저장값은 유지)
Task T6: fix round 1/5 (1 addressed, 0 open; commits a87b1f2..cbe7727)
Task T6: complete (commits 0d509ac..cbe7727, review clean)
