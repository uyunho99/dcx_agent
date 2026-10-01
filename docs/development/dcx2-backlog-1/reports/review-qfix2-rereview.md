# QA 2회차 수정(Q5) 리뷰 (c0fc3ee..7eefcf6)

## 1차 리뷰 — Needs fixes
- Important 1: 학습 내보내기 뒤 세션 갱신 실패가 저장 실패로 보이고 이동이 막힘(재시도 시 재내보내기)
- Important 2: 전처리 완료 뒤 세션 갱신 실패가 저장 오류로 보이고 상태를 다시 읽음
- Important 3: 과거 버전 클러스터 결과 읽기까지 막힘
- Minor: 진입 시 1회 갱신, 학습 이중 갱신 가능, 겹친 갱신 순서 보호 없음

## 수정 1회차(7eefcf6) 재리뷰 — Approved
- 1~3 모두 처리: 갱신 실패는 무시(best-effort), 실제 내보내기 · 실행 실패는 그대로 오류. 과거 버전은 읽기 · 폴링 허용, 쓰기 · 갱신은 막음.
- 새 문제: Critical 0 · Important 0 · Minor(공통 safe-refresh 헬퍼로 정리 가능, 겹친 갱신 순서 보호 없음) → 백로그
