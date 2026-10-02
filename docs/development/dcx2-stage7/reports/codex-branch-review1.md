# Codex 읽기 전용 브랜치 리뷰 — 묶음 ② (69dcf91..a92f2f3)

Critical 0 · Important 7 · Minor 2 (Codex 샌드박스가 읽기 전용이라 응답 본문을 controller가 저장)

1. Important — backend/app/evidence/assemble.py:305 — 완료 Context refresh와 다른 Context 완료 발행이 겹치면 refresh의 오래된 `running` 스냅샷이 done 상태 · 수치를 덮어씀(발행이 refresh의 세션 잠금을 안 씀) → 재시도 · 건너뛰기 없는 partial — 발행과 refresh를 같은 잠금 + 세대 검사로 직렬화, assembly 소유 필드만 갱신.
2. Important — backend/app/evidence/pipeline.py:155 — evidence 실행 중 6단계 재시작 가능(launch guard가 segment만 봄) → stale 표시 뒤 옛 worker가 새 segment 배정에 옛 선택을 조립해 done으로 덮어씀 — 충돌 worker 동시 시작 원자적 차단, 시작 시 segment 세대를 잡아 바뀌면 발행 거부.
3. Important — backend/app/evidence/pipeline.py:126 — Context 완료 뒤 추가된 문장형 Known Insight가 그 Context 캐시 문서와 판정되지 않음(refresh가 기존 쌍만 투영, knownChanged=False로 확인 처리) — 빠진 (문서, 문장) 판정을 예약하고 끝날 때까지 변경 표시 유지, LLM 0회 refresh는 넘긴 원문 변경에만.
4. Important — backend/app/evidence/tagging.py:229 — Known Insight 문장을 수정해도 ID가 같아 (doc_id, ki_id) 캐시가 옛 문장 판정을 재사용, 변경 표시 없음 — 캐시 키 · 스냅샷에 Known Insight 내용 지문(또는 판)을 넣고 바뀐 쌍 재판정.
5. Important — backend/app/routers/evidence.py:126 — 제목 · 댓글 인용 위치는 그 필드 기준인데 API가 본문 텍스트를 내려 카드가 본문에 그 위치를 칠함(댓글 인용 0–6이 본문 'unrela'를 강조) — 인용된 필드 · 댓글 텍스트와 위치를 짝으로 내리거나 인용을 따로 표시.
6. Important — backend/app/evidence/assemble.py:255 — tag.v1.md를 바꾸면 기존 실행이 새(빈) 태그 캐시를 읽음 → 이어 하기에서 완료 Context 근거가 사라진 채 패키지 덮어씀 · done 유지, refresh도 새 발견 탭을 비울 수 있음 — 생성마다 prep · 프롬프트 참조를 저장해 기존 결과 읽기에 사용, 프롬프트 업그레이드 시 해당 체크포인트 무효화.
7. Important — backend/app/evidence/candidates.py:15 — Voyage 예외가 0 질의 벡터가 되어 "결과 없음"으로 조용히 처리 → 빈 근거로 완료 체크포인트, 이어 하기가 건너뜀 — 질의 임베딩 노름 · 완전성 검사, 실패는 재시도 가능/중단으로.
8. Minor — frontend/src/app/pipeline/labeling/page.tsx:53 — 배너가 `stage7.irrelevant`를 읽지만 백엔드는 `relevant_false` → 배너가 절대 안 뜸 — 필드 이름 통일 + 실제 응답 모양으로 테스트.
9. Minor — frontend/src/components/evidence/EvidenceCard.tsx:21 — novelty 배지가 'none' 포함 모든 값에 표시(설계는 high · very_high만) — 백엔드 표시 플래그를 API로 내리고 카드에서 사용.
