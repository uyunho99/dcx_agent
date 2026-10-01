# gstack /review — 백로그 1차 (feature/dcx2-backlog-1)

- 모드: READ-ONLY (Fix-First 자동 수정 · 사용자 질문 생략, 서브에이전트 · Codex 적대 패스 생략 — 별도 Codex 리뷰가 병행)
- 기준: DIFF_BASE=40ca7fe (fetch 안 함) · HEAD 675760a · 코드 변경 30개 파일(백엔드 19 · 프론트 9 · 테스트/설정), 문서 다수
- 이전 학습 적용: `dcx-full-session-save` (confidence 9/10, 2026-09-29) — `completion`이 `/save-session`의 서버 소유 키 목록에 들어가 있어 덮어쓰기 위험 없음을 확인함.
- 이미 알려진 보류 항목(progress.md 마지막 줄)은 다시 보고하지 않음.

## Scope Check

```
Scope Check: DRIFT DETECTED (minor, all justified by ledger rulings or review fixes)
Intent: B-108·B-109 안정화(AC-01~08) + 키 없는 자동완성 커버리지 B-110(AC-09~13), 네트워크 없는 테스트(AC-14)
Plan: docs/development/dcx2-backlog-1/03-plan.md
Delivered: 자동완성 어댑터 · 순위 가중 지표 · 백그라운드 커버리지 작업과 refresh · 커버리지 카드/폴링, 감시 사유 · 임대 갱신 · 버전 생성 정리 · audit_set.kind · stale 해제 · 사이드바 완료 신호, 테스트 외부 접속 차단
Plan items: 11 Task DONE (T9는 CHANGED), 브라우저 QA 8건 UNVERIFIABLE
Out-of-plan files (계획 소유표 밖):
  - backend/app/routers/keywords_v2.py (refresh 파라미터 · GET에서 coverage_status) — ledger 판단으로 허용
  - frontend/src/app/pipeline/keywords/page.tsx, frontend/src/lib/api/keywords.ts — ledger 판단으로 허용
  - backend/app/routers/sessions.py (`completion` 페이로드) — 표시 리뷰 fix1 (AC-08 신호 부족)
  - backend/app/model/infer.py (새 감시 시작 시 `training.monitor=None`) — T5 보조, 기록 없음
  - backend/app/label/judge.py 구조 변경(T6 콜백 + T10 judge_done), backend/app/label/overview.py 배치 저장(fix1 판단)
  - backend/tests/conftest.py, backend/tests/test_no_network.py (T12-netfix)
  - backend/tests/label/perf_stability.py (pytest plugin, perf 측정 보조)
```

## Plan Completion Audit

```
PLAN COMPLETION AUDIT
Plan: docs/development/dcx2-backlog-1/03-plan.md

## Implementation Items
  [DONE]     T1 자동완성 어댑터 — backend/app/external/naver_autocomplete.py, config.autocomplete_backend
  [DONE]     T2 순위 가중 지표 — backend/app/keywords/coverage.py (m2_bands, m7_reason, 1/rank)
  [DONE]     T3 소스 선택 · 백그라운드 · refresh — backend/app/keywords/rounds.py, routers/keywords_v2.py
  [DONE]     T4 커버리지 카드 · 3초 폴링 · R3 비활성 — CoveragePanel.tsx, keywords/page.tsx
  [DONE]     T5 감시 사유 유지 — routers/training_v2.py (+ model/infer.py)
  [DONE]     T6 하트비트마다 임대 갱신 — work/worker.py, label/votes.py, label/judge.py
  [DONE]     T7 버전 생성 시 paused judge/infer 중지 · monitor 허용 — context/versions.py
  [DONE]     T8 audit_set.kind + 마이그레이션 — label/store.py, label/audit.py, routers/labeling_v2.py
  [CHANGED]  T9 개요 성능 — 따뜻한 호출은 코드 변경 없이 통과(0.284s), 차가운 색인은 배치 저장으로 변경(overview.py)
  [DONE]     T10 stale 해제 — context/stale.py + prep/pipeline.py · label/judge.py · model/export.py 호출
  [DONE]     T11 사이드바 완료 — lib/logic/completedThrough.ts, StepBar.tsx, layout.tsx (+ 서버 completion)

## Test Items
  [DONE]     T1~T11 테스트 파일 모두 존재(test_autocomplete, test_coverage, test_rounds_api, CoveragePanel.test,
             test_monitor_reason, test_lease_refresh, test_versions_backlog1, test_audit_kind, perf/test_overview_perf,
             test_stale_clear, completedThrough.test) + test_session_completion, test_index_batches, test_no_network
  [DONE]     perf 마커 기본 제외 — backend/pytest.ini addopts -m "not perf"

## Browser QA (QA-C1~C4, QA-V1, QA-S1, QA-M1, QA-R)
  [UNVERIFIABLE] diff에 QA 보고서 없음 — build.json · reports/에 브라우저 QA 근거가 없음. /qa 단계에서 확인 필요.

COMPLETION: 10/11 DONE, 1 CHANGED, 0 NOT DONE; QA 8건 UNVERIFIABLE
```

