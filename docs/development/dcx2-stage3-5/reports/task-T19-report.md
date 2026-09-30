# T19 구현 보고서

## 범위와 기준

- `.superpowers/sdd/03-plan/task-T19-brief.md`를 먼저 읽고, 지정된 `02-design-r2.md` 5.7 및 목업 `s6`를 확인했다.
- 학습 화면과 모델 저장소를 구현했다. D1에 따라 단일 모델 만들기 버튼을 만들지 않았으며 저장소에서도 `kind: distilled` 행을 제외한다.
- 수정: `frontend/src/app/pipeline/training/page.tsx`
- 신규: `frontend/src/components/train/ModelRepository.tsx`, `TrainingResult.tsx`, `trainingView.ts`, `trainingView.test.ts`
- 별도 요청에 따라 이 보고서를 작성했다. 다른 작업자의 파일, T16 공유 API·타입·label 컴포넌트는 수정하지 않았다. 커밋하지 않았다.

## 구현 내용

- 기존 LSTM/CNN/GRU/Claude 학습 화면과 전체 세션 저장 호출을 제거했다.
- T16 `startTraining`, `getTrainingStatus`, `getModels`, `exportTraining`을 사용하며 선택된 세션 버전을 모든 관련 호출에 전달한다.
- 라벨링 개요는 T16 `getLabelOverview`로 읽고, 내보내기 등급 표시에 T16 `LevelBadge`를 재사용한다.
- 학습 전 제목·안내·채택 라벨 수·검수 대기 수·학습 시작·모델 없이 내보내기를 제공한다. 라벨 0건이면 지정된 빈 상태 문구를 표시하고 실행을 막는다.
- 5초 간격으로 상태를 갱신한다. 타이머는 요청 종료 후 예약하므로 느린 요청이 중첩되지 않는다. 정리 시 타이머를 해제하고 이전 요청 결과를 무시한다.
- 학습과 추론 중에는 MLP 3개와 선형 1개의 진행 막대를 표시한다. 완료된 학습 멤버는 100%, 미제공 진행률은 indeterminate로 표시한다.
- 결과는 넓은 InsightCard와 헤드별 지표 카드로 구성했다. 모델 ID, 학습 건수, 등급 정확도, 임베딩 모델·차원, 규칙·질문 버전, 생성 시각, 헤드별 F1·보정 오차를 표시한다.
- 실제 멤버별 정확도가 4개 모두 있는 경우만 MLP 3개 평균과 선형 1개의 정확도 차이를 %p로 표시한다.
- 헤드 표본 부족(30건 기준), 작업 중단·실패, 불러오기 실패, 저장 실패, 읽기 전용 상태를 처리한다. 감시 괴리율이 15%를 초과하면 지정된 안내를 표시한다.
- 저장소는 모델·앙상블 종류·학습한 세션·한줄 정의·학습 건수·등급 정확도·임베딩·추가 학습 동작을 제공한다. 현재 모델을 표시하고 다른 임베딩 모델은 흐리게 표시하며 선택 동작 대신 정확한 사유 문구를 보여 준다.
- 추가 학습은 선택 모델 ID를 `parent`로 전달한다. 기존 학습셋이 없는 모델은 해당 동작을 비활성화한다.
- 파란 주요 버튼은 학습 전 학습 시작, 학습 완료 후 저장하고 클러스터링으로 중 하나만 표시한다. 다시 학습·추가 학습·모델 없이 내보내기는 보조 동작이다.
- 저장 순서: 전용 export API → `PATCH /session`의 `step: clustering` → 로컬 단계 갱신 → 클러스터링 화면 이동. 중간 실패 시 이동하지 않는다. `training.exportRef`는 전용 export API가 저장한다.
- 읽기 전용·버전 충돌·작업 진행 중에는 변경 동작을 막는다. 즉시 ref 잠금으로 중복 클릭을 막고 세션/버전 변경 시 화면 상태를 새로 만든다. 시작 이전에 발행된 폴링 응답이 새 작업 상태를 덮지 않도록 세대 번호를 사용한다.

