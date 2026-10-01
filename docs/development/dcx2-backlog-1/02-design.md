# DCX 2.0 백로그 1차 · 설계

기준: `01-brainstorm.md`(승인) AC-01~AC-14. 기존 설계는 `../dcx2-stage0-2/02-design.md`(커버리지 절) · `../dcx2-stage3-5/02-design-r2.md`.

## 1. B-108 안정화

| # | 동작 | 위치 | 데이터 · API 변화 | 실패 상태 |
|---|---|---|---|---|
| 1 | 감시 사유 유지 (AC-01) | `routers/training_v2.py` 상태 조립(68~71행) | `monitor.reason` 우선순위: 실행 detail.reason → 저장된 `stage5.monitor.reason` → 예외면 `감시 중 오류가 났습니다(<종류>).` → 실패 · 중단이면 `감시를 완료하지 못했습니다.`. `None`으로 덮지 않음 | 없음 |
| 2 | 투표 임대 갱신 (AC-02) | `work/worker.py` 하트비트 스레드, `label/votes.py` | 하트비트(10초)마다 `UPDATE votes SET at=now WHERE run_id=? AND status='pending'`. `reclaim`의 600초 기준은 그대로 | 갱신 실패는 로그만, 다음 하트비트에서 재시도 |
| 3 | 읽기 전용 버전 워커 정리 (AC-03) | `context/versions.py` 새 버전 생성 | 이전 활성 버전의 `paused` 실행(judge · infer)에 중지 요청 → `interrupted` 기록. 워커는 `should_stop`을 보고 종료 | 이미 끝난 실행은 그대로 |
| 4 | 수동 감사 분리 (AC-04) | `label/audit.py` `maybe_new_round`, `routers/labeling_v2.py` 수동 라운드 | `audit_set`에 `kind TEXT DEFAULT 'auto'` 열 추가(마이그레이션: 없는 열이면 `ALTER TABLE`). 자동 일정은 `kind='auto'` 라운드 수로만 계산. 라운드 번호는 지금처럼 전체 MAX+1 | 기존 라운드는 모두 `auto`로 간주(구분 불가) |
| 5 | 감시 중 새 버전 생성 (AC-05) | `context/versions.py` `_idle` | `running` 판정에서 `kind='monitor'` 실행 제외. 버전 생성 때 그 감시 실행에 중지 요청 | 판정 · 전처리 · 학습 · 추론 실행 중이면 지금처럼 409 |
| 6 | 개요 31만 건 (AC-06) | `label/overview.py`, `tests/perf/` | 31만 건 합성 `labels.sqlite`로 `GET /label/{sid}/overview` 응답 시간 측정 테스트(기본 테스트에서는 건너뜀, `-m perf`로 실행). 0.5초 넘으면 집계를 인덱스 · 증분 카운트로 바꿈 | 측정값은 보고서에 기록 |

## 2. B-109 표시

### 2.1 stale 배너 (AC-07)
- 지금: `StageVersion.tsx` `StaleBanner`가 `session.stale[stageN]`이 있으면 항상 보인다.
- 바꿈: 서버가 그 단계를 이 버전에서 다시 끝냈을 때 `stale[stageN]`을 지운다.
  - 3단계: `prep.status`가 `done`이 되면(재사용 포함) `stale.stage3` 삭제
  - 4단계: 라벨링 판정 완료(판정 워커 모두 done) 시 `stale.stage4` 삭제
  - 5단계: 학습 완료 · 내보내기 시 `stale.stage5` 삭제
- 프론트는 기존 조건 그대로(서버 값만 따른다).

### 2.2 사이드바 완료 표시 (AC-08)
- 지금: `StepBar`가 저장된 `step` 순서 이전만 완료로 표시해, 끝났지만 `step`이 갱신되지 않은 단계(예: 크롤링 완료 후 전처리 화면을 바로 연 경우)는 체크가 늦게 붙는다.
- 바꿈: 완료 판정 = max(저장된 step 순서, 서버 상태로 계산한 마지막 완료 단계).
  - 서버 상태 계산(프론트 순수 함수 `completedThrough(session)`): 키워드 4라운드 확정 → 1, 수집 완료 → 2, `prep.status=done` → 3, 라벨링 판정 완료 → 4, `training.exportRef` → 5, 클러스터 결과 → 6.
