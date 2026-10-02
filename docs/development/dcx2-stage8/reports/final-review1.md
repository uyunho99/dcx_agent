# 묶음 ③ 최종 브랜치 리뷰 1 — `feature/dcx2-stage8` (0dcf213..763c83c)

- 범위: T1~T16 커밋 14개(백엔드 `app/persona/*` · `routers/stage8.py` · known 추천 · versions/sessions/worker, 프론트 `components/persona/*` · 경로 · 서랍). T17(② 위 rebase)은 의도적으로 보류.
- 기준: `03-plan.md`(계약 · Review Focus), `02-design.md`, `../dcx2-stage6-8/02-design.md` 5 · 9 · 10 · 14절, D-201~D-248, D-301~D-311.
- 실행: `pytest backend/tests/persona backend/tests/known backend/tests/context/test_versions_stage8.py backend/tests/context/test_session_completion.py` → 319 passed. `npm --prefix frontend test` → 57 files / 548 tests passed. (lint · build은 돌리지 않음.)

## 판정: Ready with fixes

백엔드 핵심(등급 표 D-213, 구역 · 경계 D-307, ★, targetScope 제외 D-210, 원자적 쓰기 · 판 · 되돌리기, LLM 숫자 무시 후 코드 재계산, 추천 add-only D-217/D-305, 최근 20 · 제목 중복 제거 D-309, `/insights` 리다이렉트 D-306, 옛 세션 분기 D-303)은 설계와 맞고 테스트도 실제로 검증합니다. 잠금 순서(`.insight.lock` → 세션 lock, 중첩된 `sessions.locked` 없음)에도 교착은 없습니다.
다만 아래 Critical 1건은 merge 전에 반드시 고쳐야 합니다. 화면에서 stale 상태를 빠져나올 방법이 없습니다. Important 5건도 작은 국소 수정이라 이번 묶음 안에서 고치는 것을 권합니다.

| 심각도 | 건수 |
|---|---|
| Critical | 1 |
| Important | 5 |
| Minor | 14 |

---

## Critical

### C1. stale이 된 뒤 "페르소나 만들기"를 눌러도 아무 일도 일어나지 않음(복구 경로 없음)
- 위치: `frontend/src/components/persona/PersonaScreen.tsx:121`(`api.startPersona(sid,{},version)`, `fresh`를 보내지 않음) · `backend/app/persona/pipeline.py:210`(`if not fresh and mark_stale_if_changed(...): return`) · `pipeline.py:108-122`.
- 실패 시나리오: 7단계를 다시 돌려 package `run`/hash가 바뀝니다(5.x · 계획 "7단계 결과 변경 → stale"). 상태 GET이 `persona.status = 'stale'`로 바꾸고 화면에 "근거 또는 확정값이 바뀌었습니다. 페르소나를 다시 만들어 주세요."가 뜹니다. 사용자가 주요 버튼 "페르소나 만들기"를 누르면 `POST /persona/run {}`가 갑니다. 워커는 `fresh=False`라서 `mark_stale_if_changed`가 다시 True를 돌려주고, 아무것도 만들지 않은 채 끝납니다(`test_package_changed_marks_stale`가 "두 번째 run은 LLM 0회"로 이 동작을 고정하고 있음). 상태는 계속 stale이고, 사용자가 화면에서 할 수 있는 일이 없습니다. 페르소나 화면에는 "8부터 다시" 버전 만들기 진입점도 없습니다(M13).
- 수정: (a) 프론트에서 `status.status === 'stale'`이면 `startPersona(sid, {fresh: true}, version)`을 보내고, 버튼 문구는 "다시 만들기"로 둡니다(fresh는 `persona/` 전체와 insight를 지우므로 확인 대화상자도 둡니다). (b) 또는 백엔드 `start_persona`에서 `mark_stale_if_changed`가 True이고 `_confirmed_matches`가 참이면 `fresh=True`로 승격합니다. 6단계 확정값만 바뀌어 package가 옛것이면(`_confirmed_matches` False) 409 `evidence_required`류 오류와 "근거 탐색을 다시 실행하세요" 문구를 냅니다. (c) 회귀 테스트: stale → run → 카드가 새 `package_run`으로 다시 생성됨(API · 화면 각각).

