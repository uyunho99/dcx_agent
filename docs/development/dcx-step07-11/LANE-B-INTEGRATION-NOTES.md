# Lane B (T6–T11) 통합 노트

실행 ID `dcx-step07-11` · 하네스(development-harness-native)로 T6, T7, T8, T9→T10, T11을
골든 픽스처(`backend/tests/fixtures/golden/`) 기반으로 병렬 개발 → 독립 리뷰 → 리뷰에서
발견된 결함 수정 → 재검토까지 완료한 결과를 통합한 브랜치다.

## 결과 요약

| Task | 내용 | 빌드 | 독립 리뷰 | 비고 |
|---|---|---|---|---|
| T6 | 07 군집 → Touch Point | ✅ `17f13f7` | **PASS** | — |
| T7 | 08 SNA → 페르소나 v2 | ✅ `6a1221b` | **PASS** | 아래 "알려진 통합 이슈 1" 참고 |
| T8 | 09 Evidence Package | ✅ `7f3af40` → fix `fb9f6f3` | 재검토 후 조건부 수용 | 아래 "알려진 제한사항 1" |
| T9 | 10-A CAM 등급 판정 | ✅ `e3140bb` | fix `34ffd81` → **PASS** | — |
| T10 | 10-B 기회 영역 집계 | ✅ `2b67350` | fix `34ffd81` → **PASS** | — |
| T11 | 11-A/B Insight/Concept | ✅ `88cd18c` → fix `da6afc6` → fix `969b6dd` | 3회 재검토 후 조건부 수용 | 아래 "알려진 제한사항 2" |

전체 백엔드 테스트(`backend/tests/`, T0 골든 픽스처 계약 테스트 포함) **144개 전부 통과**
(이 통합 브랜치에서 재확인, `python3 -m pytest tests/ -q`).

각 Task는 별도 git worktree + 독립 Codex 세션에서 구현되고, 구현하지 않은 별도 Codex 세션이
리뷰했다. Controller(본 세션)가 매 커밋 전 실제로 테스트를 재실행해 보고서를 검증했다.

## 알려진 제한사항 (수정하지 않고 문서화만 하기로 결정 — 2026-09-19 사용자 확인)

### 1. T8 — Evidence 수집은 T4(레인 A) 없이는 항상 거부된다

`evidence.collect()`는 새로 파생된 Action의 `context_id`를 검색 백엔드에 동기화한 뒤에만
검색한다(`app/services/pinecone_svc.update_context_mappings`). 이 동기화 함수는 현재
`NotImplementedError`를 던지는 명시적 스텁이다 — 실제 구현은 T4(임베딩/Pinecone 메타 확장,
레인 A 소관)의 몫이며, 이 저장소 어디에도(레인 A의 실제 작업 포함) 아직 존재하지 않는다.

**이건 결함이 아니라 계획의 `QA-NEG-008`("Pinecone 부재 시 요청 거부, 빈 결과를 성공
처리하지 않음")이 요구하는 정확한 동작이다.** T4가 구현되어
`update_context_mappings(sid, mappings)`가 실제로 문서-컨텍스트 매핑을 인덱스에 반영하게
되면 Evidence 수집은 별도 코드 변경 없이 바로 동작한다.

**통합 시 할 일**: T4 구현자가 `backend/app/services/pinecone_svc.py`의
`update_context_mappings` 함수 시그니처(`sid: str, mappings: list[dict]`, 각 mapping은
`doc_id`·`cluster_id`·`persona_id`·`context_id`)를 그대로 채우거나, 다른 이름/시그니처를
쓴다면 `backend/app/services/evidence.py`의 호출부와 맞춰 조율해야 한다.

### 2. T11 — 동시 확정(confirm)이 비-local 저장소에서 아주 좁은 확률로 유실될 수 있다

`insight.py`의 확정 로직은 두 라운드에 걸쳐 동시성 버그를 고쳤다:

1. (fix 1) 문장을 소수점(`3.5분`)에서 잘못 쪼개던 버그, 같은 프로세스 내 동시 확정 유실 →
   수정 및 확인 완료.
2. (fix 2) 실제 배포(`scripts/systemd/dcx-backend.service`, `--workers 2`)가 여러 OS
   프로세스로 뜨는데 최초 수정이 `threading.Lock`(프로세스 내부만 유효)이었던 문제 →
   `STORAGE=local`일 때는 sid별 `flock`으로 프로세스 간 직렬화, 그 외 백엔드는 낙관적
   재시도(최대 5회, 쓰기 전후 값 비교)로 전환.

**3번째 재검토에서 발견된, 아직 남은 문제**: `backend/app/services/s3.py`(모든 Task가
공유하는 저장소 추상화 파일, 특정 Task 소유가 아님)에는 compare-and-swap(조건부 쓰기)
기능이 전혀 없다. 낙관적 재시도는 이 좁은 창(window)을 줄이지만 완전히 없애지는 못한다 —
두 프로세스가 겹치는 타이밍에 검증까지 마쳤는데 그 사이에 다른 프로세스가 이미 썼다면,
드물게 한쪽 확정 내용이 예외 없이 조용히 사라질 수 있다. **로컬 개발(`STORAGE=local`)은
`flock`으로 안전하다.** 실제 S3 백엔드에서만 이 좁은 레이스가 남아 있다.

**근본 수정에 필요한 것**: `backend/app/services/s3.py`에 진짜 조건부 쓰기(예: S3의
`IfMatch`/`IfNoneMatch` 헤더 활용, 또는 DynamoDB 등 별도 락 저장소)를 추가하는
크로스커팅 인프라 작업 — 특정 Task 하나가 임의로 공유 파일을 고칠 범위가 아니라고 판단해
후속 작업으로 남긴다. 사용자 확인: "일단 문서화만 해놓고" 진행.

## main.py 라우터 등록 (통합 시 필요)

세 개의 신규 라우터가 아직 `backend/app/main.py`에 등록되어 있지 않다(공유 파일이라 각
Task가 직접 건드리지 않고 노트로만 남겼다):

```python
from app.routers import evidence, cam, insight

app.include_router(evidence.router)
app.include_router(cam.router)
app.include_router(insight.router)
```

## 이 브랜치에 아직 포함되지 않은 것

- 레인 A(T1 수집 레코드, T2 마이그레이션, T3 known_insights, T4 임베딩/Pinecone 메타, T5
  06 산출 계약) — 별도 세션에서 진행 중이며 이 브랜치와 독립적으로 병합되어야 한다.
- T12(프롬프트 외부화·어드민), T13(프론트엔드 화면).
- 하네스의 독립 브라우저 QA 단계(코드 리뷰까지만 완료, 실제 화면 QA는 미실행).