- UI 모양 · 문구 변화 없음.

## 3. B-110 키 없는 커버리지

### 3.1 구조
```
R2 확정 ──▶ rounds.coverage()
             ├─ 검색광고 연결됨 → naver_searchad.related_queries (기존, 검색량 가중)
             └─ 미연결          → naver_autocomplete.suggestions (신규, 순위 가중)
                                    └─ 결과 저장 coverage.humanQueries (+ source, weights)
            coverage.compute(human, llm, axes, weighting)
```

### 3.2 어댑터 `backend/app/external/naver_autocomplete.py`
- `suggestions(seeds: list[str], client=None) -> list[tuple[str, int]]` : (검색어, 최고 순위 1~10).
- 요청: `GET https://ac.search.naver.com/nx/ac` 파라미터 `q=<seed>&con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&run=2&rev=4&q_enc=UTF-8&st=100`, User-Agent 지정, 타임아웃 10초, 질의 간 1초.
- 응답 `items[0]`의 각 행 첫 값이 검색어. 순서 = 순위.
- 시드: `[bk] + 승인 LLM 키워드 앞 20개`(표시 순서). 시드 자체가 자동완성 결과에 있으면 그대로 포함.
- 같은 검색어(정규화 키 기준)는 가장 높은 순위만 남김.
- 백엔드 설정 `autocomplete_backend: Literal['http','fake'] = 'http'`. `fake`는 `tests/fixtures/autocomplete/*.json`을 읽음.
- 실패: 네트워크 오류 · JSON 형식 오류 · 결과 0개 → `AutocompleteUnavailable`. 질의 일부만 실패하면 받은 것만 쓰고 실패 수를 기록.
- `external/base.py`의 외부 API 서랍 목록에는 넣지 않는다(키 없는 내부 소스, R-114 네이버 카드 제외 원칙 유지).

### 3.3 지표 `keywords/coverage.py`
- `compute(..., weighting: Literal['volume','rank'] = 'volume')`.
  - `rank`일 때 가중치 = `1/순위`. ① = 매칭 가중치 합 ÷ 전체.
  - ② = 순위 구간 `[1–3, 4–6, 7–10]` 세 칸(기존 10분위 대신). 결과 키 `m2_bands = [{'label':'1~3위','value':…}, …]`, `m2`는 `None`.
  - ⑥ = 기존과 동일.
  - ⑦ = `None`, 사유 `no_volume`.
  - `missing_top` = 매칭 안 된 검색어를 순위 오름차순 20개 `(검색어, 순위)`.
- `volume`(검색광고)은 기존 그대로(AC-13).

### 3.4 저장 · API
- `coverage` 저장값에 `source: 'searchad'|'autocomplete'`, `weighting: 'volume'|'rank'`, `seeds`, `failedSeeds` 추가.
- 상태: `connected`(계산됨) · `unconnected`(검색광고 미연결이면서 자동완성도 실패) · `unavailable`(자동완성 실패 사유 포함). R-114 문구는 검색광고만 쓰던 때의 미연결용이므로 아래 3.5로 대체.
- 세션당 1번 받아 저장. `POST .../coverage/refresh`(기존 "다시 계산하기")에서만 다시 받음(AC-10).

