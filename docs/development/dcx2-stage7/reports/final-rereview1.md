# 묶음 ② (7단계) 최종 수정 재리뷰 1

- 범위: `a92f2f3..99a8c22`(커밋된 수정 diff). 기준: `final-review1.md`(opus C1 · I1–I8 · M1–M11), `codex-branch-review1.md`(Codex 1–9), D-259–D-266, 수정 보고서 2건.
- 읽기 전용. 이 파일 외 수정 · 커밋 없음.
- 주의: 리뷰 도중 worktree에 **커밋되지 않은 다른 세션(QA, D-267 · D-268)의 변경**이 생겼다(`pipeline.py` · `routers/evidence.py` · `EvidenceScreen.tsx` · `types.ts` · `llm/fake.py` · `evidence_echo.py` 등). 아래 판정은 커밋 HEAD 기준이다. 테스트 실행에는 그 변경이 일부 섞였을 수 있다.
- 실행:
  - `backend/.venv/bin/python -m pytest backend/tests/evidence backend/tests/segment backend/tests/context -q` → **687 passed, 2 deselected**
  - `npm --prefix frontend test` → **56 files / 539 tests passed**
  - 통합 테스트(`test_integration.py`, `--basetemp`로 보존) 산출 `package.json`을 `backend/app/evidence/package.py` `EvidencePackage`로 다시 검증 → **유효, round-trip 동일**. Context quality 4키(`cohesion · boundary · stability · npmi`, 관측 없으면 null), Persona quality 3키(실측 `cohesion 0.886 · boundary 0.0 · stability_ari 1.0`), `quote` null 0건, 전체 탭 전용 항목 중 novelty 있는 것 0건(I6 관측 사례 `d000056` → `novelty: null`).
  - 참고: 같은 파일을 ③ `dcx_agent-stage8-impl`(HEAD 4438f50) `app/persona/package.py`로 검증하면 여전히 103/683 오류지만 **전부 ③ 쪽 엄격성**(`polarity: str`, `novelty`/`combo_rarity`/quality 값 non-null 요구)이다. ② 쪽 키 누락 오류는 0. D-259에 따라 ③ T17 몫.

## 판정: **Ready with one fix** (새 Important 1건)

---

## 항목별 판정

### opus

