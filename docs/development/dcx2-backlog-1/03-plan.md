# DCX 2.0 백로그 1차 · 구현 계획 + QA 계획

> 구현은 Codex(`codex:codex-rescue`, 쓰기)에 위임하고 Claude는 분해 · 위임 · 리뷰만 한다. Task마다 RED → GREEN → 리팩터링, 보고서는 `.superpowers/sdd/03-plan/task-<ID>-report.md`.

**목표:** 3~5단계 잔여 안정화(B-108 · B-109)와 키 없는 커버리지(B-110)를 넣는다.
**기준 문서:** `01-brainstorm.md`(AC-01~14) · `02-design.md`(승인).
**기술:** Python 3.12 FastAPI(`backend/.venv`), Next.js + Vitest(`frontend`), SQLite.

## 전역 제약
- 0~2 · 3~5단계 계획의 전역 제약을 그대로 따른다(로컬 전용, 키 값 비노출, UI 문구 규칙, 토큰).
- 테스트는 네트워크 · 키 · codex 없이 돈다(`socket.connect` 차단 패턴). 자동완성은 `AUTOCOMPLETE_BACKEND=fake`.
- 네이버 검색광고 경로(검색량 가중)는 바꾸지 않는다(AC-13).
- 외부 API 서랍에 자동완성을 추가하지 않는다(R-114).
- 기존 백엔드 1,279개 · 프론트 242개 테스트를 깨지 않는다.

## 파일 소유 · 의존 관계

| Task | 내용 | 의존 | 소유 파일(C 새로 · M 수정) |
|---|---|---|---|
| T1 | 자동완성 어댑터 | — | C `backend/app/external/naver_autocomplete.py` · M `backend/app/config.py`(설정 1줄) · C `backend/tests/fixtures/autocomplete/*.json` · C `backend/tests/keywords/test_autocomplete.py` |
| T2 | 순위 가중 지표 | — | M `backend/app/keywords/coverage.py` · M `backend/tests/keywords/test_coverage.py` |
| T3 | 소스 선택 · 저장 | T1 · T2 | M `backend/app/keywords/rounds.py` · M `backend/tests/keywords/test_rounds_api.py` |
| T4 | 커버리지 카드 UI | (계약만) | M `frontend/src/components/keywords/CoveragePanel.tsx` · M/C `CoveragePanel.test.ts` · M `frontend/src/lib/types.ts`(커버리지 타입만) |
| T5 | 감시 사유 유지 | — | M `backend/app/routers/training_v2.py` · C `backend/tests/model/test_monitor_reason.py` |
| T6 | 투표 임대 갱신 | — | M `backend/app/work/worker.py` · M `backend/app/label/votes.py` · C `backend/tests/label/test_lease_refresh.py` |
| T7 | 버전 생성: 일시 정지 워커 정리 · 감시 중 허용 | — | M `backend/app/context/versions.py` · C `backend/tests/context/test_versions_backlog1.py` |
| T8 | 수동 감사 분리 | — | M `backend/app/label/audit.py` · M `backend/app/label/store.py`(열 추가 마이그레이션) · M `backend/app/routers/labeling_v2.py`(수동 라운드 `kind='manual'`) · C `backend/tests/label/test_audit_kind.py` |
| T9 | 개요 31만 건 측정 · 개선 | — | C `backend/tests/perf/test_overview_perf.py` · M `backend/pytest.ini`(또는 conftest, `perf` 마커 · 기본 제외) · M `backend/app/label/overview.py`(목표 초과 시에만) |
| T10 | stale 해제(서버) | — | C `backend/app/context/stale.py` · M `backend/app/prep/pipeline.py`(완료 시 호출 1줄) · M `backend/app/label/judge.py`(판정 완료 시 호출 1줄) · M `backend/app/model/export.py`(내보내기 시 호출 1줄) · C `backend/tests/context/test_stale_clear.py` |
| T11 | 사이드바 완료 계산 | — | C `frontend/src/lib/logic/completedThrough.ts` · C `completedThrough.test.ts` · M `frontend/src/components/StepBar.tsx` · M `frontend/src/app/pipeline/layout.tsx`(세션 전달만) |

- **동시 진행:** 1차 웨이브 = T1 · T2 · T4 · T5 · T6 · T7 · T8 · T9 · T10 · T11(파일 겹침 없음). 2차 웨이브 = T3(T1 · T2 뒤).
- 겹침 점검: T5(`training_v2.py`)와 T10(`model/export.py`)은 서로 다른 파일. T8(`labeling_v2.py` · `audit.py` · `store.py`)과 T9(`overview.py`)도 다른 파일. T10의 `judge.py`는 다른 Task가 건드리지 않는다.

