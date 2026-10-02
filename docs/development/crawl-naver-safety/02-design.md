# 크롤링 네이버 차단 안전장치(B-115) + 요청 간격 0.5초 · 설계

기획: `01-brainstorm.md`. 기준 `a33b44b`. 참고 구현: 커밋 `2c4aed1`(B-115 부분만 옮기고 네이버 공식 API 부분은 버린다).

## 1. 구조 (서버 중심 · 화면은 초기값 숫자만)
| 파일 | 변경 |
|---|---|
| `backend/app/crawl/ratelimit.py` | `ChannelLimiter(concurrency, min_interval_s, *, jitter=0.2, rng=random.random, clock, sleep)` — 다음 시작 시각 = 지금 + `min_interval_s × (1 + jitter × (2·rng() − 1))`. `min_interval_s=0`이면 흔들림 없음. 기존 시그니처 호환(키워드 인자 추가만). |
| `backend/app/crawl/adapters/community.py:54` | 어댑터 고정 간격 `1.0` → 모듈 상수 `DEFAULT_INTERVAL_S = 0.5` |
| `backend/app/crawl/adapters/base.py` | `AdapterBlocked(message='', *, host=None)` |
| `backend/app/crawl/adapters/naver_common.py` | `search_limiter`(기본 = 어댑터 자체 제한기, 워커가 공용 제한기로 교체) · `request()`에서 `search.naver.com` 요청은 `search_limiter` 사용 · 응답 본문에 `검색 서비스 이용이 제한` 포함 시 `search_limiter.blocked = True` 후 `AdapterBlocked(host='search.naver.com')`, 이후 같은 제한기 요청은 즉시 `AdapterBlocked`. **API 관련 코드(`api_list_page`, `api_configured`, `api_limiter`) 제외.** |
| `backend/app/crawl/worker.py` | (a) 채널 기본값 `(1, 1)` → `(1, 0.5)`(클리앙 · 뽐뿌 · 블로그 · 카페) (b) 목록 · 본문 실행 시작 때 블로그 · 카페 어댑터에 공용 `search_limiter = ChannelLimiter(1, max(두 채널 간격, 기본 0.5))` 주입 (c) `AdapterBlocked.host == 'search.naver.com'`이면 블로그 · 카페 둘 다 즉시 `paused_blocked` (d) `mark_list_failed` · `mark_failed_attempt`에 `blocked=isinstance(error, AdapterBlocked)` 전달 |
| `backend/app/crawl/queue.py` | `mark_list_failed(..., *, blocked=False)` — blocked면 시도 수 증가 없이 `pending` · `requeue_blocked_lists(sources)` — `last_error='AdapterBlocked'`로 실패한 목록 작업을 대기로 · `mark_failed_attempt(..., *, blocked=False)` — blocked면 시도 수 유지, `retry_at` 설정, 소진 아님 |
| `backend/app/crawl/control.py` | 상태 표시 기본 간격 1 → 0.5 · 재개 시 `requeue_blocked_lists` · 차단 실패가 남은 목록 실행은 미완료로 판정 |
| `backend/app/routers/crawl_v2.py:112` | `perChannel` 저장 시 `model_dump(exclude_unset=True)` — 보낸 칸만 저장(덮어쓰기 버그 수정) |
| `frontend/src/lib/logic/crawlConfig.ts:23` | 4채널 `min_interval_s` 초기값 1 → 0.5 |
| `frontend/src/lib/logic/finalFix.ts` | 변경 없음(두 배, 최소 1초) |

## 2. 데이터 · 동작
- 공용 제한기는 실행(목록 · 본문)마다 하나. 블로그 · 카페 중 하나만 수집하면 그 채널 간격 그대로.
- `blog.naver.com` · 카페 글 API 등 본문 서버는 채널별 제한기(0.5초 ± 20%).
- 차단 감지 후 상태 `paused_blocked`는 기존 화면 문구 · "간격을 늘리고 재개" · "여기까지로 마치기" 흐름을 그대로 쓴다.
- 저장 데이터 이전 없음. 이미 저장된 설정의 `min_interval_s=0`(덮어쓰기 버그로 저장된 값)은 그대로 0으로 읽힌다 → 어댑터 기본 제한기(0.5초)가 아래에서 받친다.

## 3. 실패 상태
| 상황 | 결과 |
|---|---|
| 차단 문구 응답 | 첫 응답에서 블로그 · 카페 `paused_blocked`, 재시도 횟수 증가 없음 |
| 문구 없는 403/429 | 기존 20회 연속 규칙, 재시도 횟수 증가 없음 |
| 재개 | 차단 실패 목록 · 본문 작업 대기열 복귀, 간격은 재개 요청 값 |
| 클리앙 · 뽐뿌 차단 | 기존 규칙(채널별) |

## 4. UI
화면 구성 변경 없음. "고급 설정" 요청 간격 초기값만 1 → 0.5. `plan-design-review` 미적용(숫자 기본값만 바뀜).

## 5. 권한 · 외부
네이버 공식 API · 키 사용 없음(D-094 · D-095). 법률 · 약관 검토는 범위 밖(프로젝트 원칙).

## 6. 테스트
- 단위: 흔들림 범위 · 0 간격 무흔들림(가짜 시계 · 고정 난수), 공용 제한기로 블로그+카페 합산 간격, 차단 문구 즉시 감지 · 이후 요청 0건, blocked 실패 시 시도 수 유지 · 재개 시 복귀, perChannel 부분 저장 기본값 유지, 기본 간격 0.5(서버 · 상태 · 화면).
- 기존 1초 기대 테스트 갱신: `test_final_w4.py:110`, `adapters/test_naver.py:270`, `adapters/test_community.py:167`, `frontend finalW4.test.ts:9`. `finalFix.test.ts:31`(최소 1초)은 유지.
- 브라우저: 크롤링 설정 화면 "고급 설정" 초기 간격 0.5 표시. 실제 네이버 수집은 하지 않음(가짜 채널).