| 항목 | 판정 | 근거 |
|---|---|---|
| C1 패키지 2.4 | **addressed**(② 범위) · ③ 리더 완화는 **deferred-by-ruling**(D-259, ③ T17) | `package.py:58-75` `ContextQuality` · `PersonaQuality` 타입 모델, `assemble.py:158-159` 4키 고정, `assemble.py:363-364` Persona quality(SQLite 실측 → stage_6 보고서 fallback), `segment/pipeline.py:445-447` Persona quality 계산 · 저장, `segment/store.py:84-85` 컬럼 추가 마이그레이션. 통합 산출물 재검증 통과(위). |
| I1 완료 뒤 문장형 KI | **addressed** | `pipeline.py:566-611` refresh가 빠진 (문서, 문장 KI) 쌍만 잠금 밖에서 판정 → 잠금 안에서 세대 재확인 후 투영. `:575` 판정 전 `knownChanged=True`, `:137-139` 빠진 쌍이 남으면 계속 True. `:258-267` worker reconcile도 빠진 쌍 · 지문 변경을 `knownChanged`로 표시. |
| I2 첫 실행 stale 오표시 | **addressed** | `segment/pipeline.py:68-69`(evidence 상태가 none이 아닐 때만 stale), `versions.py:162`(7부터 다시 → none), `EvidenceScreen.tsx:55`(`status.run !== null`일 때만 경고). 테스트 `test_d260_first_segment_not_stale`. 단 `test_integration.py:113`은 여전히 `'stale'` 허용(테스트 좁히기 미반영, Minor). |
| I3 실행 중 태깅 호출 수 | **partially**(HEAD 기준) | 백엔드는 됨: `pipeline.py:243` detail.tagCalls, `routers/evidence.py:88` status `tagCalls`. 프런트 HEAD는 `EvidenceScreen.tsx:60`에서 여전히 `status.stage7?.tag_calls`를 읽는데, 새 실행은 `pipeline.py:202`에서 `stage_7.json`을 지우고 끝날 때만 다시 쓰므로 실행 중엔 계속 0회. 프런트 픽스처(`evidenceFixtures.ts` `evidenceStatusFixture`)가 running 상태에 stage7을 넣어 다시 가린다. 커밋되지 않은 QA 변경(D-268: `status.tagCalls` 사용 · `tagCalls?: number` 타입 추가)이 이를 고치는 것으로 보이나 이 리뷰 범위 밖. 커밋되면 addressed. |
| I4 라벨링 배너 키 | **addressed** | `labeling/page.tsx:53` `relevant_false`. 백엔드 `stage_report` 키와 일치(`assemble.py:181-182` `_COUNTERS`, 통합 테스트 `:154`). |
| I5 인용 하이라이트 필드 | **addressed** | `quotes.py:28-37` `quote_source`(locate와 같은 원문 · 같은 코드 포인트 기준), `assemble.py:241-252` `item_view`가 GET · refresh 공통으로 `quoteSource` · `noveltyShown` 생성, `EvidenceCard.tsx:11,15` 하이라이트는 `quoteSource.text`에만, 본문 미리보기는 별도 비강조. |
| I6 refresh 뒤 전체 탭 novelty | **addressed**(SQLite · API) — 단 디스크 패키지 반영은 새 결함 N1 | `pipeline.py:133-135` all 탭 novelty를 새 new 탭 소속 기준으로 다시 씀, `assemble.py:344` 패키지는 `tab == 'new'` 행에서만 novelty. |
| I7 미분화 플래그 잔존 | **addressed** | `assemble.py:89-101` set/remove, `:325-326` 이번 결과 기준 갱신, `versions.py:163-168` 7부터 다시에서 제거, `pipeline.py:598-601` refresh 시 해당 Context 재계산. |
| I8 Persona 위반 전파 | **addressed** | `queries.py:141` 응답 자체 실패만 전체 대체, Context 위반은 해당 Context만, `:157-163` Persona 쿼리 대체(Desire + Goal, `origin: fallback`), `assemble.py:293` `persona_query_fail`. docstring(`queries.py:105-107`)은 옛 설명 그대로(Minor). |
| M1 Act 불일치 | **addressed** | `assemble.py:298` `act_mismatch`. |
| M2 반례 기준 평균 | **addressed** | `assemble.py:43-45` `context_polarity_mean`을 API(`routers/evidence.py:147`) · refresh(`pipeline.py:535`) · 패키지(`assemble.py:347`) 공통 사용. |
| M3 첫 인용만 사용 | **addressed** | `assemble.py:231-232` 첫 verified, 없으면 첫 인용. |
| M4 novelty 입력 과대 | **addressed** | `novelty.py:65-70` 태깅과 같은 발췌. |
| M5 novelty 배지 임계 | **addressed** | `params.NOVELTY_SHOW` → `noveltyShown`, `EvidenceCard.tsx:22`. |
| M6 6단계 실행 버튼 | **addressed** | `SegmentScreen.tsx:371` `?start=1`, `EvidenceScreen.tsx` 자동 시작 effect(1회, URL 정리). |
| M7 공유 캐시 drop_known | **addressed**(D-265) | `pipeline.py` 실행 · refresh에서 `drop_known` 호출 제거, 투영은 현재 KI 지문만. |
| M8 refresh 전체 적재 | **addressed** — 단 지연 조립이 새 결함 N1 | `pipeline.py:543-563` `_load_context`(후보 문서 · 벡터만), `:610` `package_dirty.json`. |
| M9 doc KI LLM 판정 | **addressed** | `tagging.py:184` · `:228` statement만. |
| M10 stale 스켈레톤 | **addressed** | `EvidenceScreen.tsx:46,71,74` stale이면 "다시 실행 후 열람할 수 있습니다." |
| M11 작은 표시 | **addressed** | Artifact `mention_count`(`EvidenceScreen.tsx:74`), KI 번호(`knownNumbers`), partial 안내 배너(`:56`). |

### Codex

| 항목 | 판정 | 근거 |
|---|---|---|
| 1 refresh · 발행 경합 | **addressed** | 모든 발행이 `sessions.locked` + `generation.check`: `pipeline.py:161-162, 419-420, 434-435, 475-485`, refresh 2단계 `:584-611`. 조립은 `store.patch_counts`(`store.py:174-181`)로 소유 필드만 병합(`assemble.py:333`). `save()`(`:222-234`)도 잠금 + run 확인 + 호출 수 델타 병합. |
| 2 실행 중 6단계 재시작 | **addressed** | `work/runner.py:29-33` 같은 work DB 트랜잭션 안에서 segment ↔ evidence 동시 실행 거부, `generation.py:34-41` 발행 시 segment run · prepKey · stale 확인. |
| 3 완료 뒤 문장 KI | **addressed** | = I1. |
| 4 KI 수정 시 같은 ID 캐시 | **addressed** | `cache.py:39-46` `known_key` = id + (type, text, doc_id) SHA-256, `known_snapshot`; 모든 판정 쓰기 · 읽기(`tagging.py:170-178, 213-215, 231-234`, `pipeline.py:80-85`, `assemble.py:282-285`)가 같은 키 사용. 키 구성은 `model_dump`와 `_known_rows`에서 동일함을 확인. |
| 5 인용 필드 짝 | **addressed** | = I5. |
| 6 프롬프트 판 변경 | **addressed** | `generation.py:12-18` 생성마다 segmentRun · prep · training · prepKey · 프롬프트 해시 4종 기록, 읽기는 `generation.inputs`로 기록된 pver 사용(`assemble.py:268`, `routers/evidence.py:110`, `pipeline.py:545`), `pipeline.py:191` 값이 다르면 fresh, `generation.py:49-54` refresh는 409. |
| 7 질의 임베딩 실패 | **addressed** | `candidates.py:17-23` 개수 · 모양 · 유한 · 노름 검사 → retryable 예외, `pipeline.py:322-323` 쿼리 없음 실패, `:411-431` Persona 임베딩 실패 시 해당 Context failed · partial. |
| 8 라벨링 배너 키 | **addressed** | = I4. |
| 9 novelty 배지 | **addressed** | = M5. |

