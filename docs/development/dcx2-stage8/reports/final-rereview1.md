# 묶음 ③ 최종 수정 재리뷰 1 — `feature/dcx2-stage8` (763c83c..7ce3215)

- 범위: 최종 수정 커밋 `7ce3215`만. 기준은 `final-review1.md`(opus: C1, I1~I5, Minor 14건), `codex-branch-review1.md`(Codex: Important 7건, Minor 2건), 결정 D-312~D-316, 수정 보고서 2개입니다.
- 실행(읽기 전용): `pytest backend/tests/persona backend/tests/known -q` → **312 passed**. `npm --prefix frontend test` → **58 files / 567 tests passed**.
- 방식: 코드 읽기와 테스트만 했습니다. 소스는 고치지 않았고, 이 파일만 썼습니다.

## 판정: Not ready — 새 Critical 1건, 새 Important 3건

| 구분 | 건수 |
|---|---|
| 반영됨 | 21 |
| 일부 반영 | 4 |
| 반영 안 됨 | 2 |
| 결정에 따라 보류(D-316) | 2 |
| **새 결함** | Critical 1 · Important 3 · Minor 6 |

잠금 순서는 다시 확인했고 교착은 없습니다. 아래 "잠금 검토"를 보세요. 다만 I1을 프론트에서 고친 방식 때문에, 새 세션에서 8단계를 시작할 수 없게 되었습니다(N1).

---

## 새 결함

### N1 (Critical). 패키지가 있는 새 세션의 페르소나 화면이 "근거 탐색을 마친 뒤…" 빈 상태로 막혀 생성 버튼이 없음
- 위치: `frontend/src/components/persona/PersonaScreen.tsx:64`, `:122`. 백엔드 `backend/app/routers/stage8.py:83-87`(`_ready` → 카드가 없으면 409 `not_ready`), `:138`(`package` 플래그를 보내지만 프론트가 읽지 않음). `frontend/src/lib/types.ts:240`의 `PersonaStatus`에는 `package` 필드가 없습니다.
- 시나리오: 7단계를 마쳐서 `evidence/package.json`이 있습니다. 페르소나를 한 번도 실행하지 않았으므로 `GET /persona/{sid}/status`는 `status:'none'`을, `GET /cards`는 409 `not_ready`를 돌려줍니다. 이때 `missingEvidence`가 `needsEvidence(not_ready) && ['none','idle'].includes('none')`로 true가 되고, 화면은 122행에서 바로 빈 상태로 돌아갑니다. "페르소나 만들기" 버튼이 없어서 사용자는 이 화면에서 8단계를 시작할 수 없습니다. 이전 코드(문구 매칭)에서는 `not_ready` 문구가 `missingCopy`와 달라 이렇게 되지 않았으므로, 이번 수정에서 생긴 회귀입니다.
- 테스트가 이 회귀를 고정하고 있습니다: `PersonaScreen.test.ts:44` `it.each(['evidence_required','not_ready'])`. `not_ready` + `status:'none'`에서 빈 상태를 기대하는데, 이 조합이 바로 "패키지는 있고 카드만 없는" 상태입니다.
- 수정: 백엔드가 이미 내보내는 `status.package`(D-312 범위 밖이지만 I1 백엔드 수정에 이미 있음)를 `PersonaStatus` 타입에 넣고, `missing = status.package === false || cause.kind === 'evidence_required'`로 판단합니다. `not_ready`는 빈 상태로 보지 않습니다. 테스트 44행의 `not_ready` 경우는 "생성 버튼이 보인다"로 뒤집고, `package:false` 경우를 추가합니다.