## Findings (main report, confidence ≥ 5)

Severity 기준: P0 = 데이터 손실/보안, P1 = 사용자 흐름이 틀어짐, P2 = 정보성/경계 사례.

1. **[P2] (confidence 8/10) backend/app/keywords/rounds.py:385,422,426 + backend/app/external/naver_autocomplete.py:54 — 받는 중(fetching) 단계에 `updatedAt` 갱신이 없어 느린 응답에서 2분 판정을 넘긴다.**
   `begin`이 `'phase': 'fetching', 'startedAt': now, 'updatedAt': now`를 저장한 뒤, 첫 `progress(...)`는 `suggestions(seeds)`가 모두 끝난 뒤(426행)에야 불린다. 요청마다 `timeout=10`이고 사이에 `sleep(1)`이 있어서, 네이버가 느리거나 막으면 시드 21개 × 약 11초 ≈ 230초가 걸릴 수 있다. 이는 `coverage_status`의 `if age > 120:`(349행)를 넘는다. 이렇게 되면 (a) GET 결과가 `unavailable/interrupted`로 바뀌어 폴링이 멈추고 R3 버튼이 다시 켜진다. (b) 저장소 쪽 상태는 여전히 `loading`이고 `startedAt`도 같아서, 늦게 끝난 작업이 나중에 `connected`를 써 넣는다. 화면은 새로고침해야 이 값을 보고, 그 사이 R3는 이미 "커버리지 계산 실패" 입력으로 만들어졌을 수 있다. (c) 그 사이 "다시 계산하기"를 누르면 새 작업이 시작되는데, 이전 작업은 남은 시드를 다 보낼 때까지 네이버를 계속 부른다.
   Fix: `suggestions()`에 시드마다 부르는 콜백을 넘겨 `progress({})`로 `updatedAt`을 갱신하고, 상위 작업이 superseded면 멈추게 한다. 또는 전체 마감 시간을 120초보다 짧게 둔다(예: 요청 timeout 3초 + 전체 90초).

2. **[P2] (confidence 7/10) backend/app/keywords/rounds.py:111-135 (start_round) — R3 생성을 막는 조건이 서버에 없고 UI에만 있다.**
   `start_round`의 `patch`는 `_order` · running · committed만 검사하고 `coverage.status`는 보지 않는다. `page.tsx`의 `r3Blocked` · `(round === 2 && coverageLoading)`만 막는다. 다른 탭에서 열었거나, 화면이 오래된 경우, 또는 API를 직접 부르면 받는 중에 R3가 시작된다. 이때 `_inputs`(188~193행)는 `loading`을 어느 분기에도 넣지 않아 `coverage_text=''`가 되고, `r3_input_status`는 이를 `empty:searchad_unconnected`로 기록한다. 그래서 자동완성 경로인데도 출처가 잘못 남는다.
   Fix: `start_round(n=3)`에서 `coverage_status(...)['status'] == 'loading'`이면 409 `StoreError('커버리지를 받는 중입니다…')`를 낸다. 또는 `_inputs`가 loading을 따로 표시하게 한다.

3. **[P2] (confidence 5/10, medium — 실제 문제인지 확인 필요) backend/app/keywords/rounds.py:376,383-385 — loading 상태가 이전 결과의 필드를 그대로 물려받는다.**
   `{**saved, 'status': 'loading', 'source': source, ...}`는 이전의 `humanQueries` · `weighting` · 지표 · `error`(`interrupted` 포함)를 그대로 둔다. refresh 작업이 2분 판정을 넘긴 뒤 R2를 다시 확정하면(refresh 없음) 376행 `if not refresh and 'humanQueries' in saved`가 **이전** 캐시로 다시 계산해 `connected`를 돌려준다. 사용자가 요청한 새로 받기는 소리 없이 사라진다. 또 `source`는 새 값으로 바뀌었는데 `weighting`은 이전 값이라, 검색광고 키를 넣거나 뺀 사이에는 카드가 "자동완성"이라고 표시하면서 실제로는 검색량 가중으로 계산할 수 있다.
   Fix: loading으로 바꿀 때 `humanQueries`/`humanAxes`/`weighting`/`error`를 따로 보관(예: `previous`)하거나 지운다. `source`와 `weighting`은 같은 쪽에서 함께 정한다.