## 계약(T3 ↔ T4)
`GET /keywords/{sid}/...` 응답의 `coverage` 객체(기존 위치 그대로)에 다음을 더한다.
```json
{
  "status": "connected | unconnected | unavailable | loading",
  "source": "searchad | autocomplete",
  "weighting": "volume | rank",
  "seeds": 21, "failedSeeds": 3,
  "humanQueries": [["에어컨 소음 민원", 2]],
  "m1": 0.62, "m2": null,
  "m2_bands": [{"label": "1~3위", "value": 0.7}, {"label": "4~6위", "value": null}, {"label": "7~10위", "value": 0.4}],
  "m6": 0.12, "m7": null, "m7_reason": "no_volume",
  "missing_top": [["에어컨 소음 민원", 2]]
}
```
- `missing_top`/`humanQueries`의 두 번째 값: `source=autocomplete`면 순위, `searchad`면 월간 검색수.
- `unavailable`: 자동완성 실패. `unconnected`: 검색광고 미연결이면서 자동완성 설정이 꺼진 경우(지금은 생기지 않지만 기존 값 호환).
- `loading`: 서버가 백그라운드로 자동완성을 받는 중(R2 확정 직후 또는 "다시 계산하기" 뒤). `startedAt`을 함께 저장하고, 2분이 지나도 `loading`이면(서버 재시작 등) `unavailable`로 본다.
- 재계산: `POST /keywords/{sid}/coverage?refresh=true`만 저장된 `humanQueries`를 버리고 다시 받는다. `refresh` 없는 호출은 저장값을 돌려준다(AC-10).

## Task별 단계

### T1 자동완성 어댑터
- **RED:** `test_autocomplete.py`
  - `test_parses_suggestions_in_rank_order` — 픽스처 `items[0]` → `[('에어컨 소음',1), ('시스템에어컨 소음',2), …]`
  - `test_dedupes_keeping_best_rank` — 두 시드에서 같은 검색어(정규화 키 기준)가 2위 · 5위 → 2위만
  - `test_partial_failure_returns_received_and_counts_failed` — 시드 3개 중 1개 오류 → 결과 + `failed=1`
  - `test_all_failed_raises_unavailable` — 형식 오류 · 0개 → `AutocompleteUnavailable`
  - `test_http_backend_builds_expected_request` — `httpx.MockTransport`로 URL · 파라미터(`q`, `st=100`, `r_format=json`) · User-Agent · 1초 간격(시간 함수 주입) 확인
  - `test_fake_backend_makes_no_http` — `autocomplete_backend='fake'`에서 요청 0회
- **GREEN:** `suggestions(seeds, client=None, sleep=time.sleep) -> AutocompleteResult(queries: list[tuple[str,int]], failed: int, total: int)`. 설정 `autocomplete_backend: Literal['http','fake']='http'`.
- 명령: `backend/.venv/bin/python -m pytest backend/tests/keywords/test_autocomplete.py -q`

### T2 순위 가중 지표
- **RED:** `test_coverage.py`에 추가
  - `test_rank_weighting_m1` — 순위 1 · 2 · 4 중 1 · 4 매칭 → (1 + 0.25)/(1 + 0.5 + 0.25)
  - `test_rank_bands_three_with_empty_band_none`
  - `test_rank_mode_m7_none_with_reason`
  - `test_rank_missing_top_sorted_by_rank_limit_20`
  - 기존 volume 테스트 전부 유지(AC-13)
- **GREEN:** `compute(human, llm, human_axes=None, weighting='volume')` → `CoverageReport`에 `m2_bands`, `m7_reason` 필드 추가(volume 모드는 `m2_bands=None`, `m7_reason=None`).
- 명령: `… -m pytest backend/tests/keywords/test_coverage.py -q`

### T3 소스 선택 · 저장
- **RED:** `test_rounds_api.py`에 추가
  - `test_coverage_uses_searchad_when_connected`(기존 동작, 자동완성 호출 0)
  - `test_coverage_falls_back_to_autocomplete_when_unconnected` — 시드 = `[bk] + 승인 LLM 키워드 앞 20개(표시 순서)`, 저장값 `source=autocomplete`, `weighting=rank`, `seeds`, `failedSeeds`
  - `test_coverage_autocomplete_unavailable_status` — 파이프라인 계속(라운드 생성 가능)
  - `test_coverage_cached_once_refresh_refetches`(AC-10)
  - `test_missing_top_feeds_r3_inputs`(AC-12)
  - `test_r2_commit_returns_before_autocomplete_finishes` — R2 확정 응답 시점의 `coverage.status == 'loading'`, 백그라운드 완료 뒤 `connected`(테스트는 `rounds.execute`를 즉시 실행으로 바꿔 순서 확인)
  - `test_stale_loading_over_2min_reads_unavailable`
  - `test_refresh_param_refetches_only_when_true`