### N2 (Important). `responseError`가 `kind`를 `code`보다 먼저 봐서 crawl 등 다른 화면의 오류 문구가 일반 문구로 바뀜
- 위치: `frontend/src/lib/api/errors.ts:28`(`data.error?.kind ?? data.error?.code`). 이 함수는 공용 `contextRequest`(`frontend/src/lib/api/context.ts:7`)를 거쳐 모든 v2 클라이언트(crawl · segment · label · prep · known …)가 씁니다.
- 시나리오: `backend/app/routers/crawl_v2.py:45`는 `{kind: exc.kind ('conflict'·'validation'·'storage'), code: 'no_paused_detail'·'other_channels_unfinished'·'invalid_request'·'storage_error'…, message: 영문}`을 돌려줍니다. 이제는 `kind`('conflict')가 먼저 선택되는데 `messages`에 이 키가 없습니다. 그래서 영문 message로 넘어가고, 한글이 없으니 "요청에 실패했습니다. 다시 시도하세요."가 나옵니다. 예를 들어 "차단 또는 파싱 오류로 멈춘 상세 수집 채널이 없습니다." 같은 1~2단계 안내 문구가 사라집니다. `errors.test.ts`는 `code`만 넣고 `kind`는 넣지 않아서 이 회귀를 잡지 못합니다.
- 수정: `code`가 `messages`에 있으면 그것을 먼저 쓰고, 없을 때만 `kind`로 찾습니다(예: `[code, kind].find(k => Object.hasOwn(messages, k))`). `{kind:'conflict', code:'no_paused_detail'}` 회귀 테스트를 추가합니다.

### N3 (Important). D-312 `worker.reason`에 사람이 읽을 문구 대신 예외 클래스 이름이 실림
- 위치: `backend/app/routers/stage8.py:264`(`reason = work.get('error') or …`, 감독자 값이 우선) · `backend/app/work/worker.py:139`(`error = type(exc).__name__`) · 프론트 `InsightScreen.tsx:87`(`{worker.reason && <p>{worker.reason}</p>}`를 그대로 표시).
- 시나리오: `insight.derive`가 범위 밖 결과를 두 번 돌려주면 파이프라인은 `reason=FAILURE_COPY`(한글)를 기록합니다. 그런데 감독자 행의 `error`는 `'InsightError'`이고 이 값이 우선이라서, 화면에 "인사이트를 만들지 못했습니다." 아래에 `InsightError`가 보입니다. LLM 연결이 끊긴 경우(interrupted)에는 설계 문구 `LLM_REASON` 대신 `_Unavailable`이 보입니다. 파이프라인 쪽 reason도 `str(exc)`라서 `'Persona source changed'`, `'Preparation embedding dimension …'`, `'insight.concept: backend failed'` 같은 내부 영문 문자열이 노출됩니다. 테스트 `test_worker_contract_uses_durable_supervisor`(`test_final_fixes.py:350`)는 가짜 `'durable failure'` 문자열을 넣어서 실제 형식을 보지 못합니다.
- 수정: 같은 run이면 파이프라인의 한글 `reason`을 우선합니다. 감독자 `error`는 클래스 이름이므로 표시하지 말고, failed/interrupted 기본 문구로 바꿉니다. 파이프라인은 `str(exc)` 대신 한글 사유표(LLM_REASON · FAILURE_COPY · stale 문구)에서 고릅니다.

### N4 (Important). 인사이트 하나를 고쳐도 거의 모든 컨셉이 `outdated`가 됨(D-313보다 넓음)
- 위치: `backend/app/persona/store.py:101`(`old.get(key) != active[key]`, 행 전체 비교) · `:125`(읽을 때 같은 전체 비교) · `backend/app/persona/insights.py` `recompute`(레이더 `percentile`은 세션 내 midrank, `opportunity_mean` · `default_target`은 모든 항목에 걸친 값).
- 시나리오: 채팅으로 `I1`의 `context_ids`만 바꿉니다. `recompute`가 모든 항목의 백분위 · 평균 · 기본 대상을 다시 계산하므로 `I2`, `I3` 행도 바뀌고, 이 인사이트들의 컨셉도 `outdated: true`가 됩니다. 8-F가 숨겨지고 "컨셉 다시 만들기"가 뜹니다. D-313은 "그 인사이트의 컨셉"만 무효화하라고 했습니다. 컨셉마다 다시 LLM을 호출해야 하므로 비용이 들고, 사용자는 바꾸지 않은 컨셉을 잃은 것처럼 보게 됩니다.
- 수정: 비교 대상을 컨셉이 실제로 기대는 원천 필드(`id`, `title` · 본문 텍스트, `context_ids`)로 좁힙니다. 계산 필드(radar · odi · opportunity_mean · default_target · known_badge)는 비교에서 뺍니다. 회귀 테스트: I1의 context_ids를 바꾸면 I1 컨셉만 outdated, I2 컨셉은 그대로.

