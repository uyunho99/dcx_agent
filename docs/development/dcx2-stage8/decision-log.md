# 결정 기록 — 묶음 ③ (`dcx2-stage8`)

- 공통 원장: [`../dcx2-stage6-8/decision-log.md`](../dcx2-stage6-8/decision-log.md) D-201~ (묶음 ①·②가 이어 씀). 묶음 ③은 병행 브랜치라 merge 충돌을 피하려고 이 파일에 D-301~로 남긴다.

## 기획 (2026-10-02)

### D-301 ③은 Evidence Package를 픽스처 + 읽기 검증 모델로만 쓰고, 생성 모델은 ② 소유 · 판단 (Claude, R1)
- ③을 ② 위로 rebase할 때 ②의 모델로 바꾸고 픽스처 ↔ ② 실제 출력 대조 테스트를 추가한다. 비용: rebase 때 모델 교체 1회.
### D-302 Persona 카드 생성은 Context 최대 4개씩 나눠 호출 + 8-B · 8-C 요약 1회 · 판단 (Claude, R2)
- D-235로 Persona당 Context가 최대 10개라 한 번에 넣으면 입력이 너무 크다. CCM 화면은 설계대로 4열 넘으면 2단.
### D-303 새 세션은 새 8단계 화면, 옛 세션은 기존 페르소나 · 인사이트 화면 그대로 · 판단 (Claude, R3)
### D-304 ③ 픽스처 Evidence Package는 구역 A~F · ★ 마커가 모두 나오도록 따로 만든다 · 판단 (Claude, R4)

## 설계 (2026-10-02)

### D-305 확정 인사이트 추천은 별도 API(`/known/{sid}/suggestions`) + 서랍 접힘 구역, 기존 prev_session 자동 복사에 섞지 않음 · 판단 (Claude)
- 이유: 기존 `known.store.initialize`가 이전 세션 Known 문장을 자동 복사하므로, 그 경로에 넣으면 D-217(추천만)을 어긴다. 비용: API 1개 · 서랍 구역 1개.
### D-306 기존 `/insights` 경로를 `/pipeline/insights`로 옮기고 옛 세션은 그 경로에서 기존 화면 · 판단 (Claude)
- 사이드바 단계 경로를 한 체계(`/pipeline/*`)로 맞춘다. 옛 링크 `/insights`는 새 경로로 넘김.
### D-307 Opportunity 기준선 위 정확히 놓인 점은 위쪽 구역 · 판단 (Claude)

## 계획 (2026-10-02)

### D-308 ② · ③ 공유 파일 충돌은 ② 먼저 merge, ③ T17 rebase에서 해결 · 판단 (Claude)
- 공유 파일: `app/work/worker.py` · `app/context/versions.py` · `app/routers/sessions.py` · `StepBar.tsx` · `completedThrough.ts`. 각 브랜치 안에서는 한 Task만 고친다.
### D-309 이전 세션 추천은 최근 20개 · 같은 제목 중복 제거 · 판단 (Claude, Review Focus 4)

## 구현 (2026-10-02)

### D-310 8-F 근거 문구의 작성자 수는 근거 문서의 author_hash 중복 제거 수 · 판단 (Claude, T9 Codex 우려)
- Context별 author_count를 더하면 여러 Context에 쓴 같은 작성자가 두 번 센다. segment.sqlite docs의 author_hash로 근거 doc_id 기준 중복 제거.
### D-311 레이더 백분위는 중간 순위(midrank) 0~100 · 판단 (Claude, T8 Codex 선택 수용)
- `100 × (아래 수 + 0.5 × 같은 수) / N`. 같은 값은 같은 순위, 하나뿐이면 50.

## 최종 리뷰 반영 (2026-10-02)

### D-312 최종 리뷰(opus · Codex) 지적은 백엔드 · 프론트 두 수정 묶음으로 동시에 고친다 · 판단 (Claude)
- 공유 계약: `GET /insight/{sid}` 응답에 `worker: {status: 'idle'|'running'|'done'|'failed'|'interrupted', reason: string|null, runId: string|null, mode: 'derive'|'concept'|null, target: string|null}` 추가. 카드 응답 Context마다 `keywords: string[]`, Persona에 `artifacts: [{name, mention_count}]`(패키지 값 그대로).
- 오래된(stale) 결과에서 "페르소나 만들기"는 `fresh: true`로 보낸다(C1).
### D-313 인사이트를 채팅 수정 · 되돌리기로 바꾸면 그 인사이트의 컨셉은 "다시 만들기 필요"로 표시하고 화면에서 숨긴다 · 판단 (Claude, 리뷰 I5 · Codex 3)
- 컨셉에 `insight_revision`과 `context_ids`를 기록하고, 현재 인사이트와 다르면 `outdated: true`. 다시 만들기 전까지 8-F는 안내 문구만.
### D-314 단계 결과가 stale이면 채팅 · 되돌리기 · 확정도 409 `stale` · 판단 (Claude, Codex 5)
### D-315 구역 이름은 화면 전체에서 "A Exciting"처럼 글자 + 설계의 영문 이름 하나로 통일 · 판단 (Claude, 리뷰 Minor)
### D-316 보류: "8부터 다시" 버전 선택 UI(② 소유 파일, T17에서), 인사이트 도출 프롬프트 크기 축소(실세션 확인 D-247 때 측정 후) · 판단 (Claude)
### D-317 known_ki_id만 바뀐 인사이트 수정은 컨셉을 무효화하지 않음 · 판단 (Claude, 재리뷰 2 m4)
- 컨셉은 Known 여부와 무관한 제목 · pain point · Context로 만든다. 배지는 인사이트 쪽에서만 바뀐다.

## 브라우저 QA 1회차 (2026-10-02)

### D-318 QA용 가짜 LLM은 프롬프트의 Context ID · 근거 번호로 유효한 응답을 만든다(카드 · 요약 · 인사이트 · 컨셉) · 판단 (Claude)
- 정적 응답 파일은 Persona 1개에만 맞아 QA에서 나머지 Persona 카드 · 컨셉이 "실패"로 나왔다(제품 결함 아님). QA-P6(실패 Persona)는 실패용 Persona 하나만 일부러 실패하게 한다.