---

## Important

### I1. 패키지가 없는 세션에서 설계된 빈 상태가 처음에 보이지 않음(QA-P1)
- 위치: `PersonaScreen.tsx:61`(오류 문구에 `missingCopy`가 있는지로 판단) · `backend/app/routers/stage8.py:105-129`(`status`에 패키지 유무가 없음) · 테스트 `PersonaScreen.test.ts:31`(`h.data.missing = true`를 직접 넣어서 fetcher 경로를 검증하지 않음).
- 실패 시나리오: 7단계를 하지 않은 새 세션으로 `/pipeline/personas`에 들어갑니다. GET status는 `none`, cards · map · tree는 409 `not_ready`("아직 결과가 준비되지 않았습니다.")를 돌려주므로 `needsEvidence`는 항상 false입니다. 그래서 7절 · 9절의 "근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다. [근거 탐색으로]" 대신 일반 화면과 "페르소나 만들기"가 보이고, 버튼을 눌러야 비로소 빈 상태로 바뀝니다.
- 수정: `persona_status`에 `package: bool`(또는 `evidenceRequired: true`)을 넣고 `load_package`의 존재만 확인합니다. 프론트는 그 값으로 분기하고 문구 매칭은 없앱니다. 테스트는 fetcher가 status 응답에서 `missing`을 만드는지 검증하도록 바꿉니다.

### I2. 인사이트 · 컨셉 워커가 실패하면 화면이 6분 동안 "처리 중…"에 머물고 설계 문구가 나오지 않음
- 위치: `frontend/src/components/persona/InsightScreen.tsx:46-59`(판 번호가 오를 때까지만 폴링, 120회 × 3초) · `backend/app/routers/stage8.py:190-203`(`GET /insight`에 `session.insight.status/reason`이 없음).
- 실패 시나리오: `insight.derive`가 범위 밖을 두 번 돌려주거나(→ `InsightError`), LLM이 끊기거나(→ interrupted), 컨셉 AS-IS 검증이 실패합니다. 워커는 `insight.status = failed/interrupted`를 쓰지만 GET 응답에는 상태가 없어서, 화면은 6분 뒤 "처리 상태를 확인하지 못했습니다."를 냅니다. 9.1절의 "인사이트를 만들지 못했습니다. 다시 시도하세요."와 "이어서 진행"은 나오지 않습니다.
- 수정: `GET /insight/{sid}`에 `status: {state, reason, run}`(session.insight + 최근 `insight` 워커 상태)을 넣습니다. 프론트 폴링은 `failed`이면 문구 + [다시 시도], `interrupted`이면 [이어서 진행]으로 끝냅니다. 실패 · 중단 각 1건씩 Vitest를 추가합니다.

### I3. CCM 8-A의 "키워드" · "쓰는 제품 · 수단" 행이 항상 "근거 부족"으로 나옴
- 위치: `backend/app/persona/cards.py:192-193`(카드 Context 행에 `action · context_name · situation_origin · metrics`만 복사하고 `keywords`가 없음, Persona `artifacts`도 카드에 없음) · `PersonaScreen.tsx:111`(`context[field]`) · `CCMTable.tsx:9`.
- 실패 시나리오: 5.9절 8-A의 행은 Action / 상태 · 감정 · 장벽 / Keywords / Artifact / Satisfaction / Opportunity입니다. package에는 `context_evidence[].keywords`와 `persona_evidence.artifacts`가 있지만 카드에 옮기지 않아서, 모든 Context에서 두 행이 "근거 부족"으로 보입니다. 사용자는 근거가 없다고 오해합니다.
- 수정: `cards.py`에서 `row.update(keywords=context.keywords, ...)`, card에 `artifacts=persona.artifacts`(코드 소유, LLM 입력 아님)를 넣습니다. 화면은 artifact 행을 Persona 값(또는 Context 키워드와 겹치는 artifact)으로 채웁니다. 키워드 · artifact 행이 값을 보이는지 테스트를 추가합니다.

