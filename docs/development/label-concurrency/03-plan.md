# GPT(Codex) 판정 동시 처리 — 구현 · QA 계획

기획 [01](01-brainstorm.md) · 설계 [02](02-design.md) 승인(2026-10-03). 구현 담당: Codex(`codex:codex-rescue`, 쓰기 모드).

## 0. 작업 환경
- `development-harness worktree /Users/persona1/Desktop/dcx_agent-label-conc-impl feature/label-concurrency`.
- `backend/.venv`: 최신 의존성 venv(`~/Desktop/dcx_agent-gpt-only-impl/backend/.venv`) 심볼릭 링크, `npm --prefix frontend ci`.
- 기준 검사: `harness.config.json` 4개 명령.

## 1. Task
| ID | 내용 | 담당 파일 | 의존 | AC |
|---|---|---|---|---|
| T1 | 동시 묶음 처리 · 묶음별 예외 · 메인 스레드 저장 | `backend/app/label/judge.py`, `backend/app/label/gpt.py`(concurrency=1 명시만), `backend/tests/label/test_judge_concurrency.py`(신규) | — | AC1~AC6 |
| T2 | 문서 | `README.md`(LABEL_CONCURRENCY 설명), `ops/macmini/README.md`(운영에서 동시 수 조절: `shared/app.env`의 `LABEL_CONCURRENCY`) | T1 | — |

### T1 RED 테스트 (`judge_batch`를 monkeypatch, 실제 Codex 없음)
- concurrency=4, batch=2, 문서 8건: `judge_batch` 호출 4회가 **겹쳐서** 실행됨(Barrier/Event로 4개가 동시에 들어와야 통과, 타임아웃 시 실패) · 모든 글 done.
- concurrency=1: 호출이 순차(동시 진입 최대 1) · 결과 동일.
- 묶음 중 1개 `LabelerPaused(usage_limit=True)`: 다른 묶음 글 done 저장, 한도 묶음 글 pending(임대 해제) · run 상태 paused · 사유 = 한도 메시지.
- 1개 `LabelerPaused(usage_limit=False)`: 그 묶음 글 bad(`gpt_backend_failed`), 나머지 done, paused.
- 1개 누락(missing): 해당 글 bad(`invalid_or_missing_vote`), 나머지 done.
- 그 외 예외: 다른 묶음 저장 후 예외 전파.
- 중복 없음: 저장된 글 수 = 문서 수, 각 글 1회 put.
- Jev 경로 기존 테스트 무변경 통과.
- 명령: `backend/.venv/bin/python -m pytest backend/tests/label -q -p no:cacheprovider`, 전체 `-n auto`.

## 2. TDD 규칙 (Codex에 전달)
RED → GREEN → 리팩터링, 담당 외 파일 수정 금지, 보고서 `docs/development/label-concurrency/reports/T<n>.md`.

## 3. 리뷰
Codex 읽기 전용 리뷰: 스레드 안전성(VoteCache 메인 스레드 쓰기, settings 읽기), 예외 경로, 임대 해제 · 하트비트.

## 4. QA
- QA 서버(구현 worktree, 8320/3320, 운영 세라젬 복사본 · `LABEL_GPT_BACKEND=fake`, `LABEL_CONCURRENCY=8`): 새 버전에서 라벨링 시작 → 완료 · 최종 라벨 수 = 문서 수 · 진행률 · 예상 시간 표시 정상.
- 실제 Codex 소규모 확인: QA 서버를 `LABEL_GPT_BACKEND=codex_exec`, `LABEL_CONCURRENCY=4`로 재시작, 2분간 판정 → `llm_runs` 아래 서로 다른 run 폴더 4개가 동시에 생성 · 처리량이 단일(분당 ~20) 대비 증가(목표 분당 60건 이상). 이후 정지.
- 운영 반영(UAT): main 병합 → 자동 배포 → `shared/app.env`에 `LABEL_CONCURRENCY=20` → API 재시작 → "이어서 진행" → 처리량 확인.
- 보고서 `docs/development/label-concurrency/reports/qa.md`.

## 5. 수용 기준 연결
AC1→T1,QA · AC2→T1 · AC3→설계(기존 pulse)+QA · AC4→T1 · AC5→T1 · AC6→QA · AC7→검증 명령.

## 6. 되돌리기
`LABEL_CONCURRENCY=1`로 즉시 기존 동작. 코드는 revert. 데이터 형식 변경 없음.