**합계(29건, 중복 포함 개별 판정)**: addressed 28 (C1의 ③ 리더 완화 부분은 D-259로 ③ T17 이관) · partially 1 (I3, HEAD 기준) · not addressed 0.

---

## 집중 점검 결과

### 잠금 순서 · 교착
- `sessions.locked`는 `fcntl.flock`을 매번 새 fd로 잡으므로 **같은 프로세스에서 중첩하면 자기 교착**이다. 새로 추가된 잠금 지점(`pipeline.py:161, 195, 225, 250, 419, 434, 475, 483, 568, 584`, `routers/evidence.py:50, 193`)을 모두 따라가 봤고 중첩 획득은 없다: `save()`(잠금)는 잠금 밖에서만 호출, `pulse → _session`은 잠금 밖, `_finish`/`refresh_new`/GET package 안의 `generation.check` · `assert_writable` · `_assemble` · `append_context_flag`는 잠금을 잡지 않는다. `reconcile` 안의 `_refresh_cached`도 잠금 없음.
- 순서: 항상 flock → SQLite(evidence · segment · cache). work DB 트랜잭션(`runner.start`, `status.refresh`)은 flock을 잡지 않는다. router start는 flock 안에서 work DB를 읽고 놓은 뒤 `runner.start`. 역순 경로 없음.
- worker 메인 스레드는 flock을 쥔 채 pool 스레드를 기다리지 않는다(발행 블록 안은 SQLite 쓰기만). pool 스레드의 `rpc`는 메인 스레드가 잠금 밖에서 처리.
- refresh 1단계 LLM 판정은 잠금 밖이라 worker heartbeat(60초 기준)를 막지 않는다.
- **교착 없음.**

### 세대 스냅샷 무효화가 정상 완료 Context를 버리는가
- 정상 경로(같은 prepKey · segment run · 프롬프트)는 `generation.read == captured`라 이어 하기에서 완료 Context를 유지한다(테스트 `test_d263_prompt_generation_pinned_then_invalidated`).
- 다만 비교 대상이 `session.prep` · `session.training` **전체 dict**라 입력과 무관한 필드 변화에도 fresh가 된다 → N3(Minor).

### 패키지 검증
- 통합 산출물이 ② `package.py`로 유효(위). 남은 ③ 오류는 전부 ③ 엄격성(D-259 이관).

### 프런트 ↔ 백엔드 D-266 모양
- `item_view`(`assemble.py:241-252`) 키 = 프런트 `EvidenceItemView`(`types.ts:237-240`): `docId · source · location · quote · quoteSource{field, idx, text} · noveltyShown · text · tags · band · novelty · noveltyReason · knownMatch · rare · role` — 일치. GET Context · Persona · refresh-new 모두 같은 함수.
- `stage7.relevant_false` · `stage7.tag_calls`: `stage_report` 키와 일치.
- 어긋남은 실행 중 `tag_calls` 출처 하나(I3, 위).

---

## 새 결함

### Important