### I4. 실제 레지스트리 경로에서 카드 스키마 재시도가 2회가 아니라 최대 4회
- 위치: `backend/app/persona/cards.py:124`(`attempts = 1 if runner is registry.run_task else 2`) · `pipeline.py:131-141`(`_Calls.run_task`가 `registry.run_task`를 감싸므로 identity 검사가 항상 거짓).
- 실패 시나리오: 운영 워커에서는 runner가 `calls.run_task`입니다. `_call`이 2회를 시도하고 각 시도에서 레지스트리가 다시 2회를 시도해서(`registry.py:26`), 스키마가 계속 불량인 묶음 하나에 백엔드 호출이 4번 나갑니다. 5.2절 "스키마 불량 2회 → failed"와 다르고, 비용 · 지연이 두 배가 되며, stage_8 `llm_calls`(논리 호출 2)와 실제 호출 수(4)도 어긋납니다. 모듈 docstring("invoked once per logical call")과도 반대입니다. 테스트는 fake runner를 직접 주입하므로 이 경로를 보지 못합니다.
- 수정: `_Calls`에 `retries_schema = True` 표시를 두고 `_call`이 `getattr(runner, '__self__', None)`/속성으로 판단하게 하거나, 재시도 소유권을 하나로 정합니다(레지스트리에 맡기고 `_call`은 1회). 회귀 테스트: `FakeBackend`로 항상 schema 불량 → `registry` 경유 백엔드 호출이 정확히 2회.

### I5. 채팅 · 되돌리기로 인사이트가 바뀌어도 컨셉 · 확정과의 정합을 확인하지 않음
- 위치: `backend/app/persona/chat.py:62-70`(insights 수정) · `chat.py:99-115`(revert) · `insight_pipeline.py:43-44`(확정 목록 필터).
- 실패 시나리오: (a) 채팅으로 인사이트 `in_2`의 `context_ids`를 `[C1, C2]` → `[C5]`로 바꿉니다. 기존 컨셉 `in_2`의 JOURNEY AS-IS `context_id`는 이제 그 인사이트의 Context가 아닌데도(5.7 코드 검증 위반) 그대로 표시되고, 다시 만들기도 `done`이라 건너뜁니다(`insight_pipeline.py:110-113`). (b) 인사이트 ID가 바뀌거나 지워지면 컨셉이 고아가 됩니다. (c) 판 1로 되돌리면 판 2에만 있던 `in_5` 확정이 `publish_status`에서 영구히 지워지고, 판 2로 다시 돌아와도 복구되지 않습니다.
- 수정: insights 새 판을 저장할 때 각 컨셉을 검사해서, 대상 인사이트가 없거나 AS-IS `context_id`가 대상 `context_ids` 밖이면 컨셉에 `stale: true`(화면 배지 + "다시 만들기" 허용)를 붙이거나 제거합니다. 확정은 판에 묶지 말고 `confirmed`를 그대로 두되 화면에서 현재 판에 있는 것만 표시합니다(필터는 표시 계층에서). 각 경우를 테스트합니다.

---

## Minor