- **GREEN:** R2 확정 뒤 커버리지 계산을 기존 라운드 생성과 같은 `rounds.execute` 백그라운드로 돌린다(시작 시 `status=loading` 저장). `compute_coverage`에서 `naver_searchad.Unconnected`면 `naver_autocomplete.suggestions`로 대체, `coverage.compute(..., weighting='rank')`.
- 명령: `… -m pytest backend/tests/keywords -q`

### T4 커버리지 카드 UI
- **RED:** `CoveragePanel.test.ts`
  - 자동완성 계산됨: 인사이트 퍼센트, 근거 `출처 네이버 자동완성` · `가중 순위 가중` · `사람 검색어 N개`
  - 일부 실패: 근거에 `질의 21개 중 3개 실패`
  - 실패(`unavailable`): 해석 `네이버 자동완성을 받지 못해 커버리지를 계산할 수 없습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.`
  - 받는 중: `네이버 자동완성에서 사람 검색어를 받는 중입니다(약 20초).` + 버튼 로딩 · `aria-live="polite"`
  - ② 이름 `② 순위 구간별 커버리지`, 빈 구간 `—`; ⑦ `계산 불가(검색량 없음)`
  - 누락 표 머리글 `자동완성 순위`, 빈 표 `자동완성 검색어를 모두 덮고 있습니다.`
  - 검색광고 소스 · R-114 미연결 문구는 기존 그대로
  - `status=loading`이면 3초마다 다시 읽고(끝나면 멈춤), R3 생성 버튼은 비활성 + `커버리지를 받는 중입니다. 끝나면 R3를 만들 수 있습니다.`(최대 약 20초)
- **GREEN:** 계약 필드 기준으로 분기. 순수 함수(문구 · 지표 행 생성)를 분리해 테스트.
- 명령: `npm --prefix frontend test -- --run CoveragePanel`

### T5 감시 사유 유지 (AC-01)
- **RED:** `test_monitor_reason.py` — done+오류 → 저장 사유 유지, 예외 이름만 → `감시 중 오류가 났습니다(ValueError).`, 실패 → `감시를 완료하지 못했습니다.`
- **GREEN:** 설계 1-#1 우선순위.

### T6 투표 임대 갱신 (AC-02)
- **RED:** `test_lease_refresh.py` — 하트비트 호출 시 해당 `run_id`의 pending 임대 `at` 갱신, 650초 경과 시뮬레이션에서 살아 있는 워커 임대가 `reclaim`으로 회수되지 않음, 다른 run의 임대는 건드리지 않음.
- **GREEN:** 하트비트에 임대 갱신 콜백 연결(판정 워커가 등록).

### T7 버전 생성 정리 (AC-03 · AC-05)
- **RED:** `test_versions_backlog1.py` — 이전 버전 `paused` judge/infer 실행 → 버전 생성 후 `interrupted`; 감시(`monitor`)만 running → 생성 성공 + 감시 중지 요청; judge/prep/train/infer running → 409 유지.
- **GREEN:** `_idle`에서 monitor 제외, 생성 트랜잭션 뒤 중지 요청.

### T8 수동 감사 분리 (AC-04)
- **RED:** `test_audit_kind.py` — 채택 500건에서 수동 라운드 생성 → 채택 1,000건 도달 시 자동 1라운드가 생김; 기존 DB(열 없음) 열면 마이그레이션되고 기존 라운드는 `auto`.
- **GREEN:** `audit_set.kind` 열, 자동 일정은 `kind='auto'` 수로.

### T9 개요 성능 (AC-06)
- **RED:** `test_overview_perf.py`(`@pytest.mark.perf`) — 31만 건 합성 labels.sqlite · 큐 · 문서 메타로 개요 2회(캐시 따뜻) 호출, 두 번째 ≤ 0.5초. 결과 시간을 출력.
- **GREEN:** 측정만으로 통과하면 코드 변경 없음. 초과 시 `overview.py` 집계를 인덱스 · 카운트 캐시로.
- 명령: `… -m pytest backend/tests/perf -m perf -q -s`(기본 실행에서는 `-m "not perf"`로 제외)

### T10 stale 해제 (AC-07)
- **RED:** `test_stale_clear.py` — `stale.stage3`가 있는 v2에서 전처리 완료(재사용 포함) → 삭제; `stale.stage4` → 판정 워커 모두 done 때 삭제; `stale.stage5` → 내보내기 때 삭제; 다른 단계 stale은 유지.
- **GREEN:** `clear_stale(sid, version, stage)` 한 곳 + 세 호출 지점.

### T11 사이드바 완료 (AC-08)
- **RED:** `completedThrough.test.ts` — 키워드 확정 → 1, 수집 완료 → 2, prep done → 3, 라벨링 판정 완료 → 4, exportRef → 5, 클러스터 → 6; 저장 step보다 앞서면 큰 값.
- **GREEN:** StepBar 완료 판정 = max(stepIndex(step), completedThrough(session)).