### 3.5 UI (`frontend/src/components/keywords/CoveragePanel.tsx`)
| 상태 | 인사이트 | 해석 | 근거 줄 |
|---|---|---|---|
| 자동완성으로 계산됨 | `사람들이 많이 찾는 표현의 62%를 덮고 있습니다.` | 기존 라운드 문구 그대로 | `사람 검색어 148개` · `출처 네이버 자동완성` · `가중 순위 가중` · `매칭 부분일치` |
| 검색광고로 계산됨 | 기존 | 기존 | 기존(`출처 네이버 검색광고 연관키워드`) |
| 자동완성 실패 | `커버리지 계산 불가` | `네이버 자동완성을 받지 못해 커버리지를 계산할 수 없습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.` | `실패한 질의 N개` |
- 지표 요약: ② 이름을 `② 순위 구간별 커버리지`로, 값은 세 칸(1~3위 / 4~6위 / 7~10위). ⑦은 `계산 불가(검색량 없음)`.
- 누락 표: 머리글 `사람 검색어 | 자동완성 순위`(검색광고면 `월간 검색수`).
- **받는 중(약 20초):** 카드 해석 자리에 `네이버 자동완성에서 사람 검색어를 받는 중입니다(약 20초).`, "다시 계산하기" 버튼은 로딩 표시 · 비활성. 이전 값이 있으면 지표는 이전 값을 흐리게 유지.
- **일부 질의 실패:** 계산은 받은 검색어로 하고, 근거 줄에 `질의 21개 중 3개 실패`를 덧붙인다(`failedSeeds` 개수 / 전체 시드 수).
- **② 빈 구간:** 그 순위 구간에 검색어가 없으면 `—`(0%가 아님).
- **누락 표가 빔(모두 덮음):** `자동완성 검색어를 모두 덮고 있습니다.`(검색광고 소스면 기존 문구 유지).
- 접근성: 기존 표 · 카드 구조 유지, 새 열 머리글은 `scope="col"`. 받는 중 문구는 `aria-live="polite"`.
- 반응형: 기존 카드 레이아웃 그대로. 새 화면 없음.

## 4. 권한 · 보안
- 로컬 전용(맥미니). 자동완성은 키 · 계정 없이 공개 응답만 받는다. 응답 원문은 저장하지 않고 검색어 · 순위만 저장한다.
- 시드에 개인정보가 들어가지 않는다(제품명 · 키워드만).

## 5. 테스트 전략
- 백엔드: 어댑터(정상 · 형식 오류 · 일부 실패 · 중복 순위), 지표(rank 가중 · 구간 · ⑦ None · missing 순위 정렬), rounds 소스 선택(검색광고 우선 · 자동완성 대체 · 둘 다 실패), B-108 각 항목 회귀 테스트, 31만 건 성능 테스트(`-m perf`).
- 프론트: CoveragePanel 상태별 문구 · 지표 · 표 머리글, `completedThrough`, stale 배너 숨김은 서버 값 기준.
- 네트워크 금지: 기존 오프라인 픽스처 패턴(`socket.connect` 차단) 유지, 자동완성은 `fake`.

## GSTACK REVIEW REPORT

| Runs | Status | Findings |
|---|---|---|
| plan-design-review (UI 범위: 2.1 · 2.2 · 3.5), 2026-10-01 | 완료 | 4건 발견 · 4건 사용자 승인 반영 |

- 범위 판단: 기존 화면 3곳(키워드 커버리지 카드 · 버전 stale 배너 · 사이드바 단계)의 문구 · 표시 조건 변경. 새 화면 · 레이아웃 없음. 목업 생성과 외부 디자인 리뷰는 범위에 비해 과해 생략(사용자에게 고지).
- 시작 평가 6/10 → 반영 후 9/10. 남은 1점: 실제 화면 확인은 브라우저 QA에서.
- 반영(각각 사용자 승인): ① 받는 중 진행 문구 + 버튼 로딩 · ② 일부 질의 실패를 근거 줄에 표시 · ③ 빈 순위 구간 `—` · ④ 누락 표가 비면 "자동완성 검색어를 모두 덮고 있습니다."
- 2.1 · 2.2는 서버 값 · 완료 계산만 바꾸고 모양 · 문구가 그대로라 추가 결정 없음.

VERDICT: 설계 승인 요청 가능(UI 결정 모두 확정).

NO UNRESOLVED DECISIONS