1. **`known_ki_id` 미검증** — `backend/app/persona/insights.py:126` · `chat.py:62-70`. LLM이 없는 ID를 주면 "Known Insight #ki_99와 같은 내용" 배지가 생깁니다. 수정: 세션 Known ID 집합에 없으면 `None`으로 바꾸거나 재생성 사유로 처리합니다.
2. **교차 종류 실행 경쟁** — `routers/stage8.py:94-101` · `178-186`. `_idle`은 lock 안에서 보지만 `runner.start`는 lock 밖이고 같은 kind만 중복을 막습니다. persona(fresh, `persona/` rmtree)와 insight가 동시에 시작될 수 있습니다. 수정: `runner.start`를 세션 lock 안으로 옮기거나, 워커 시작 시 반대 kind 실행 여부를 다시 확인합니다.
3. **채팅 · 되돌리기 · 확정이 persona 선행 조건과 stale을 확인하지 않음** — `chat.py:32-35`, `stage8.py:211-226`. stage8 stale이거나 persona fresh 재실행 중에도 insights.json에 새 판을 씁니다. 수정: `_persona_required(data)`를 재사용합니다.
4. **처음 들어온 인사이트 화면에 실패 문구가 나옴** — `InsightScreen.tsx:83`. 아직 한 번도 도출하지 않았는데 "인사이트를 만들지 못했습니다. 다시 시도하세요."가 보입니다. 수정: 실행 이력(`insight.status`)이 failed일 때만 표시하고, 처음에는 안내 문구를 둡니다.
5. **맵 구역 이름이 두 가지** — `OpportunityMap.tsx:53`('A 흥미 · B 경험 …') vs `personaView.ts:37-40`/표/aria('Exciting · Experiencing …'). 5.5절 용어(A Exciting … F At-risk)로 통일합니다.
6. **맵이 백엔드 legend · shape · tone을 무시하고 다시 계산함** — `OpportunityMap.tsx:30-31`(ID 문자열 정렬이라 `CL10`이 `CL2`보다 앞) vs `opportunity.py:61-75`(package 순서). 범례 칩도 Persona 이름 대신 ID만 보입니다. 수정: `map.legend`의 `shape/tone/persona_name/cluster_label`을 그대로 씁니다.
7. **범례 칩이 "필터"가 아니라 파란 강조만 함** — `OpportunityMap.tsx:33,44`. 5.9절은 "클릭으로 필터"(켜고 끔)입니다. 의도한 해석이면 결정 로그에 남기고, 아니면 고르지 않은 Persona의 점을 흐리게 합니다.
8. **헤더 · 8-C 표기가 설계와 다름** — `PersonaScreen.tsx:133`: "신뢰도"와 "처방 · 제약 검사 ✓ ⚠" 요약이 헤더에 없습니다. `PersonaScreen.tsx:23,139`: journey · sensitivity가 `pre_purchase: 0.3 · price: 상`처럼 영문 키로 나옵니다. 한글 라벨(구매 전 · 구매 · 구매 후 / 가격 · 브랜드 · 기능)로 바꿉니다.
9. **숫자 서식 없음** — `ContextTable.tsx:13`, `Radar.tsx:8,14`, `OpportunityBars.tsx:6-7`, 맵 aside. 0.6234567 같은 원값이 그대로 보입니다. 소수 2자리 + 백분위 정수로 맞춥니다.
10. **`insight.derive` 입력이 지나치게 큼** — `insights.py:77`. 설계 5.6은 "Context 요약(8-A 행 · pain point 인용 1~2개 · Context ID · ODI)"인데, `cards.json` 전체(실패 행 · trace의 근거 스냅샷 전부 · 처방 · scope reason)를 보냅니다. 비용과 컨텍스트 초과 위험이 있습니다. 필요한 투영만 보냅니다.
11. **컨셉 스키마가 코드 소유 필드를 "무시"가 아니라 "실패"로 처리** — `concepts.py:29-48`(`extra='forbid'`). LLM이 `basis`나 숫자를 덧붙이면 컨셉 전체가 실패합니다. 인사이트(`extra='ignore'`)와 원칙이 다릅니다. `pain_points` 중복(같은 번호 3개)도 허용합니다(`concepts.py:44,131`). 수정: extra ignore + 중복 거부.
12. **불필요한 LLM 호출** — `cards.py:175`(근거가 없는 Context만 모인 묶음도 호출), `cards.py:201-208`(refs가 0이어도 summary를 호출한 뒤 결과를 버림). 호출 전에 건너뜁니다.
13. **"8부터 다시"를 화면에서 고를 수 없음(QA-V)** — `frontend/src/components/versions/StageVersion.tsx:16`(routes가 `personas`를 index 7로 두고 stage8 선택지가 없음). ② 소유 파일이라 T17 rebase 때 정리 대상으로 표시해 둡니다(D-308).
14. **기타 소소한 것** — `insights.py:59`: `with sqlite3.connect(...)`가 연결을 닫지 않습니다(`closing` 사용). 추천 서랍(`KnownInsightsDrawer`/`known/store.py suggestions`)은 이미 추가한 항목을 다시 열면 또 보여 줘 중복 추가가 가능합니다(현재 세션 Known에 같은 텍스트가 있으면 제외). `_completion.personaDone`은 6단계 확정값 변경을 상태 GET 전까지 반영하지 않습니다(사이드바가 잠시 8로 보임). `tablist`에 화살표 키 이동이 없습니다.