**N1. refresh-new 뒤 디스크의 `package.json`이 갱신되지 않는다 — ③은 파일을 직접 읽는다**
- 위치: `pipeline.py:610`(refresh는 `package_dirty.json`만 남김), `routers/evidence.py:188-196`(dirty 재조립은 GET /package에서만), ③ `dcx_agent-stage8-impl/backend/app/persona/package.py:138-144`(`load_package`가 `evidence/package.json`을 바로 읽음). 프런트에서 `getEvidencePackage`를 부르는 곳은 테스트(`evidenceView.test.ts:63`)뿐.
- 시나리오: 7단계 완료 → 카드 [Known Insight에 추가] → 새 발견 다시 계산 → 화면 · SQLite는 바뀌지만 `package.json`은 이전 그대로(그 문서가 `tab: ["all","new"]`, `novelty: "high"`) → `evidenceDone`은 그대로 true → [페르소나 만들기] → 8단계가 옛 패키지로 "이미 아는 얘기"를 새 발견으로 서술. I6 · I1 수정이 7→8 경계에서 다시 무효가 된다(이전 코드는 refresh에서 동기 조립했으므로 회귀).
- 덧붙여 dirty 재조립은 `generation.check → assert_writable`을 거치므로, refresh 뒤 새 버전을 만들어 이 버전이 읽기 전용이 되면 GET /package도 영구 실패.
- 통합 테스트 `assert_package`(`test_integration.py:125-129`)가 GET을 먼저 불러 재조립을 일으킨 뒤 파일을 비교해서 가려졌다.
- 수정(택1): (a) refresh 2단계 끝에서 잠금 안에 `_assemble`을 다시 호출(M8의 적재 축소는 유지, 조립 비용만 감수), (b) ②에 `ensure_package(sid, version)`(dirty면 잠금 안에서 재조립, 읽기 전용 버전에서도 동작)를 두고 ③ `load_package`가 그것을 쓰도록 T17 계약에 명시, (c) dirty 동안 `evidenceDone`을 내린다. 테스트: refresh 뒤 GET 없이 `package.json`을 읽어 novelty · tab 확인.

### Minor

- **N2. 발행 시 세대 불일치가 `failed`(영문 사유)로 끝남** — `pipeline.py:483-485`의 `except`가 `generation.check`를 다시 불러 같은 예외로 빠져나가고 `:501`이 `status='failed', reason='Evidence input generation changed'`로 덮는다. 런처 차단(Codex 2) 덕에 드물지만, 생기면 사유가 영어이고 stale로 보이지 않는다. 409 `stale_run`은 `_Stopped`처럼 따로 잡아 `interrupted`(또는 손대지 않음) + 한국어 사유.
- **N3. 생성 비교가 `prep` · `training` 전체 dict** — `generation.py:13-15`, `pipeline.py:191`. `training.monitor`(`model/monitor.py:126`) 같은 입력과 무관한 쓰기만으로 이어 하기가 fresh가 되어 완료 Context를 버린다. 수정 전 세션(`generation.json` 없음)도 첫 이어 하기에서 전부 다시 계산. 비교는 `prepKey` · `exportRef` · `modelId` 등 입력 참조만.
- **N4. refresh가 문장 KI 판정을 HTTP 요청 안에서 동시 1로 순차 실행** — `pipeline.py:576-583`. 후보 수/8회 LLM 호출이 한 요청에 묶여 수십 초 이상 걸릴 수 있다(설계 7 "수 초"). 같은 Context refresh 두 건이 겹치면 같은 쌍을 두 번 판정. 동시성 상한 사용 또는 worker 위임 검토.
- **N5. GET /package 재조립이 완료 검사보다 먼저 돎** — `routers/evidence.py:192-196`. 이어 하기 실행 중 GET이 오면 부분 패키지를 조립 · 기록한 뒤 409를 낸다. dirty 재조립을 done 확인 뒤로.
- **N6. 프롬프트 판 변경 후 refresh 409 문구가 영어("resume evidence first")이고 done 상태 화면엔 이어 하기 버튼이 없음** — `generation.py:49-54`. 개발자만 겪는 경로.
- **N7. 카드에 본문이 두 번 보임** — `EvidenceCard.tsx:14-15`: 600자 미리보기 + `quoteSource.text` 전체를 blockquote로. 인용이 없을 때도 `item_view`가 body 필드로 기본값을 줘서(`assemble.py:245`) 본문 전체가 다시 나온다. 인용 필드가 body면 미리보기를 생략하거나 blockquote를 인용 주변 발췌로.
- **N8. 런처 충돌 오류가 영어** — `runner.py:32-33` "Conflicting segment/evidence worker is active"가 6단계 화면에 그대로 뜰 수 있다. paused evidence는 취소 전까지 6단계 재실행을 막는다는 안내 필요.
- **N9. KI 번호 effect가 status 폴링마다 KI 목록을 다시 받음** — `EvidenceScreen.tsx`(deps `[sid,version,revision,status]`). `status?.run`/`revision`으로 좁히기.
- **N10. `?start=1`로 이미 done인 화면에 들어오면 새 실행을 시작** — `start`는 running만 거부. `before`(none/stale)일 때만 자동 시작.

### 테스트 공백
- refresh 뒤 GET 없이 `package.json` 직접 읽기(N1).
- `test_integration.py:113`이 첫 6단계 뒤 `'stale'`을 여전히 허용(I2 수정 뒤 `'none'`으로).
- 프런트 running 픽스처에 `stage7`이 들어 있어 실행 중 값의 실제 출처를 검증하지 못함(I3).
