# 브라우저 QA (코드 c3ed4c0, 2026-10-03)

환경: 운영 세라젬 세션(s89d92341…, 문서 87,143건, 판정 0건) **복사본**(스크래치 폴더), 백엔드 8320(`JEV_BACKEND=fake`, `LABEL_GPT_BACKEND=fake`), 화면 3320(`next dev`). URL `http://localhost:3320/pipeline/labeling`. 운영 원본은 읽기만 함.

| ID | 결과 | 근거 |
|---|---|---|
| S1 안내 · GPT 카드 하나 | PASS | 시작 전 화면 텍스트: "Jev 미연결 · GPT 단독 판정" 배너, 전량 판정 카드에 GPT만, Jev 비용 문구 없음, 불일치율 "—", Jev 정확도 열 전부 "—". |
| S2 최종 라벨 · 4단계 완료 | PASS | 시작 → 응답 workers `['gpt']`, GPT 87,143건 done → final `gpt_only/accepted` 87,143행(confidence NULL 87,143), session `labeling.status=done`, `labelerMode=gpt_only`, `judgeRuns={gpt}`. 사이드바 "5. 라벨링 완료". |
| S3 "—" 표시 | PASS(부분) | 불일치율 · Jev 정확도 "—" 확인. 판정 실패 문서가 0건이라 검수 카드 Jev 열은 화면에서 못 봄 → `queueView.test.ts`(null Jev → 모든 칸 "—")로 대체. |
| S4 Jev 제어 거부 | PASS | `POST /label/{sid}/judge/jev/resume` → 409 "Jev가 연결되지 않아 GPT 단독으로 판정합니다." |
| S5 학습 대상 포함 | PASS | 5단계 화면 "학습할 라벨 87,143건 · 검수 대기 0건", overview `trainable=87143`. |
| S6 교차 회귀 | PASS | `LABEL_FAKE_JEV_CROSS=true`로 재시작, 새 버전 v2(4단계부터) → `labelerMode=cross`, workers `['gpt','jev']`, GPT는 캐시 재사용으로 즉시 done, Jev 87,143 done → final agreed 87,143(accepted 44,253 · 불일치 42,890), 화면 배너 없음 · Jev/GPT 카드 둘 · Jev 비용 문구 · 불일치율 49.2%. |
| R3 모델 방식 안내 | 화면 확인 불가 | 이 데이터에 분류 모델이 없어 "분류 모델" 선택지 비활성. `labelerMode.test.ts`(model ⇒ 배너 없음)로 대체. |

스크린샷: 브라우저 창이 숨겨진 상태라 2차 QA는 페이지 텍스트 · API · DB 조회로 기록. 1차 QA(86ead3a)에서 S1 · S2 화면 스크린샷 확인.
