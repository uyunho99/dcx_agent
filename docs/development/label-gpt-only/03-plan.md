# Jev 미연결 시 GPT 단독 라벨링 — 구현 · QA 계획

기획 [01](01-brainstorm.md) · 설계 [02](02-design.md) 승인(2026-10-03). 구현 담당: Codex(`codex:codex-rescue`, 쓰기 모드). Claude는 위임 · 리뷰 · QA만.

## 0. 작업 환경
- 계획 승인 후 `development-harness worktree /Users/persona1/Desktop/dcx_agent-gpt-only-impl feature/label-gpt-only`로 구현 worktree 생성, 세션 폴더를 그곳으로 옮긴다.
- 준비: `backend/.venv`, `frontend/node_modules`는 main 체크아웃(`~/Desktop/dcx_agent`)의 것을 심볼릭 링크(의존성 변경 없음).
- 기준 검사: `harness.config.json`의 4개 명령(pytest · lint · build · vitest)을 먼저 돌려 기존 실패를 기록한다.

## 1. Task

| ID | 내용 | 담당 파일 | 의존 | AC |
|---|---|---|---|---|
| T1 | 방식 판정 · 저장 · 시작/제어 API · 워커 방어 | `backend/app/config.py`, `backend/app/label/jev.py`, `backend/app/routers/labeling_v2.py`, `backend/app/label/judge.py`, `backend/tests/label/test_gpt_only_mode.py`(신규), 교차 흐름에 기대는 기존 테스트 픽스처(`backend/tests/conftest.py` 등) | — | AC1 |
| T2 | 저장 구조 이전 + 최종 라벨 합치기 + 4단계 완료 | `backend/app/label/store.py`, `backend/app/label/schema.py`, `backend/app/label/route.py`, `backend/app/context/stale.py`, `backend/app/label/overview.py`(sync 호출부만), `backend/tests/label/test_gpt_only_final.py`(신규) | T1(방식 헬퍼) | AC2, AC3, AC5, AC6 |
| T3 | 5단계 학습 · 내보내기 · 보고 · 개요 API | `backend/app/model/dataset.py`, `backend/app/model/train.py`, `backend/app/model/export.py`, `backend/app/label/report.py`, `backend/app/label/overview.py`, `backend/app/label/audit.py`(확인), `backend/app/known/filter.py`(확인), `backend/tests/model/test_gpt_only_training.py`(신규) | T2 | AC4, AC7(API) |
| T4 | 화면 | `frontend/src/lib/api/label.ts`, `frontend/src/components/label/Overview.tsx`, `KappaTable.tsx`, `QueueCard.tsx`, `Audit.tsx`, 필요 시 `queueView.ts` · `workerControls.ts`, 신규 `frontend/src/components/label/labelerMode.ts`(+`.test.ts`), `frontend/src/app/pipeline/labeling/page.tsx`(필요 시) | T3(필드 이름) | AC7 |
| T5 | 문서 | `README.md`(JEV_BACKEND · LABEL_GPT_BACKEND 표 근처), `ops/macmini/README.md`(runtime 기본값 아래 한 줄) | T1 | — |

실행 순서: T1 → T2 → T3 → T4, T5는 T1 뒤 아무 때나(파일 안 겹침). `overview.py`는 T2(호출부)와 T3(응답 필드)이 겹치므로 순차.

### T1 세부
- `settings.label_fake_jev_cross: bool = False`(env `LABEL_FAKE_JEV_CROSS`), 알 수 없는 env 무시 목록 규칙에 맞게 등록.
- `jev_available()`, `labeler_mode(data)`(저장값 → 없고 시작 전이면 `jev_available()` 기준, 시작된 옛 세션 저장값 없음 → `'cross'`).
- `start`: `labelerMode` 저장, `gpt_only`면 gpt 실행만. `control('jev')` in gpt_only → 409 `Jev가 연결되지 않아 GPT 단독으로 판정합니다.` 워커도 같은 문구로 실패.
- 기존 테스트 중 fake Jev 교차 흐름을 쓰는 것은 픽스처에서 `label_fake_jev_cross=True`로 켠다(동작 기대값 변경 금지).
- RED: fake · 키 없음 → gpt_only, http+키 → cross, fake+opt-in → cross; 시작 응답 workers 키 = {'gpt'}; Jev 제어 409; 옛 세션(started, 저장값 없음) → cross.
- 명령: `backend/.venv/bin/python -m pytest backend/tests/label -q`

### T2 세부
- 설계 3 · 4절 그대로. 이전은 `PRAGMA table_info(final)` notnull 확인 → 한 트랜잭션에서 새 테이블 · 복사 · 교체 · 인덱스/트리거 재생성.
- RED:
  - GPT done 3건 + bad 1건, gpt_only → final 3행(`source='gpt_only'`, `route='accepted'`, confidence NULL, level = `rule.grade(GPT 태그)`), 큐 `labeler_failed` 1건, `grade_mismatch` 0건.
  - Jev 캐시가 비어도(또는 없어도) 동작.
  - gpt_only 버전: gpt 실행 done만으로 `labeling.status == 'done'`; cross 버전은 기존대로 둘 다 필요.
  - cross로 바뀐 복사본: 두 표 있는 글의 gpt_only 행 → agreed, human 행 유지.
  - NOT NULL 스키마로 만든 옛 labels.sqlite → 이전 후 행 수 · 값 동일, `label_events` 트리거 동작(새 행 삽입 시 이벤트 기록), 두 번 열어도 재이전 없음.
