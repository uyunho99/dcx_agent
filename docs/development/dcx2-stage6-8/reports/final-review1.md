# 묶음 ① 최종 브랜치 리뷰 (Claude opus, 2026-10-02)

- 범위: 9c1e3d7..5981e30 (21 commits), 리뷰 패키지 `.superpowers/sdd/03-plan/review-9c1e3d7..5981e30.diff`
- 판정: **Ready with fixes** — Critical 0, Important 7, Minor 6 (+ 원장 deferred minor 분류)

## Important (모두 54435cf에서 수정, 재리뷰 opus: all addressed)
1. 확정 후 임시저장 편집값이 deep_merge로 남아 새로고침 시 확정 상태가 숨겨짐 → 확정 id는 null 저장, 복원 시 제거
2. 실행 실패 시 예외 클래스 이름 노출 → StoreError 한국어 사유를 segment.reason으로, 그 밖은 일반 한국어 문구
3. QA 데이터로 dims · 반례 · 과다 경고를 확인할 수 없음 → segment.dims 에코 가짜 응답, 5개 이상 Context Persona, 부정 KNU 어휘 소수 Context
4. "초안 힌트: 0단계 대상 선언" 미전달 → GET personas가 targetScope로 hint 제공
5. 100만 건 입력 적재 메모리 → 관련 문서만 샤드 스트리밍, input.json 축소, 재개 시 재구성
6. 긴 단계 진행률 정체 → Persona i/N · 문서 i/N 세부 진행, 명사 캐시 단계 pulse/stop
7. LLM 장애 시 전체 재분할 외 재시도 없음 → 단계 내 LLM 호출 전부 실패 시 interrupted + 한국어 사유, "이어서 진행"으로 L1~L3 재계산 없이 재개

## 병합 전 수정한 Minor
- export `_label_entropy` NULL votes 방어 · dims 프롬프트 분석 용어 제거 + 본문 2,000자 · 댓글 300자×10 상한 · 대표 원문 300자 상한 + 초안 프롬프트 쉬운 표현 · segment.sqlite WAL + 스키마 DDL 1회

## 보류(원장 기록)
- 서버측 stale-run 임시저장 거부 · 읽기 전용 버전의 paused segment 워커 정지 · 요청 메모 run 확인 · stale 배너 문구 · 불용어 목록(UAT 전 사용자 결정 항목) 외 원장 `sdd-ledger.md`의 deferred minor

## 재리뷰 잔여(낮음)
- `_SelectedVectors.get` 행마다 stat 호출(속도) · 일부 영어 StoreError 메시지가 사유로 노출될 수 있음
