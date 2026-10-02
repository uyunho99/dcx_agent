# 02 · 설계 — 묶음 ③ 8단계 페르소나 · 인사이트 · 컨셉

- 기준(승인됨): [`../dcx2-stage6-8/02-design.md`](../dcx2-stage6-8/02-design.md) **5절 전체** · 2.4(읽기) · 2.5 · 6 · 7 · 8 · 9 · 10(화면 8) · 11(8) · 14절 디자인 리뷰(D-222 · D-225 · D-226 · D-227) · 목업 s5 · s6 · s7. 이 문서는 그 설계를 바꾸지 않고 (1) 묶음 ① 구현 규칙 (2) 01의 판단 D-301~304 (3) 설계가 비워 둔 부분만 정한다.
- 결정: [`decision-log.md`](decision-log.md) D-301~.

## 1. 묶음 ①에서 이어받는 규칙

| 항목 | 8단계 적용 |
|---|---|
| 워커 | KINDS에 `persona`(Persona 단위 체크포인트, args `{'fresh': bool, 'personas': [id] \| None}`) · `insight`(args `{'mode': 'derive' \| 'concept', 'target': id \| None}`) |
| 실행 세대 | `persona.run` · `insight.revision`. 7단계를 다시 돌리면 `persona/` 결과 stale(`{status: 'stale'}`), 오래된 화면 저장 409 `stale_run` |
| 저장 | JSON 파일(설계 2.5) — 원자적 쓰기(임시 파일 → rename), 판(revision) 단위 |
| LLM | 작업 `persona.card` · `persona.summary` · `persona.prescribe` · `persona.constraint_check` · `persona.scope` · `insight.derive` · `insight.concept` · `insight.edit`, 가짜 응답 `tests/fixtures/llm/{task}.json`, 전부 backend/timeout 실패면 `interrupted` |
| 완료 표시 | 서버 `completion.personaDone`(카드 생성 완료 ∧ stage8 not stale) → 8, `completion.insightDone`(8-E 생성 완료) → 인사이트 단계 |
| 버전 | 8부터 다시: `persona/`만 삭제(설계 6절), 6 · 7부터 다시에서도 삭제 — versions.py 확장 + 테스트 |
| 옛 세션(D-303) | `/pipeline/personas` · `/pipeline/insights`(기존 `/insights`는 새 경로로 이동) 모두 클러스터링 화면과 같은 분기: `prep.derivedRef` 있으면 새 화면, 없으면 기존 화면 그대로 |

## 2. 입력: Evidence Package 읽기 (D-301)

- `app/persona/package.py`: 2.4 스키마의 **읽기 검증 모델**(Pydantic, 알 수 없는 키 허용 · 필수 키만 검사) + `load_package(sid, version) -> Package`.
- `tests/fixtures/evidence_package.py`: 합성 세션 기준 가짜 패키지 생성기(D-304) — Persona 4 · Context 11, Context마다 I · S가 달라 구역 A~F가 모두 한 번 이상, ★ 조건(novelty high 이상 2건 ∧ odi ≥ 평균) 2곳, 반례 Context 1, 인용 `verified: false` 섞음, 근거 0건 Context 1.
- ② 합류 시: ③ 브랜치를 ② 위로 rebase → `load_package`가 ②의 생성 모델로 검증하도록 바꾸고, ② 실제 출력 ↔ 픽스처 키 대조 테스트를 추가(계획의 마지막 Task로 둠, ② 미완이면 보류).

## 3. 카드 생성 분할 (D-302)

- `persona.card`를 Context 최대 4개 묶음마다 1회 호출 → 8-A(state · emotion · barrier, cite) 칸만 받는다. 근거 번호 `E1…`은 묶음 안에서만 유효, 코드가 Persona 전체 번호로 다시 매김.
- `persona.summary` 1회: 8-A 결과 요약 + Persona 근거 → 8-B intent · 8-C 속성(usage_context · jtbd · journey · sensitivity · values · decision_style).
- 실패: 한 묶음이 스키마 불량 2회면 그 Persona 카드 `failed`(설계 5.2 그대로, 부분 카드 저장 안 함).

