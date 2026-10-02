# 01 · 기획 — DCX 2.0 묶음 ② 7단계 근거 탐색 (RAG)

- 기준 문서(승인됨): [`../dcx2-stage6-8/01-brainstorm.md`](../dcx2-stage6-8/01-brainstorm.md) · [`../dcx2-stage6-8/02-design.md`](../dcx2-stage6-8/02-design.md) 4절 · 결정 원장 [`../dcx2-stage6-8/decision-log.md`](../dcx2-stage6-8/decision-log.md) D-201~D-244
- 실행 분리: D-228(묶음마다 별도 하네스 실행). 이 문서는 묶음 ②의 범위와, 묶음 ① 이후 새로 생긴 쟁점만 적는다.
- 출발점: `feature/dcx2-stage6-8`(묶음 ① UAT 승인, 4ff1a64) 위에 `plan/dcx2-stage7` 브랜치.

## 1. 문제와 목표

6단계에서 사람이 확정한 Persona · Context마다, 그 주장을 받치는 실제 원문(근거)을 찾아 보여 주고 8단계로 넘길 Evidence Package를 만든다. 연구자는 Context마다 "전체 10건 / 새 발견 10건"을 보고, 이미 아는 얘기는 Known Insight로 넘겨 새 발견만 남긴다.

## 2. 범위 (02-design 12절 묶음 ②)

- 2.3 지연 태깅 캐시(`tag-{pver}.sqlite`) · 2.4 Evidence Package
- 4.1 쿼리 생성 · 코드 검증 → 4.2 Context 필터 검색 → 4.3 지연 태깅 · 인용 위치 → 4.4 quality × DPP 리랭킹 · Coverage 보충 · rare fallback → 4.5 전체 / 새 발견 탭 · Known Insight 추가 후 재계산 → 4.6 novelty → 4.7 반례 · 희소 · 미분화 후보 · 지표 · 패키지 조립 → 4.8 `stage_7.json`
- 7절 `evidence` 워커(Context 단위 이어 하기) · 8절 evidence API · 10절 화면 7(`/pipeline/evidence`, 실행 중 완료 행 열람 D-223) · 11절 7단계 테스트
- 불용어(D-246): 6단계 L2 어휘 네트워크 · L3 Context 키워드 · 7단계 쿼리 키워드 · Artifact 후보에서 기본 불용어 약 100개 + 제품명 제외(params 한곳)
- 곁가지: 6-C "새 Context 후보" 표시(4.7), 라벨링 화면 "7단계에서 무관 판정 N건" 배너(4.3), 사이드바 7단계 완료 표시

## 3. 수용 기준 (01 그대로)

AC-06 · AC-07 · AC-08 · AC-09 · AC-14.

## 4. 제외 범위

8단계(묶음 ③), 로컬 Re-ranker(01 6절), 자동 4단계 재판정.

## 5. 묶음 ① 이후 새로 생긴 쟁점

| # | 쟁점 | 근거 | 상태 |
|---|---|---|---|
| Q1 | 제품명이 dims "환경"으로 뽑힘 → 7단계 `situation.state`(환경 + 과업 목표 매핑)에 "LG 에어컨"이 상황으로 들어감 | QA-L1: 환경 코드 `LG 에어컨` 130건 | 그대로 둠(D-245) |
| Q2 | 불용어 목록(묶음 ① UAT 미결) — 6-B 어휘가 7단계 Artifact 후보 · 쿼리 키워드로 그대로 쓰임 | D-244 | 기본 불용어 목록 넣기(D-246) — 이 묶음 Task |
| Q3 | 묶음 ①은 합성 데이터로만 확인 — Persona 초안 유사성 · 근거 품질은 실데이터에서만 판단 가능 | D-241 · D-244 | ②③은 합성 + 실제 LLM 맛보기, ③ 뒤 실세션 0→8(D-247) |
| Q4 | 7단계 실행 시간: QA-L1 속도(호출당 약 15초)로 합성 세션(Context 34개)을 순서대로 돌리면 태깅 · novelty만 약 300회 ≈ 75분 | D-241 | Claude 판단: LLM 동시 호출 4개(설정값) → 약 20분 |
| Q5 | 묶음 ③(8단계)을 가짜 Evidence Package로 ②와 병행할지 | D-228 | 병행(D-248), 실행 `dcx2-stage8` |

## 6. 위험

- 지연 태깅이 대부분의 비용 · 시간 — 캐시(버전 밖) · Context 단위 체크포인트 · 동시 호출로 줄인다.
- 인용 위치 매칭 실패율이 높으면 8단계 등급이 대거 하향 — `stage_7.json`에 미확인 비율 기록, QA에서 확인.
- Context가 많은 Persona(D-235, 최대 10개)에서 호출 수가 선형 증가 — 진행 표시 · 이어 하기로 감당(D-235에서 이미 수용).

## 7. 결정 기록

사용자 답은 decision-log(`../dcx2-stage6-8/decision-log.md`에 이어서 D-245~)에 남긴다.