## 검증 명령
```
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend test
```
성능: `backend/.venv/bin/python -m pytest backend/tests/perf -m perf -q -s`(보고서 기록, 하네스 기본 검증에는 넣지 않음).

## 브라우저 QA 계획
- 시작: 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=<QA 임시 폴더> LLM_BACKEND=fake ENABLE_FIXTURE_CHANNEL=true FIXTURE_CORPUS_PATH=<합성 CSV> EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3310 .venv/bin/uvicorn app.main:app --port 8310`, 프론트 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8310 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3310`
- 테스트 URL: `http://localhost:3310/pipeline/keywords` · `/pipeline/preprocess` · `/pipeline/labeling` · `/pipeline/training`

| ID | 시나리오 | 기대 | AC |
|---|---|---|---|
| QA-C1 | 새 세션 R1 · R2 확정 → 커버리지 카드 | ① 퍼센트, ② 세 칸, ⑥ 값, ⑦ "계산 불가(검색량 없음)", 출처 "네이버 자동완성 · 순위 가중" | AC-09 |
| QA-C2 | "다시 계산하기" | 받는 중 문구 · 버튼 로딩 → 다시 계산 | AC-10 · 3.5 |
| QA-C3 | 가짜 자동완성을 실패로(픽스처 없음) 두고 계산 | 실패 문구, R3 생성 계속 가능 | AC-11 |
| QA-C4 | 누락 표 | 순위 순, 머리글 "자동완성 순위" | AC-12 |
| QA-V1 | 3단계부터 다시 → v2에서 전처리 실행 완료 | stale 배너 사라짐 | AC-07 |
| QA-S1 | 크롤링만 끝난 세션을 전처리 화면으로 바로 열기 | 사이드바 크롤링 완료 체크 즉시 | AC-08 |
| QA-M1 | 감시 실행 중 "4단계부터 다시" | 새 버전 생성 성공 | AC-05 |
| QA-R | 1024×768 커버리지 카드 | 가로 스크롤 없음 | — |

## 수용 기준 연결
| AC | Task · 근거 |
|---|---|
| 01 | T5 |
| 02 | T6 |
| 03 · 05 | T7 · QA-M1 |
| 04 | T8 |
| 06 | T9(성능 보고) |
| 07 | T10 · QA-V1 |
| 08 | T11 · QA-S1 |
| 09 | T1 · T2 · T3 · T4 · QA-C1 |
| 10 | T3 · T4 · QA-C2 |
| 11 | T1 · T3 · T4 · QA-C3 |
| 12 | T2 · T3 · QA-C4 |
| 13 | T2 · T3(기존 테스트 유지) |
| 14 | 전체 검증 명령 |

## 되돌리기
- main 머지 커밋을 `git revert -m 1 <merge>`로 되돌린다. 데이터 변경은 `audit_set.kind` 열 추가뿐이며(기존 코드는 이 열을 무시) 되돌려도 안전하다. 자동완성 저장값은 `coverage`의 추가 필드라 이전 코드가 무시한다.

## GSTACK REVIEW REPORT

| Runs | Status | Findings |
|---|---|---|
| plan-eng-review(계획 · 2026-10-01) | 완료 | 1건 사용자 결정 · 3건 계획에 반영 |

- 아키텍처: 어댑터 한 곳(T1) · 순수 지표(T2) · 소스 선택(T3)으로 나눠 검색광고 경로를 건드리지 않는다. 계약(T3↔T4)을 계획에 고정해 T4를 1차 웨이브에서 함께 진행한다.
- 사용자 결정 E1: R2 확정 요청이 자동완성 21회(약 20초)를 기다리지 않도록 **백그라운드 실행**(기존 `rounds.execute` 재사용). 카드는 받는 중 문구 + 3초 폴링, R3 버튼은 받는 동안 비활성.
- 계획 반영(기계적 결정): E2 `refresh=true`일 때만 재수집(AC-10) · E3 2분 넘은 `loading`은 `unavailable`로(서버 재시작 대비) · E4 성능 테스트는 `perf` 마커로 기본 검증에서 제외하고 보고서에 측정값 기록.
- 파일 겹침: 1차 웨이브 10개 Task 모두 소유 파일 분리 확인. T3만 T1 · T2 뒤.
- 테스트: AC-01~14 모두 Task 테스트 또는 QA 시나리오에 연결(위 표). 네트워크 없는 실행 유지.
- 실패 · 되돌리기: 되돌리기 절 참조. 데이터 변경은 `audit_set.kind` 열 추가뿐.

VERDICT: 계획 승인 요청 가능.

NO UNRESOLVED DECISIONS
