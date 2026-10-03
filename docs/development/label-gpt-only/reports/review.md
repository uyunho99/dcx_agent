# 리뷰 1차 (Codex 읽기 전용 + Claude, 2026-10-03)

범위: `git diff 271c067..86ead3a`

## 발견
- R1 High `backend/app/label/route.py:84` — 시작 전 개요 동기화가 교차 방식으로 GPT 커서를 전진시킨 뒤(최종 행 없음) GPT 단독으로 바뀌면, GPT 단독 합치기가 그 커서를 재사용해 이미 완료된 GPT 표를 다시 보지 않는다 → 최종 라벨 누락. 재현: GPT done 1건, cross sync → gpt_only sync → final 0행.
- R2 High `backend/app/label/route.py:88` — 비활성 Jev 체크포인트가 route_sync에 남아, 규칙/질문 버전 변경 뒤 `changed` 판정이 매 동기화마다 참이 되어 GPT 단독 행을 반복 삭제한다. 재현: 규칙 변경 후 1차 sync 1행 생성, 2차 sync 삭제 후 0행.
- R3 Low `frontend/src/components/label/labelerMode.ts:12` — Jev 미연결 상태에서 시작 전 "분류 모델" 방식을 고르면 GPT 단독 안내가 그대로 보인다(모델 방식과 무관).

## 이상 없음
nullable confidence 이전(트랜잭션 · 트리거 재생성), 4단계 완료 · 복구, 버전 복사 시 방식 재계산, confidence/source/votes 소비처 null 처리, 교차 방식 화면.

## 2차 (수정 c3ed4c0 확인, Claude)
- R1: gpt_only 후보를 "완료된 GPT 표 중 최종 행 없음" 전체 anti-join으로 변경 — 이전 커서와 무관. 재현 테스트 추가 확인.
- R2: `changed`를 현재 방식의 활성 캐시 체크포인트로만 판정. 재현 테스트 추가 확인.
- R3: 안내 · Jev 필터를 LLM 방식일 때만 적용(시작 전은 화면에서 고른 방식). 테스트 추가 확인.
- 남은 발견 없음.