## 실제 API 계약에 따른 한계

백엔드는 읽기만 했으며 소유권 범위 밖이므로 변경하지 않았다. 목업 예시 숫자를 실제 데이터처럼 하드코딩하지 않았다.

1. 학습 전 API에는 정확한 학습 가능 건수 및 합의/사람별 분해 값이 없다. `Overview.accepted`는 별도의 채택 라벨 수로 표시하며, 합의 건수나 실제 학습셋 크기로 바꾸어 부르지 않는다. 281,410 / 280,800 / 610은 목업 예시이며 실제 값으로 만들지 않았다. 실제 학습 완료 건수는 모델 metadata의 `n`을 사용한다.
2. 학습 worker는 features/train/saving/done의 전체 진행률만 제공한다. 멤버별 진행률을 가정해 만들어내지 않는다. 네 개 멤버 막대는 진행 중 표시이며 학습 완료 후 100%로 표시한다.
3. 모델의 `metrics.grade_accuracy`는 `evaluation_split: validation` 기준이다. 목업의 감사 정답 150건 기준 정확도 및 같은 기준의 Jev 대비 수치는 제공되지 않아 `검증셋 기준`을 명시한다. Jev 대비와 멤버 불일치 비율은 확인 불가로 표시한다.
4. 헤드별 지표와 MLP/선형 차이는 실제 metadata에서 계산한다. null/누락/비수치 지표를 0이나 성능 추정치로 대체하지 않는다.
5. 실서비스 워커를 실행한 end-to-end 검증 및 브라우저 시각 QA는 하지 않았다. 사용자 지시대로 브라우저 스크린샷은 생략했다. JSX·타입·상태 로직과 production build를 확인했다.

## 테스트 우선 작성

- `trainingView.test.ts`를 먼저 작성한 뒤 실행해 모듈 부재로 실패하는 것을 확인했다.
- 표시/상태 로직을 구현한 뒤 5개 테스트가 통과했다.
- 저장 순서 테스트를 먼저 추가해 `exportAndAdvance is not a function` 실패를 확인한 뒤 함수를 구현했다.
- T19 테스트 6개: 누락·NaN·문자형 수치 처리, 추론 완료 전 저장 차단/재학습 진행 상태, 중단 워커 상태, MLP/선형 비교, 증류 행 제외, export/PATCH/이동 순서 및 실패 시 이동 금지.

## 검증 결과

- `npm --prefix frontend test -- --run`: 최종 **31개 파일 / 169개 테스트 통과**. 첫 실행에서는 병렬 T17 작업의 `components/prep/prep.test.ts`가 아직 없는 `./prep` 모듈을 참조해 실패했으며, 해당 파일을 수정하지 않고 재실행한 최종 결과는 통과했다.
- `npm --prefix frontend run lint`: **통과**, 오류·경고 없음.
- `npx --prefix frontend next build --webpack`: 저장소 루트에서 실행하면 Next가 루트를 프로젝트로 해석하여 `Couldn't find any pages or app directory`로 실패한다. `--prefix`는 Next의 프로젝트 디렉터리를 지정하지 않는다.
- `npx --prefix frontend next build --webpack frontend`: **통과**. webpack 컴파일, TypeScript, 14개 정적 페이지 생성 완료. `/pipeline/training` 포함.
- 실행 중 Node의 기존 `module.register()` deprecation 경고만 관찰했다.

## 컨트롤러 인계

위 소유 파일과 보고서만 커밋 대상이다. 다른 작업자가 병렬 편집한 변경은 건드리지 않았다. 추가 API 필드를 제공할 후속 작업이 있으면 학습 전 정확한 건수, 멤버별 진행률, 감사 기준 비교, 멤버 불일치 비율을 채울 수 있다.