### Minor (새 결함)
- **N5 확정 클릭이 숨은 확정 ID를 지움.** `InsightScreen.tsx:97`은 화면에 보이는(현재 판으로 필터된) `confirmed`로 `PUT /confirm`을 보냅니다. 그런데 `insights.confirm`(`insights.py` confirm)은 `confirmed_ids`를 그 목록으로 통째로 바꿉니다. 그래서 판 1로 되돌린 뒤 무엇이든 확정을 한 번 누르면, 판 2에만 있던 확정은 판 2로 돌아와도 복구되지 않습니다(I5(c)가 남음). 수정: 서버에서 `confirmed_ids = (기존 − 현재 판 ID) ∪ 새 ids`로 합칩니다.
- **N6 `displayValue`의 숫자 규칙.** `personaView.ts:53`은 0~1이면 소수 2자리, 그 밖이면 정수로 반올림합니다. ODI처럼 1을 넘는 지표(`record(context.metrics).odi` 대체값, 처방 `target_metric`의 숫자 등)는 `1.37 → 1`로 뭉개지고, 같은 값이 맵에서는 `formatMetric`으로 `1.37`이 되어 서로 어긋납니다. 수정: 지표 필드는 항상 `formatMetric`을 쓰고, 정수 반올림은 개수 필드에만 적용합니다.
- **N7 페르소나 실행 중 채팅 · 되돌리기 요청이 몇 분 동안 멈춤.** 이제 `pipeline.run`(`pipeline.py:215`)은 non-fresh 카드 재시도에서도 `.insight.lock`을 잡고 끝까지 놓지 않습니다. `chat.edit`/`revert`(`chat.py:34`, `:107`)는 상태를 확인하기 전에 이 잠금을 기다리므로, HTTP 스레드가 실행이 끝날 때까지 막혀 있다가 409 `persona_required`를 받습니다. 교착은 아니지만 응답이 없어 보입니다. 수정: `serialized` 전에 `require_persona`로 빠르게 409를 주거나, `LOCK_NB`를 시도하고 실패하면 409 `locked`를 줍니다.
- **N8 GET `/session`이 500을 낼 수 있음.** `routers/sessions.py:68`은 `load_package`를 감싸지 않습니다. 카드는 있는데 패키지가 없으면 `PackageMissing`(FileNotFoundError → OSError)가 500 "저장소 작업에 실패했습니다"가 됩니다. 버전 생성은 둘을 함께 지우므로 드물지만, 7단계를 다시 돌릴 때 패키지를 지우고 다시 쓰는 구현이라면 사이드바 폴링이 깨집니다. `PackageMissing`이면 False를 돌려주게 합니다. 또 인사이트 화면 폴링(3초)마다 `getVersionSession`이 `_completion`을 부르고, `_completion`이 package 전체 직렬화 · sha256과 segment.sqlite 읽기를 합니다. 비용이 작지 않습니다.
- **N9 persona fresh 재생성 뒤 인사이트 화면에 옛 실행 상태가 보임.** fresh는 `session.insight`를 지우지만 감독자 DB에는 그 버전의 마지막 insight run이 남아 있습니다. `_insight_worker`(`stage8.py:250-271`)가 이 run의 `failed`/`done`을 그대로 보고하므로, 새 카드로 처음 들어간 인사이트 화면에 옛 실패 배너가 뜰 수 있습니다. 다시 시도하면 회복되지만, `insight.run`이 비어 있으면 감독자 상태를 쓰지 않는 편이 맞습니다. 같은 이유로, 실패한 run 뒤에 채팅이 성공해도 배너가 계속 `failed`로 남습니다.
- **N10 `Source(...)`를 run의 try 밖에서 만듦.** `insight_pipeline.py:71`. 실행 대기 중에 upstream이 바뀌면 `Source` 생성자가 409를 던지는데, 이때 `publish_status('failed')`를 거치지 않습니다. 화면은 감독자의 `StoreError` 클래스 이름만 봅니다(N3와 겹침).