## 4. 인식론 등급 · 계산 (설계 5.3 · 5.5 · 5.6 그대로, 순수 함수)

- `app/persona/grade.py`: `grade(field, cites, evidence_by_id) -> 'observed' | 'inferred' | 'speculated'` + Traceable Support 하향. 표 전 경우를 매개변수 테스트로.
- `app/persona/opportunity.py`: 기준선 · 구역 A~F · ★ 마커. 경계값(선 위 정확히)은 위쪽 구역에 넣는다(테스트로 고정).
- 레이더 축 문장 3개는 `app/persona/params.py`, 축 문장 임베딩은 세션 임베더(`input_type='query'` 인자가 ②에 있으면 사용, 없으면 기본).

## 5. 인사이트 확정 → 다음 세션 추천 (D-217, D-305)

- 기존 `known.store.initialize`는 같은 제품명 이전 세션의 **Known Insight 문장을 자동으로 복사**한다(prev_session). 확정 인사이트는 여기에 넣지 않는다(D-217: 추천만).
- 새 API `GET /known/{sid}/suggestions`: 같은 `bk` 다른 세션의 `insight.confirmed` 인사이트 제목 · pain point 목록. 서랍(`KnownInsightsDrawer`)에 접힌 "이전 세션 추천" 구역 → [추가]를 눌러야 `origin: prev_session`으로 저장.

## 6. 저장 (설계 2.5 + 빈 부분)

`versions/vN/persona/`: `cards.json`(`{run, personas: {id: {status, card, grades, trace, prescription, constraint, scope}}}`) · `map.json` · `tree.json` · `insights.json` · `concepts.json`(`{revision, items, history}`) · `chat.jsonl` · `stage_8.json`. 판 되돌리기는 `history`의 판을 새 판으로 복사(덮어쓰기 아님).

## 7. 화면 (설계 5.9 그대로)

- `/pipeline/personas`: `[전체 맵 | Persona 카드]`, 왼쪽 Persona 목록(D-227), 맵 아래 Context 표(D-226), 점 모양 · 명도(D-225).
- CCM 표: Context 5개 이상이면 2단 접기(설계 10절), 열 머리에 Context ID · 이름 · 반례 표시.
- `/pipeline/insights`: 인사이트 카드 · Opportunity 막대 · 8-F · 채팅 · 판 목록. 기존 `/insights`는 `/pipeline/insights`로 바꾸고, 옛 세션도 그 경로에서 기존 화면.
- 7단계 결과가 없을 때: "근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다." + [근거 탐색으로] (버튼 하나).

## 8. 디자인 리뷰

화면 8 · 인사이트는 묶음 ① 설계 디자인 리뷰(14절, 결정 1A · 4A · 5A · 6A = D-222 · D-225 · D-226 · D-227, 목업 s5 · s6 · s7)에서 검토 · 승인됐다. 이 문서의 새 UI는 서랍의 "이전 세션 추천" 접힘 구역(기존 서랍 목록 행 재사용)과 7절 빈 상태 문구뿐이다.

## 9. 테스트 추가분 (설계 11절 8단계 + 이 문서)

- 카드 분할: Context 10개 Persona → card 3회 + summary 1회, 근거 번호 재매김 후 cite가 원래 근거를 가리킴.
- 픽스처: 구역 A~F · ★ 2곳 · 반례 · 미확인 인용 → 🟡 하향 · 근거 0건 Context → 칸 null.
- 추천: 확정 인사이트가 다음 세션 Known Insight에 자동으로 들어가지 않고 suggestions에만 보임.
- 옛 세션: `prep.derivedRef` 없는 세션은 두 경로 모두 기존 화면.
