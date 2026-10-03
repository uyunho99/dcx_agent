# 리뷰 (Claude, 7883b9a)
- 설계 1절 일치: 임대 = batch × concurrency, 묶음 분할, ThreadPoolExecutor + as_completed, VoteCache 쓰기는 메인 스레드만.
- 예외: 한도 → 기록 없음(release로 임대 해제) · 한도 메시지 우선, 비한도 일시정지 → gpt_backend_failed, 기타 예외 → 다른 묶음 저장 후 재발생(finally에서 release).
- judge_batch는 묶음별 run ID · 파일이라 공유 가변 상태 없음. run_many concurrency=1 명시.
- Jev 경로 무변경. 기존 감사 테스트는 순차 하트비트를 가정해 concurrency=1로 고정(단언 무변경).
- 관찰: 다음 임대는 그룹의 가장 느린 묶음이 끝난 뒤라, 처리량은 동시 수에 정확히 비례하지 않음(QA 4개 → 약 2.7배). 설계 범위 내, 발견으로 올리지 않음.
- 발견 없음.