---

## 잠금 검토(교착 · 재진입) — 문제 없음

- `sessions.locked`와 `serialized`는 둘 다 파일별 `fcntl.flock`입니다. 같은 프로세스에서 중첩하면 스스로 막히므로(재진입 불가) 모든 중첩 경로를 따라갔습니다.
- `PersonaStore.new_revision`/`revert`/`write`/`write_aux`/`append_chat`: 세션 lock 안에서 `assert_writable`(읽기만), `guard` = `Source.check`(`assert_writable` · `load_package` · `_confirmed_matches`(ro sqlite), lock 없음), `_check_concept_sources`/`_invalidate_concepts`(read · `write_json`, lock 없음)를 부릅니다. 중첩된 `locked`는 없습니다.
- `publish_status`: lock 안에서 `before_publish`(읽기만)와 `PersonaStore.read`를 부르고, `refresh_report` → `store.write`는 lock을 놓은 뒤에 부릅니다. 문제 없습니다.
- `insights.confirm`: lock 안에서 `Source(...)` 생성과 `.check()`를 부르는데 둘 다 읽기만 합니다. 문제 없습니다.
- `_Calls.run_task` → `write_aux`(lock 획득): LLM 호출 경로(chat · derive · concept · card)는 세션 lock을 잡은 채 부르지 않습니다. 확인했습니다. `PersonaStore(task.sid, root, root.parent.name)`의 version은 `versions/vN/persona`의 `vN`과 일치합니다.
- 순서: `.stage8-launch.lock` → 세션 lock, `.insight.lock` → 세션 lock. 반대 순서는 없습니다. persona `run`의 fresh 사전 단계는 세션 lock을 잡았다가 놓은 뒤 `.insight.lock`을 기다리고, 그 다음 `_run`이 세션 lock을 잡습니다. 순서가 지켜집니다. 운영 워커는 별도 프로세스(`subprocess.Popen`)라서 launch lock과 겹치지 않습니다. 워커의 heartbeat는 별도 스레드(`worker.py:125`)에서 돌기 때문에, `.insight.lock`을 기다리는 동안에도 `STALE_AFTER_S=60`으로 interrupted가 되지 않습니다.
- 경합 · 발행: chat → `source.check()` → `new_revision`(lock 안에서 guard 재확인) → `publish_status`(lock 안에서 guard 재확인). fresh 사전 단계의 `reset_epoch`/`status` 쓰기도 같은 세션 lock으로 직렬화되므로 Codex #1 · #2 · #5의 창이 닫혔습니다.

## 계약 검토(D-312 형태)

| 항목 | 백엔드 | 프론트 | 판정 |
|---|---|---|---|
| `GET /insight` `worker{status,reason,runId,mode,target}` | `stage8.py:250-271` | `types.ts` `InsightWorker`, `InsightScreen.tsx:39-55,87` | 형태 일치. **reason 내용 불일치(N3)** |
| 카드 Context `keywords: string[]` | `cards.py:198` | `types.ts` `PersonaCardContext`, CCM `context[field]` | 일치 |
| 카드 `artifacts: [{name, mention_count}]` | `cards.py:207` | `PersonaScreen.tsx` artifact 행 | 일치 |
| 컨셉 `outdated`/`insight_revision`/`context_ids` | `concepts.py:189`, `chat.py:84`, `store.py:119-128` | `InsightScreen.tsx` 8-F 숨김 · 대상 선택 비활성 | 일치. 무효화 범위가 넓음(N4) |
| 409 `stale` | `source.py:7-9,48` (`kind='stale'`) | `errors.ts` `messages.stale`, `insightActions.ts` chat 분기 | 일치. 다만 kind 우선 규칙이 다른 화면을 깨뜨림(N2) |
| status `package: bool` | `stage8.py:138` | **사용 안 함** | 불일치 → N1 |
| 확정 목록 | `session.insight.confirmed`(현재 판으로 투영) + `confirmed_ids` | `insight.ts` `getInsights`가 `/session`과 합침 | 동작함(두 번 읽으므로 원자적이지 않음, N5) |

