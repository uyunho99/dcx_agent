# 목업 — DCX STEP 07~11

## 위치

목업 소스는 제품 소스와 분리해 `docs/development/dcx-step07-11/mockup/`에 있다. Design 캔버스 아티팩트의 게시 루트가 그곳이라 이동하지 않았다.

- **아티팩트** https://claude.ai/artifact/8mb7VfY8ZyX2s7w8xpbJTK — 페이지 `Person A` (15 아트보드)
- **소스** `docs/development/dcx-step07-11/mockup/parts/*.body.html` (내용) + `docs/development/dcx-step07-11/mockup/_shell.css` (Person A 토큰)
- **빌드** `cd docs/development/dcx-step07-11/mockup && node build.mjs && node preview.mjs`

## 화면 15개

| 파일 | 화면 | 이번 범위 |
|---|---|---|
| `Main` | 00 세션 | 참조 |
| `Declare` | 01·02 입력 선언 | **수정** — `known_insights` 입력 신설 |
| `Keywords` | 03 키워드 설계 | 참조 |
| `Crawling` | 04 데이터 수집 | **수정** — doc_id · author_hash |
| `Preprocess` | 05 전처리 · 임베딩 | **수정** — Pinecone 메타 확장 |
| `Training` | 06-A 모델 학습 · 캘리브레이션 | **수정** — alpha · run 사이드카 |
| `Labeling` | 06-B 근거 판정 | **수정** — decision · label |
| `Clustering` | 07 군집 → Touch Point | **신규 구현** |
| `Persona` | 08 SNA → 페르소나 | **신규 구현** |
| `Evidence` | 09 LDA → 근거 수집 | **신규 구현** |
| `ContextMap` | 10-A Customer Action Map | **신규 구현** |
| `Opportunity` | 10-B 기회 영역 | **신규 구현** |
| `Concept` | 11-A 인사이트 도출 | **신규 구현** |
| `Design` | 11-B 경험 디자인 컨셉 | **신규 구현** |
| `Admin` | 프롬프트 · 파이프라인 상수 | **신규 구현** |

`Liquid Glass (이전안)` 페이지는 동결 상태다. Person A 시스템(Light 단일 테마 · 정적 카드 그림자 금지)과 충돌해 갱신을 멈췄고, 기록으로만 남겼다.

## 읽는 법

각 화면 아래 `1.0 대비 변경점` 스트립의 번호가 화면 안의 동그란 핀과 짝을 이룬다.
`치환` AS-IS가 있고 대체된다 · `신설` AS-IS 없음 · `유지` 기존 확정 재확인 · `미결` 답이 필요한 것

## 상태

정적 아트보드다. **인터랙션은 별도 세션에서 부여한다** (클릭·입력·단계 전환).
