# 크롤링 네이버 차단 안전장치(B-115) + 요청 간격 0.5초 · 구현 계획 + QA 계획

> 실행: 하네스 네이티브. 구현은 `codex:codex-rescue`(`--wait --fresh`, 쓰기)에 위임. Main Claude는 위임 · 확인 · 리뷰 · 커밋.

**설계:** `02-design.md` · 기획 `01-brainstorm.md`. 기준 `a33b44b`. 참고 `git show 2c4aed1`(B-115 부분만).

## 전역 제약
- 네이버 공식 API 코드 반입 금지(`api_list_page` · `api_configured` · `api_limiter` · external 'naver' 통합 · `total_hint`).
- 실제 외부 사이트 요청 금지(테스트 · QA 모두 가짜 클라이언트 / fixture 채널).
- 사용자 서버(3000 · 3400 · 3401 · 8400 · 8401 · 3310 · 8310)는 건드리지 않는다.
- 흔들림 기본 ±20%(`jitter=0.2`), 기본 간격 0.5초(클리앙 · 뽐뿌 · 네이버 블로그 · 카페).

## 리뷰 집중 지점
1. 블로그 · 카페 동시 목록 수집 시 `search.naver.com` 합산 간격 → T2 테스트.
2. 차단 문구가 200 응답에 섞여 와도 감지 → T2 테스트(상태 코드 매개변수화).
3. 차단 실패가 본문 재시도 3회를 다 써서 글이 빠지지 않음 → T3 테스트.
4. 덮어쓰기 버그로 저장된 `min_interval_s=0` 기존 설정에서도 어댑터 0.5초가 받침 → T1 테스트.
5. 재개 후 차단 작업 복귀 · 같은 작업 중복 없음 → T3 테스트.

### T1: 제한기 흔들림 · 기본 간격 0.5 · 설정 덮어쓰기 수정 (Codex)
**파일:** `backend/app/crawl/ratelimit.py`, `backend/app/crawl/adapters/community.py`, `backend/app/crawl/worker.py`(기본값 줄만), `backend/app/crawl/control.py`(표시 기본값만), `backend/app/routers/crawl_v2.py`, `frontend/src/lib/logic/crawlConfig.ts`, 테스트 `backend/tests/crawl/test_resume.py`(제한기), `backend/tests/crawl/test_crawl_api.py`, `backend/tests/crawl/test_final_w4.py`, `backend/tests/crawl/adapters/test_community.py`, `frontend/src/lib/logic/finalW4.test.ts`
- RED: `test_limiter_jitter_bounds`(고정 난수 0/0.5/1 → 0.4/0.5/0.6초), `test_limiter_zero_interval_no_jitter`, `test_partial_naver_limits_preserve_defaults`(2c4aed1 참고), `test_default_interval_half_second`(워커 · 상태 · 어댑터 0.5), 화면 `limits('naver_blog').min_interval_s === 0.5`, 기존 1초 테스트 → 0.5 기대로 수정.
- GREEN · 전체 테스트. 로그 `logs/T1-*.txt`, 보고 `reports/T1.md`.

### T2: 네이버 공용 제한기 · 차단 즉시 감지 (Codex, T1 뒤)
**파일:** `backend/app/crawl/adapters/base.py`, `backend/app/crawl/adapters/naver_common.py`, `backend/app/crawl/worker.py`(공용 제한기 주입 · 호스트 차단 처리), 테스트 신규 `backend/tests/crawl/test_naver_safety.py`, 수정 `backend/tests/crawl/adapters/test_naver.py`
- RED: `test_search_block_stops_host`(상태 200/403 매개변수, 첫 응답에서 두 채널 paused_blocked, 이후 요청 0), `test_shared_search_limiter_spacing`(블로그 · 카페 합산 시작 간격 ≥ 0.4초, 가짜 시계), `test_article_hosts_use_channel_limiter`.
- GREEN · 전체. 로그 `logs/T2-*.txt`, 보고 `reports/T2.md`.

### T3: 차단 실패 재시도 보호 · 재개 복귀 (Codex, T2 뒤)
**파일:** `backend/app/crawl/queue.py`, `backend/app/crawl/worker.py`(blocked 전달), `backend/app/crawl/control.py`(재개 · 미완료 판정), 테스트 `backend/tests/crawl/test_naver_safety.py`, `backend/tests/crawl/test_queue.py`
- RED: `test_blocked_list_failure_keeps_attempts`, `test_detail_blocks_preserve_attempts_on_resume`, `test_resume_requeues_blocked_lists`, `test_resume_no_duplicate_tasks`.
- GREEN · 전체. 로그 `logs/T3-*.txt`, 보고 `reports/T3.md`.

(T1 → T2 → T3 순차: worker.py · control.py 공유)

## 독립 리뷰
Task별 Main Claude diff 검토 + 브랜치 전체 Codex 읽기 전용 리뷰 1회(리뷰 집중 지점 5개, API 코드 반입 여부).

## QA 계획
- worktree(생성 예정) `~/Desktop/dcx_agent-crawl`. 가짜 LLM · fixture 채널, 포트 8317 / 3317, 데이터 `/private/tmp/dcx-crawl-qa`.
- 시작: 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=/private/tmp/dcx-crawl-qa LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake ENABLE_FIXTURE_CHANNEL=true CORS_ORIGINS=http://localhost:3317 .venv/bin/uvicorn app.main:app --port 8317` · 화면 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8317 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3317`
- URL `http://localhost:3317/pipeline/crawling`

| ID | 시나리오 | 기대 | AC |
|---|---|---|---|
| QA1 | 크롤링 설정 "고급 설정" | 클리앙 · 뽐뿌 · 블로그 · 카페 요청 간격 0.5, 유튜브 0 | AC5 |
| QA2 | 키워당 상한만 바꿔 저장 → GET 설정 · 상태 | 간격 0.5 유지(0 아님) | AC1 |
| QA3 | 가짜 채널 수집 시작 → 상태 | 정상 진행 · 오류 없음 | AC7 |
| QA-정적 | 차단 감지 · 공용 간격 · 재시도 보호 | 실제 네이버 접속 없이 T2 · T3 테스트 결과로 갈음(실측은 배포 후 첫 수집에서 관찰) | AC2~AC4 |

## 검증
`development-harness evidence`.

## 되돌리기
머지 커밋 revert(데이터 변경 없음). 운영 중 빠른 완화: 화면 "고급 설정"에서 간격을 1 이상으로 저장하거나 "간격을 늘리고 재개".

## 엔지니어링 리뷰 (요약)
- `2c4aed1`과 main 사이 crawl 파일 변경 없음 → 해당 hunk 이식 충돌 없음(merge-tree 확인).
- 이중 제한기(워커 + 어댑터) 구조는 유지 — 어댑터 0.5가 덮어쓰기 버그 저장분의 바닥 역할.
- 흔들림은 제한기 한 곳에서만 → 테스트 가능(난수 주입).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 0 issues, 0 critical gaps |

- **VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
