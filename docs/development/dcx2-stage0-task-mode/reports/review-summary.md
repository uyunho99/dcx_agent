# 리뷰 기록 — dcx2-stage0-task-mode

모든 리뷰는 Claude 리뷰어(읽기 전용, 별도 컨텍스트)가 했고, 수정은 모두 Codex가 했다.

| 범위 | 리뷰 모델 | 결과 | 처리 |
|---|---|---|---|
| T1 모델 · 렌더 · API (4ec7719..c240a7c) | sonnet | Approved, Minor 5 | 원장에 보류 기록 |
| T4 폼 로직 (c240a7c..6fc04e7) | sonnet | Approved, Minor 4 | 원장에 보류 기록 |
| T5 ChoiceCards (6fc04e7..ca4d699) | sonnet | Needs fixes: Important 1(계획 계약과 props 이름 다름), Minor 2 | 계약을 실제 이름(aria-*, option.label)으로 고치는 ruling — T6이 이미 그 이름으로 작성 |
| T3 R1 프롬프트 (ca4d699..0d509ac) | sonnet | Approved, Minor 3 | 원장에 보류 기록 |
| T6 0단계 화면 (0d509ac..a87b1f2) | opus | Needs fixes: Important 1(지표 개선형 포지셔닝 접힘이 값을 지우면 저절로 닫힘), Minor 5 | Codex 수정 1회(cbe7727) → 범위 재리뷰 ADDRESSED |
| 브랜치 전체 (4ec7719..2de57e9) | opus | With fixes: Important 1(예전 임시 저장본의 선택 없는 분석 목적 + 메모 → 저장 불가), Minor 4. 보류 Minor 19건 분류: 18건 수용, 1건(예전 세션 배너 문구) 머지 전 수정 | harness retry → Codex 수정(b428144) → 범위 재리뷰 둘 다 ADDRESSED |

## 남은 Minor (수용, 머지 막지 않음)
- 서버 직접 호출로만 생기는 값: 지표 출처 · 문항 공백, 페르소나 글자 줄바꿈, 빈 이름 지표 거부(설계 2.2는 "세지 않음")
- 화면 편의: Home/End 키가 이미 고른 칩을 해제, 빈 "+ 직접 입력" 상자 닫기 없음, 중복 페르소나 추가 시 안내 없음, 과제 유형 전환 시 입력 중인 직접 입력 글자 사라짐
- 예전 세션을 R1 뒤 다시 저장하면 R1 뒤 변경 배너도 함께 뜸(과제 유형 · 페르소나 섹션이 새로 생기므로 사실과 맞음)
- 테스트 스타일: 픽스처 교차 import, 문구 하드코딩, 빈 줄
- 기존 경고: PydanticDeprecatedSince20, Node DEP0205

원본 판정 · 처리 이력: `reports/sdd-ledger.md`, Task 보고서 `reports/task-T*-report.md`, `reports/final-fix-report.md`.
