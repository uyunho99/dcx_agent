# SDD ledger — plan: docs/development/dcx2-stage6-8/03-plan.md

Spec: docs/development/dcx2-stage6-8/02-design.md (+ decision-log D-229..D-239 override). Executor: Codex (codex:codex-rescue, --wait --fresh, write). 순차 위임(같은 worktree).
BASE(branch start): 9c1e3d7. Baseline: backend 1458 passed · frontend 318 passed · lint · build OK.

## Pre-flight scan
| 대상 | 생산 ↔ 소비 | 발견 | Ruling |
|---|---|---|---|
| T1 ↔ T2~T9 | 합성 세션(`make_segment_session`) · 가짜 LLM JSON ↔ 모든 백엔드 테스트 | export 행 `source`는 판정 출처로 둬야 Codex #1 테스트가 성립 | Ruling: T1 픽스처 export 행 `source='agreed'`, 수집 채널은 derived/docs에만 — 실제 export와 같게 — 틀리면 T2 채널 테스트가 무의미 |
| T11 ↔ T6 | export `pred_entropy` ↔ T6 복사 | 이미 만든 옛 export는 라벨 경로 0 | Ruling: T6는 export 값을 그대로 복사, 옛 export는 0(재내보내기 시 갱신) — 6단계에서 votes 없이 재계산 불가 — 틀리면 옛 세션 entropy 0 |
| T2 ↔ T3/T4/T5 | `SegmentInput`(f16 vectors · tokens · nouns · docs) | 일치 | — |
| T3 ↔ T4 | `ctfidf.ctfidf` | 일치 | — |
| T7 · T8 ↔ T1 | LLM 출력 스키마 ↔ 가짜 JSON | T1이 스키마를 먼저 고정해야 함 | Ruling: T1 가짜 JSON은 brief의 `DimsOut` 형태와 T8 출력(이름 · Desire · Goal)을 따르고, T7 · T8은 T1 픽스처에 맞춘 Pydantic 모델을 정의 — 틀리면 T7/T8에서 픽스처 수정(소유 예외 허용) |
| T9 ↔ T10 | `session.segment` · `run` · confirm 집계 | run은 T9가 기록, T10이 검사 | Ruling: `run` 생성 · 기록은 T9(pipeline), 검사는 T10 |
| T10 ↔ T12 | API 계약 표 | 일치 | — |
| T13 ↔ T14 | LayerTabs 등 ↔ 화면 | 일치 | — |
| T14 ↔ versions UI | `StageVersion stage="stage6"` | Stage 타입이 stage6을 허용하는지 미확인 | Ruling: T14가 `components/versions` 타입에 stage6 추가 필요 시 최소 수정 허용 — 소유 표 밖이지만 다른 Task가 안 건드림 — 틀리면 리뷰에서 범위 지적 |
| T15 | STEPS 10개 · 미구현 경로 | 근거 탐색 · 인사이트 경로 없음 | Ruling: 해당 링크 비활성(`aria-disabled`, 툴팁 "다음 묶음에서 열립니다"), 페르소나는 기존 `/pipeline/personas` 유지 — 틀리면 사이드바 문구만 수정 |
| 각 Task 자기 일관성 | 테스트 ↔ 소유 파일 | T6 `signals.py`에 emerging 제거(D-229) 반영 확인 · T5 L3_TOPICS (2,10) 반영 확인 | — |