---

## 확인한 항목(문제 없음)

- AC-10: Persona 이름 · Desire · Goal · Action은 package/6단계 값을 복사(`cards.py:160-161,192`). `_confirmed_matches`로 6단계 값만 바뀐 경우도 stale(Review Focus 1, 테스트 있음).
- AC-11 / D-213: `grade.py` 표 전 경우, Traceable < 0.5면 한 단계 하향, null 칸은 등급 없음, intent · persona_profile은 항상 추측. 미확인 인용 툴팁 문구가 9절과 일치.
- D-210: card · summary payload는 명시 투영이고 projectContext가 없음. extras에 sentinel을 넣은 테스트로 고정.
- AC-12: 제약 위반 → 이유를 붙여 재처방 1회 → 차단 문구(9절과 일치), review는 차단 안 함, scope는 별도 작업 이름. 구역 · 경계 D-307(선 위 정확히 → 위쪽), ★ = novelty high 이상 2건 ∧ odi ≥ 평균.
- AC-13: LLM 숫자 필드는 `extra='ignore'`로 버린 뒤 레이더(가중 평균 · midrank D-311) · 막대 · 평균선을 코드가 다시 계산. 채팅 실패 시 판 유지 + 문구 일치. 되돌리기는 새 판(by `revert`). basis 작성자 수는 author_hash 중복 제거(D-310).
- 저장: `atomic_write`(임시 파일 → replace), 판 history 스냅샷, chat.jsonl은 직렬화 후 fsync. PersonaStore는 내부에서 lock을 잡고, 호출부에서 중첩된 `sessions.locked`는 찾지 못함.
- D-305/D-217/D-309: suggestions는 같은 bk · 다른 세션 · 확정 · non-stale, 최근 20, 제목 중복 제거. `from: 'prev_session'`은 statement만 허용.
- D-303/D-306: `prep.derivedRef`로 두 경로 분기, `/insights` → `/pipeline/insights` 서버 리다이렉트, 레거시 백엔드 경로(`/persona`, `/persona-status/{sid}`)와 새 경로가 충돌하지 않음.
- 접근성: GradeMark는 모양(●▲✕) + 글자, CCM 칸은 네이티브 button + `aria-expanded/controls`, 맵은 `role=img` + 구역별 수 aria-label + 정렬 가능한 표(포커스 ↔ 점 강조, "카드 열기"), CCM 10열 2단 접기(Review Focus 2), 겹친 점은 표에 전부 + 툴팁 개수(Review Focus 5).
- API ↔ 프론트: `lib/api/persona.ts` · `insight.ts`의 경로 · 메서드 · 본문이 `routers/stage8.py`와 1:1. 타입 일부(`legend`, `bars`, tree)가 `unknown`이라 계약 변경을 컴파일러가 잡지 못하므로 M6 수정 때 좁히기를 권합니다.

## 테스트 품질 메모

- 강점: 픽스처가 구역 A~F · ★ 2 · 반례 · 미확인 인용 · 근거 0건을 실제로 만들고 테스트가 확인합니다. 통합 테스트는 소켓을 막고 실제 워커 레지스트리로 dispatch합니다. Review Focus 1~5에 대응하는 테스트가 모두 있습니다.
- 빈틈: (1) stale → 재생성 경로(C1)가 없습니다. (2) 패키지 없음 빈 상태는 fetcher 경로를 검증하지 않습니다(I1). (3) 레지스트리 경유 재시도 횟수(I4). (4) 인사이트 워커 실패 시 화면(I2). (5) 채팅 뒤 컨셉 정합(I5).
