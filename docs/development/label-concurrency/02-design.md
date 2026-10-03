# GPT(Codex) 판정 동시 처리 — 설계

기준: 01-brainstorm.md(승인), D-343.

## 1. 판정 워커 (`backend/app/label/judge.py` `run_worker`, labeler='gpt')
- 임대 크기: `settings.label_batch_size * max(1, settings.label_concurrency)`.
- 임대한 글을 문서 ID 순서대로 `label_batch_size`씩 나눠 묶음 목록을 만든다.
- `ThreadPoolExecutor(max_workers=min(label_concurrency, 묶음 수))`로 각 묶음에 `gpt.judge_batch(...)`를 동시에 호출(묶음별 run ID는 기존 규칙 그대로 → 서로 다른 llm_runs 폴더).
- 결과 저장은 **메인 스레드에서** 묶음이 끝나는 순서대로(`as_completed`): 성공 → `cache.put`, 누락 → `cache.fail('invalid_or_missing_vote')`. VoteCache(SQLite) 쓰기를 한 스레드로 유지.
- 예외 처리(묶음별):
  - `LabelerPaused(usage_limit=True)`: 그 묶음 글은 아무것도 기록하지 않음(임대 해제 대상).
  - `LabelerPaused(usage_limit=False)`: 그 묶음 글은 `cache.fail('gpt_backend_failed')`(기존 규칙).
  - 그 외 예외: 다른 묶음이 끝난 뒤 다시 던진다(기존처럼 워커 실패).
- 모든 묶음이 끝난 뒤: 일시정지 사유가 하나라도 있으면 `cache.release()` → `sync` → `_pause(ctx, 첫 사유 메시지, detail)`(한도 사유가 있으면 한도 메시지 우선) → 루프 계속(기존 흐름). 없으면 `sync` 후 다음 임대.
- 하트비트: 워커의 백그라운드 pulse 스레드가 임대를 갱신한다(`_heartbeat_callback` → `cache.refresh`, 기존). 동시 처리 동안에도 그대로 동작 — 추가 변경 없음. 진행률 하트비트(`ctx.heartbeat`)는 묶음 그룹 사이에서 기존처럼.
- `should_stop`은 그룹 사이에서 확인(실행 중인 Codex는 끝까지 기다림 — 기존 단일 묶음과 같은 의미).

## 2. `gpt.judge_batch`
- 스레드 안전성 확인: 묶음마다 독립 run ID · 파일, 공유 가변 상태 없음. `run_many(..., concurrency=...)`의 내부 동시성은 작업 1개라 의미 없으므로 `concurrency=1`로 명시(혼동 방지).

## 3. 설정 · 문서
- `LABEL_CONCURRENCY` 의미: "동시에 처리하는 GPT 묶음 수"(기본 4 유지). README 표 문구 갱신.
- 운영 값: `~/srv/dcx-agent/shared/runtime.env`에 `LABEL_CONCURRENCY=20`(배포 후 API 재시작 시 적용). 설치기가 runtime.env를 다시 쓰므로 `shared/app.env`에 둔다(설치기는 app.env를 덮어쓰지 않음; run-api는 app.env → runtime.env 순서로 읽음, runtime.env에 같은 키가 없으므로 app.env 값이 적용).

## 4. 남은 시간 추정
- 기존 GPT 추정은 최근 10분 처리량(완료 건수/시간) 기반이라 동시 처리 속도를 자동 반영 — 변경 없음, 테스트로 확인.

## 5. UI
화면 변경 없음 — 처리 속도만 바뀐다. 브라우저 QA는 QA 서버에서 판정 진행률이 정상 표시되는지만 확인.