---

## 원래 지적별 판정

### opus `final-review1.md`

| ID | 판정 | 근거 |
|---|---|---|
| C1 stale 복구 | **일부** | 프론트 `PersonaScreen.tsx:124`가 stale이면 `{fresh:true}`를 보내고, 백엔드 `pipeline.py:224-243`이 fresh에서 선택을 무시하고 전부 다시 만듭니다(`test_fresh_stale_rebuilds_checkpoints`). 남은 부분: (1) 6단계 확정값만 바뀌고 package가 옛것인 경우 `_run`(`pipeline.py:225-227`)이 다시 stale로 끝나서, "다시 만들기 → stale" 반복을 벗어날 안내(제안 (b)의 `evidence_required` · "근거 탐색을 다시 실행")가 없습니다. (2) fresh는 인사이트까지 지우는데 확인 대화상자가 없고, 버튼 문구도 "다시 만들기"가 아닙니다. |
| I1 패키지 없음 빈 상태 | **일부(+N1)** | 백엔드 `package` 플래그 추가(`stage8.py:131-138`). 프론트는 이를 쓰지 않고 `not_ready`로 추정했고, 그 결과 N1이 생겼습니다. 패키지가 없는 경우의 빈 상태 자체는 이제 처음부터 보입니다. |
| I2 인사이트 워커 실패 화면 | 반영 | `worker` 필드(`stage8.py:250`), 폴링이 terminal 상태에서 멈춤(`InsightScreen.tsx:46`), failed/interrupted 문구 + 다시 시도/이어서 진행(`:87`), 들어올 때 진행 중인 run을 이어서 폴링. reason 문구 문제는 N3. |
| I3 키워드 · Artifact | 반영 | `cards.py:198,207`, `PersonaScreen.tsx` artifact 행, `test_card_package_fields`. |
| I4 재시도 4회 | 반영 | `_Calls.retries_schema`(`pipeline.py:126`), `cards.py:124-125`, `LLMResult.attempts`와 `registry.py`의 실제 시도 수 집계, `test_real_registry_card_attempts_and_report`. |
| I5 채팅 · 되돌리기 뒤 컨셉 · 확정 정합 | 반영(+N4, N5) | (a)(b) `outdated` 무효화(`store.py:92-128`), 체크포인트에서 제외(`insight_pipeline.py:117-120`). (c) `confirmed_ids` 보존(`insight_pipeline.py:47-48`). 무효화가 넓은 문제는 N4, 확정 클릭이 숨은 ID를 지우는 문제는 N5. |
| M1 `known_ki_id` | 반영 | `insights.py` recompute에서 세션 Known ID와 대조, `test_unknown_known_id_is_cleared`. |
| M2 교차 종류 실행 경쟁 | 반영 | `_serialize_launch`(`stage8.py:96-104`, 3개 시작 경로), `test_cross_kind_launch_is_serialized`. |
| M3 채팅 · 되돌리기 · 확정의 선행 조건 · stale | 반영 | `source.Source`(`chat.py:35,108`, `insights.confirm`), `test_stale_mutations_rejected`. |
| M4 처음 화면의 실패 문구 | 반영 | `InsightScreen.tsx` 안내 문구 "페르소나를 바탕으로 인사이트를 도출하세요." |
| M5 구역 이름 두 가지 | 반영 | `personaView.ts` `zoneName` = "A Exciting"(D-315), 맵 · 표 · aria가 함께 씀. |
| M6 맵이 backend legend · 순서를 무시 | **반영 안 됨** | `OpportunityMap.tsx:30-31`은 여전히 `[...].sort()` 문자열 정렬(`CL10` < `CL2`)을 하고 `map.legend`를 쓰지 않습니다. 결정 로그에도 없습니다. |
| M7 범례 칩이 필터가 아님 | **반영 안 됨** | `OpportunityMap.tsx:44`는 여전히 `--blue` 강조만 합니다. 의도한 해석이라는 결정 기록도 없습니다. |
| M8 헤더 · 8-C 표기 | **일부** | journey · sensitivity를 한글 키로 표시(`personaView.ts:50` `fieldNames`). 헤더의 "신뢰도"와 "처방 · 제약 검사 ✓ ⚠" 요약은 여전히 없습니다(`PersonaScreen.tsx` header). |
| M9 숫자 서식 | 반영(+N6) | `formatMetric` · `formatCount`를 Context 표 · 레이더 · 막대 · 맵 · 트리에 적용. |
| M10 derive 입력 크기 | 보류(D-316) | — |
| M11 컨셉 extra · 중복 | 반영 | `concepts.py:30`(`extra='ignore'`), `:50-55` 중복 거부, 테스트 2건. |
| M12 불필요한 LLM 호출 | 반영 | `cards.py:176-181`, `:207-216`, `test_empty_evidence_skips_llm`. |
| M13 "8부터 다시" UI | 보류(D-316) | — |
| M14 기타 | **일부** | `closing`(`insights.py:60`), 이미 추가한 추천 제외(`known/store.py:225`), `personaDone` 즉시 반영(`routers/sessions.py:57-72`, 대신 N8)은 반영. `tablist` 화살표 키 이동(`PersonaScreen.tsx:138`)은 반영 안 됨. |