## Checklist pass notes (no finding)

- SQL & Data Safety: 새 SQL은 모두 매개변수 바인딩을 쓴다(`votes.refresh`, `audit_set` INSERT, `_stop_readonly_workers`, `_completion`의 읽기 전용 URI). `audit_set.kind` 마이그레이션은 `BEGIN IMMEDIATE` 안에서 PRAGMA 확인 → ALTER 순서로 돌아 동시에 열어도 안전하다. 기존 행은 DEFAULT로 `'auto'`가 된다. `versions._restart_labels`의 `DELETE FROM audit_set`도 새 열과 맞는다.
- Race/Concurrency: 커버리지 작업은 `startedAt` 펜스(`_JobSuperseded`)로 이전 작업이 결과를 덮어쓰지 못하게 한다. 분류 중 하트비트 스레드는 superseded 예외를 받으면 끝난다. `judge_done`은 store.locked → transaction 순서인데, 다른 `with transaction` 블록 안에서 store 잠금을 잡는 곳이 없어 교착 순서 문제는 없다. 임대 갱신은 `_pulse`의 `rowcount`가 있을 때(이 프로세스가 아직 주인일 때)만 한다.
- Untrusted response parsing (adapter): `isinstance`로 형태를 검사하고, `items[0][:10]`로 자르고, `norm_key`가 빈 값이면 해당 시드 전체를 실패로 센다. JSON 오류와 UnicodeDecodeError는 ValueError로 잡힌다. httpx는 기본으로 리디렉트를 따라가지 않고, `raise_for_status`가 3xx도 오류로 처리한다. `q`는 params로 인코딩되고 URL은 고정이라 SSRF 위험이 없다.
- LLM trust boundary: 자동완성 문자열은 기존 검색광고 경로와 같은 방식으로 `kw_axis_classify` · R3 입력에 JSON으로 들어간다. 분류 결과는 `coverage.compute`가 `human_axes.get(query) in axes`로 검사한다(108행).
- Enum completeness: 새 상태 `loading`/`unavailable`은 `_inputs`, `coverage_status`, CoveragePanel(해석 · 근거 · 지표), page.tsx에서 처리된다. 서버의 R3 진입은 위 #2 참고.
- Frontend polling: `startCoveragePolling`은 terminal 응답에서 멈추고 언마운트 때 타이머를 정리한다. `coverageLoading` 의존 effect가 다시 시작하는 일도 없다.
- `completion`: `/save-session`의 소유 키에 들어 있어 클라이언트가 보낸 값이 저장되지 않는다. 계산 실패는 필드마다 False로 처리해 세션 읽기를 막지 않는다.

## Appendix — suppressed (confidence ≤ 4)

- [P2] (4/10) naver_autocomplete.py:31-45 — 제안 문자열 길이와 응답 크기에 상한이 없다. 값은 session.json과 LLM 프롬프트에 그대로 들어간다. 호스트는 고정된 네이버이고 상위 10개로 잘라서 위험은 낮다. Fix: `row[0][:100]`처럼 길이를 자른다.
- [P2] (4/10) CoveragePanel.tsx:54 — 읽기 오류가 계속되면 3초마다 무한히 다시 시도하며 오류 배너를 갱신한다. Fix: 연속 실패 N회에서 멈추거나 백오프한다.
- [P2] (4/10) routers/sessions.py `_completion.crawl_done` — GET 세션마다 `phase_state` → `report.can_finalize`(큐 sqlite 읽기)를 부른다. 큰 수집본에서 비용을 측정하지 않았다.
- [P2] (4/10) naver_autocomplete.py:17 — fake 백엔드가 `backend/tests/fixtures/...`에 의존한다. tests 없이 배포하면 fake가 항상 unavailable이 된다(QA 전용이라 영향 작음).
- [P2] (3/10) rounds.py:390-394 — `mutate` 뒤 `assert_writable`이 실패하면(그 사이 버전이 바뀜) loading이 남은 채 요청이 오류로 끝나고, 2분 뒤에야 unavailable이 된다.

## Review Army / adversarial

- Review Army 전문가 디스패치는 생략했다(서브에이전트 금지 지시). 대신 테스트 · 보안 · 성능 · 데이터 마이그레이션 · API 계약 관점은 위 체크리스트 패스에서 직접 살폈다.
- Codex 적대 패스는 지시에 따라 생략했다(별도 Codex 리뷰가 병행).
- Shared-code 기회: 없음. `coverage_status`/`progress`/`finish`의 펜스 패턴은 라운드 작업과 비슷하지만, 계약(상태 키 · 2분 판정)이 달라 추출할 이득이 없다.

Pre-Landing Review: 3 issues (0 critical, 3 informational)