Task T1: complete (commits 9c1e3d7..af881bf, review clean) — executor codex, controller committed (Codex sandbox cannot write worktree git metadata)
Task T1: minor (deferred): QA 합성 어휘가 `냉방_CL0-P0` 형태 — QA 화면 사실감 낮음
Task T1: minor (deferred): segment_synth가 tests.test_integration_stage3_5를 import(브리프가 재사용 요구)
Task T1: minor (deferred): Context 안 문서 토큰이 동일 — 경계 · ARI 테스트에 너무 깨끗할 수 있음
Ruling: T7 · T8은 가짜 dims에 `segment_synth.fake_dims_backend`를 쓰고 픽스처 JSON을 실제 출력 모델로 검증해야 함(T1 리뷰 ⚠️) — 해당 브리프 위임에 전달 — 틀리면 T7/T8 테스트가 고정 doc_id에 묶임
Task T11: complete (commits af881bf..459de43, review clean)
Task T11: minor (deferred): `_label_entropy`가 votes_json NULL이면 TypeError(현재 쓰기 경로상 도달 불가) — `or '{}'` 방어 권장
Task T11: minor (deferred): Jev만 있고 GPT 없는 agreed 행 테스트 없음(동작은 0)
Task T13: complete (commits 459de43..12b4d94, review clean)
Task T13: minor (deferred): QualityBadges 표시값(반올림)과 경고 판정(원값) 불일치(0.598 → "0.60 · 분리 검토")
Task T13: minor (deferred): quality.flags 미표시 — 화면(T14)이 granularity_exceeded 등 직접 표시해야 함
Task T13: minor (deferred): LayerTabs 인라인 스타일 · focus-visible 없음 · 테스트가 함수 직접 호출
Task T15: review Needs fixes — Important: pipeline/layout.tsx handleChat 8칸 STEPS를 stepIndex로 인덱싱 → 페르소나·done 페이지 채팅 문맥 "시작", evidence는 "페르소나"
Ruling: layout.tsx는 소유 Task 없음 → T15 수정 범위에 포함(StepBar의 단계 이름 목록을 export해 공유) — 다른 Task와 겹치지 않음 — 틀리면 T14가 layout.tsx를 건드릴 때 충돌
Task T15: minor (deferred): 비활성 단계(근거 탐색)에 완료 체크가 표시될 수 있음 · 비활성 링크 스타일 없음 · 클릭 무반응 테스트 없음
Task T2: implementer DONE (Codex 전체 실행 3 실패는 샌드박스/환경변수 탓, 컨트롤러 전체 실행 1494 passed); committed 8b2545f..7af099b, review pending
Task T15: fix round 1/5 (1 addressed, 0 open — layout.tsx 채팅 단계 이름 공유; commits 7af099b..a28272d)
Task T15: complete (commits 12b4d94..a28272d, review clean after fix 1)
Task T2: review Needs fixes — Important: 명사 캐시가 세션 flock 안에서 전체 Kiwi 분석(교착 위험)
Ruling: 명사 캐시는 relevant 부분집합이 아닌 derived 전체 문서 대상 유지(prepKey 단위, 버전 무관 재사용) — 리뷰어 제안 일부 기각 — 틀리면 첫 실행이 조금 더 오래 걸림
Task T2: fix round 1 implemented (전용 잠금 · truncated 최종 대상만; commit 085f16d; 컨트롤러 전체 1496 passed), re-review pending
Task T2: fix round 1/5 (2 addressed, 0 open; commits a28272d..085f16d)
Task T2: complete (commits 8b2545f..085f16d, review clean after fix 1)
Task T2: minor (deferred): store._encode가 *_json 열의 str을 json.loads(비JSON 문자열이면 오류) · write_layers 행별 execute · VectorStore.get 배치마다 색인 재구성
Task T3: complete (commits 085f16d..ba33163, review clean)
Task T3: minor (deferred): Ward 표본 2만 건이 scipy 내부 거리 배열 약 1.6GB — 맥미니 16GB에서 T9/QA 때 확인, 필요하면 WARD_SAMPLE 축소
Task T3: minor (deferred): 테스트가 threadpool_limits(1)로 고정 — 실제 다중 스레드 비결정성 미검증
Task T5: complete (commits ba33163..61e832f, review clean)
Task T5: minor (deferred): LDA 9회 + C_v로 2만 건 Persona 약 166초 — T9는 Persona 단위 진행 보고 필요(사용자 D9 선택으로 예상된 비용)
Task T5: minor (deferred): 모든 C_v가 NaN이면 k=2 조용히 선택 · 반례 경계 부동소수 · 밴드 동률 처리
Task T6: complete (commits 61e832f..083c5e0, review clean)
Task T6: minor (deferred): boundary 표본에서 작은 target 클러스터가 빠질 수 있음 — T9가 클러스터별 계산 시 고려 · KNU word/root 병합 규칙
Task T7: complete (commits 083c5e0..96e29d4, review clean)
Task T7: minor (deferred): dims 프롬프트에 분석 용어("Context 차원", "코드 정규화") — QA-L1 전 정리 권장(프롬프트 해시 바뀜) · 본문 길이 상한 없음 · dims가 store._db 직접 호출 · 쌍 이름 tg_rc/env_ar 7단계와 맞출 것
Ruling: personas 테이블에 flags_json이 없음(T8 보고) → T9가 store.py에 personas.flags_json 열을 추가(기존 DB 마이그레이션 포함)하고 few_communities · draft_failed를 저장 — 설계 2.2 표 누락 보정 — 틀리면 6-B에 플래그가 안 보임
Task T8: complete (commits 96e29d4..62f8fea, review clean)
Task T8: minor (deferred): 플래그 위치가 클러스터 quality.flags / Persona 반환값+meta.draft_flags / Context flags로 흩어짐(T9가 통합) · reps 길이 상한 없음 · 프롬프트 분석 용어 · store 비공개 함수 사용
Task T4: implementer DONE (1590 passed), committed 62f8fea..e0d124f, review pending
Ruling: segmentDone/clear_stale 처리는 T9 pipeline.py의 `mark_done_if_complete(sid, version)`로 두고 T10 확정 API가 호출 — 계약 표 "T9 ↔ T15" 해석 — 틀리면 T10에서 위치만 이동
Task T4: review Needs fixes — Important: 고립 명사 중심성 1.0 오염 · 문서 0건 가짜 Persona (재현됨)
Task T4: fix round 1 implemented (commit 4795d31; 1618 passed), re-review pending
Task T4: minor (deferred): 불용어 목록 없음(실데이터에서 일반 명사 지배 가능 — 결정 기록 대상) · _merge 반복 재계산
Task T9: review Needs fixes — Important: R3 회귀 테스트가 예전 동작 대비를 못 잡음 · 실패한 초안 호출이 캐시돼 재개 시 재시도 안 됨
Ruling: T9 Minor 3(새 실행이 segment.sqlite-journal 삭제 → DB 손상 위험)과 Minor 4(args에 k=None이면 새 실행으로 간주돼 확정값 삭제 — T10이 의존)는 load-bearing이라 수정 라운드에 포함, Minor 7(가짜 경로라 실패할 수 없는 캐시 유지 테스트)도 포함 — 나머지(5 · 6 · 8 · 9)는 보류 — 틀리면 수정 범위가 약간 큼
Task T4: fix round 1/5 (2 addressed, 0 open; commits 6bf41e0..4795d31)
Task T4: complete (commits 62f8fea..4795d31, review clean after fix 1)
Task T9: fix round 1/5 (5 addressed, 0 open; commits 4795d31..f8502eb)
Task T9: complete (commits e0d124f..f8502eb, review clean after fix 1)
Task T9: minor (deferred): boundary를 클러스터마다 전체 표본으로 반복 계산 · stage_6 Persona 행의 fallback/ari가 클러스터 값 반복 · 실패 상태 기록 예외 은닉 · T7/T8 비공개 함수 의존
Task T10: complete (commits f8502eb..7c7d450, review clean)
Task T10: minor (deferred): GET /docs가 페이지마다 전체 샤드 스캔 · GET이 segment.sqlite를 생성(읽기 전용 버전도) · 실행 중 POST run(k, confirmReset)이 기존 실행 runId를 조용히 반환 → T14는 실행 중 "다시 나누기" 비활성 · mark_done 호출 시점 버전 전환 엣지
Task T12: complete (commits 7c7d450..534eed8, review clean)
Task T12: minor (deferred): 품질 임계 로직이 segmentView.ts와 QualityBadges.tsx에 중복 · 실제 경로에서 오류 kind가 사라지고 메시지 문자열로 판정
Task T14: implementer DONE_WITH_CONCERNS (403 frontend passed; 기본 빌드 정체는 샌드박스 탓 — 컨트롤러 환경 기본 빌드 통과); committed 534eed8..253acf9, review pending
Ruling: T14 우려 2 — POST /segment/run이 결과가 있으면 confirmReset 없이는 거부해, 중단된 실행의 "이어서 진행"(설계 9절)이 불가능 → T10 수정: 마지막 실행이 interrupted/failed/running 아님(즉 중단)이고 k 없음 · confirmReset 없음이면 fresh=false로 재개 허용, 결과가 review/done 상태일 때만 confirm_required — 설계 9절 우선 — 틀리면 재개 시 확정값 보존 규칙 재확인 필요
Task T10: fix round 1/5 (cross-task finding from T14: 중단/실패 실행 재개 허용 · 실행 중 409 running; commit 8bbd825; 1658 passed), re-review pending
Task T14: review Needs fixes — Important: 임시 저장 입력이 앱 내 이동 후 복원 안 됨(스토어 미갱신) · stale_run 배너가 "입력은 유지됩니다"라 약속하고 새로고침 시 버림
Ruling: T14 수정 라운드에 Minor 3(확정마다 편집기 언마운트 → 키보드 포커스 손실) · 4(고른 k가 로드마다 제안값으로 되돌아감) · 5(버전/stale 배너 중복) · 6(aria-live 범위) · 7(폴링 실패 오류가 남아 계속 막힘) · 8(설계 3.10 "6-B로 →" 주요 버튼 누락)과 T10의 새 오류 kind `running` 처리를 포함 — 사용자에게 보이는 결함이고 같은 파일 — Minor 9는 보류 — 틀리면 수정 범위가 큼
Task T10: fix round 1/5 (1 addressed, 0 open; commit 8bbd825)
Task T10: complete (commits f8502eb..8bbd825, review clean after fix 1)
Task T14: fix round 1/5 (9 addressed, 0 open; commits 8bbd825..5981e30)
Task T14: complete (commits 534eed8..5981e30, review clean after fix 1)
Task T14: minor (deferred): stopped 실행에서 버튼 문구가 "이어서 진행" 아닌 "클러스터링 실행"(동작 동일) · paused는 진행 화면 유지 · 레거시 화면 세션 새로고침

## Final review (opus, 9c1e3d7..5981e30): Ready with fixes — Critical 0, Important 7
Ruling: 최종 수정 1회 묶음 = Important 1~7 + 병합 전 수정 Minor(T11 votes NULL 방어 · T7 dims 프롬프트 분석 용어 제거 + 본문 길이 상한 · T8 reps 길이 상한 + 프롬프트 용어 정리) + Minor(WAL 모드 · 서버측 stale-run 임시저장 거부는 보류) — 사용자 UAT 전에 실데이터 규모 대응 필요(D-236) — 틀리면 수정 범위가 큼
Ruling: T4 불용어 목록 없음 → UAT 전 사용자 결정 항목으로 기록(결정 로그) — 실데이터에서 일반 명사가 L2 지배 가능

Final fix wave: commit 54435cf (11 findings), re-review: all addressed (opus). Residual low: _SelectedVectors per-row stat; some English StoreError messages could surface as reason.