### Codex `codex-branch-review1.md`

| # | 판정 | 근거 |
|---|---|---|
| 1 버전 전환 경합(`store.py:51`) | 반영 | 모든 변경 경로가 lock 안에서 `assert_writable`(`store.py:57,66,72,85,103`)을 확인하고, 실패한 채팅은 옛 버전에 쓰지 않음(`chat.py:91-92` StoreError를 다시 던짐), `test_failed_chat_never_appends_to_old_version`. |
| 2 fresh 재생성 ↔ 채팅 · 인사이트 | 반영 | persona run이 `.insight.lock`을 잡음(`pipeline.py:215`). `reset_epoch` 사전 공지(`:206-213`), `Source` generation 비교(`source.py:33-40`). 부작용은 N7. |
| 3 컨셉 정합 | 반영(+N4) | 위 I5와 같음. |
| 4 프론트 stale `{}` | 반영 | `PersonaScreen.tsx:124`. |
| 5 stale 상태의 변경 · 발행 | 반영 | `Source.check`를 lock 안의 `_new_revision` guard와 `publish_status(before_publish)`에서 다시 확인. 워커 `pulse`도 같음(`insight_pipeline.py:90`). |
| 6 프론트 확정 상태 동기화 | 반영(+N5) | `insight.ts` `getInsights`가 `/session`의 `insight.confirmed`를 합침. 마운트 · 폴링 · 채팅 · 되돌리기에서 `setConfirmed`. |
| 7 준비 단계 임베더 | 반영 | `known.session_embedder`를 derive(`insight_pipeline.py:111-113`)와 chat(`chat.py:73`)에 사용, 차원 불일치는 명시적 실패(`insights.py` recompute). |
| Minor 1 폴링 6분 | 반영 | I2와 같음. |
| Minor 2 keywords · artifacts | 반영 | I3와 같음. |

## 합계

- opus 20건: 반영 12 · 일부 4(C1, I1, M8, M14) · 반영 안 됨 2(M6, M7) · 보류 2(M10, M13)
- Codex 9건: 반영 9
- **전체 29건: 반영 21 · 일부 4 · 반영 안 됨 2 · 보류 2**

## merge 전 필수
1. N1(Critical): `status.package`로 빈 상태를 판단하고 `not_ready` 추정을 없앱니다. 테스트 44행을 뒤집습니다.
2. N2: `responseError`에서 code를 먼저 봅니다. kind+code 회귀 테스트를 추가합니다.
3. N3: `worker.reason`에 한글 사유만 싣습니다(감독자 클래스 이름 금지).
4. N4: 컨셉 무효화 비교를 원천 필드로 좁힙니다.
5. 권장: C1 잔여(확정값만 바뀐 경우의 안내), M6 · M7은 고치거나 "의도한 해석"을 결정 로그에 남깁니다.