- 명령: `backend/.venv/bin/python -m pytest backend/tests/label backend/tests/context -q`

### T3 세부
- 학습 대상에 `gpt_only` 채택 포함, `votes.jev` null이면 GPT 0/1 · 사유 GPT 원-핫만. `trainable_count`도 같은 기준.
- `_label_entropy`: gpt_only → 0. 내보내기 confidence null.
- 개요: `labelerMode`, gpt_only면 `progress`에 jev 없음 · `mismatchRate=null` · `labelerAccuracy.jev=null`.
- RED: build_targets가 gpt_only 행 포함 · 소프트 값 = GPT 0/1; trainable_count 포함; export 행 confidence null; overview 필드.
- 명령: `backend/.venv/bin/python -m pytest backend/tests/model backend/tests/label -q`

### T4 세부
- 타입: `labelerMode?: 'cross'|'gpt_only'`, `mismatchRate: number|null`, `confidence: number|null`.
- `labelerMode.ts`: `isGptOnly(o)`, `formatRate(v)`(null → "—"), 안내 문구 상수.
- Overview: 전량 판정 카드 위 안내 상자(`role="status"`), gpt_only면 Jev 카드 · 비용 문구 없음. KappaTable · QueueCard · Audit의 Jev 값 null → "—".
- RED: `labelerMode.test.ts` — gpt_only 판정, "—" 포맷, 안내 문구; 기존 컴포넌트 테스트에 gpt_only 개요 픽스처 1개.
- 명령: `npm --prefix frontend test -- label`, `npm --prefix frontend run lint`, `npx --prefix frontend tsc --noEmit -p frontend`

## 2. TDD 규칙 (Codex에 전달)
RED(새 테스트 실패 확인 · 출력 기록) → GREEN(최소 구현) → 리팩터링. 다른 Task 변경 보존, 담당 외 파일 수정 금지(필요하면 보고). Task별 보고서 `docs/development/label-gpt-only/reports/T<n>.md`에 RED/GREEN 명령 · 결과 요약, 변경 파일.

## 3. 리뷰
- Task별: 설계 절 일치, 교차 방식 동작 불변, null 안전.
- 브랜치 전체: gstack `review` 읽기 전용. 수정은 Codex에 재위임.

## 4. 브라우저 QA (gstack `qa-only`)
- 데이터: 운영 세라젬 세션(s89d92341bdb340b0bd7a5943a1c86dc7, 판정 0건)의 `sessions/<sid>`, `derived/<sid>`, `crawl`, `preprocessed`를 스크래치 폴더로 **복사**(운영 원본은 읽기만). 필요 시 문서를 일부만 판정하도록 QA용 세션 버전을 새로 만든다.
- 서버: 구현 worktree에서 백엔드 `LOCAL_DATA_DIR=<스크래치> JEV_BACKEND=fake LABEL_GPT_BACKEND=fake backend/.venv/bin/uvicorn app.main:app --port 8320`(cwd backend), 화면 `NEXT_PUBLIC_API_URL=http://localhost:8320 npm --prefix frontend run dev -- -p 3320`. URL `http://localhost:3320/pipeline/labeling`.
- 시나리오
  - S1 (AC1 · AC7): 시작 전 안내 상자 "Jev 미연결 · GPT 단독 판정" 표시, 시작 → 진행 카드 GPT 하나, Jev 비용 문구 없음.
  - S2 (AC2 · AC3): 판정 완료 후 최종 라벨 수 = GPT 성공 수, 4단계 완료 표시, 사이드바 5단계 진입 가능.
  - S3 (AC7): 불일치율 · Jev 정확도 "—", 검수 카드(판정 실패 건이 있으면) Jev 열 "—".
  - S4 (AC1): Jev 제어 API 직접 호출 → 409 문구.
  - S5 (AC4): 5단계 학습 대상 수에 GPT 단독 라벨 포함(화면 "학습 가능 라벨 수").
  - S6 (회귀): `LABEL_FAKE_JEV_CROSS=true`로 새 버전 시작 → 기존 교차 화면(Jev · GPT 카드 둘) 그대로.
- 증거: 스크린샷 S1 · S2, 보고서 `docs/development/label-gpt-only/reports/qa.md`.

## 5. 수용 기준 연결
AC1→T1,S1,S4 · AC2→T2,S2 · AC3→T2,S2 · AC4→T3,S5 · AC5→T2 · AC6→T2,S6 · AC7→T3,T4,S1,S3 · AC8→검증 명령 4개.

## 6. 되돌리기
브랜치 미병합 시 worktree 제거로 끝. 병합 후에는 커밋 revert. 데이터: `final.confidence` NULL 허용 이전은 되돌려도 기존 코드가 읽을 수 있다(NOT NULL 제약만 사라짐, NULL 값은 gpt_only 행에만 존재) — revert 전 gpt_only 행이 있는 버전은 새 버전에서 다시 라벨링.
