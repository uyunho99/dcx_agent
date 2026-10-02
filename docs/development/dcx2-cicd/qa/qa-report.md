# QA 보고서 — dcx2-cicd (2026-10-02)

- 브랜치 `feature/dcx2-cicd` · PR uyunho99/dcx_agent#6 (draft)
- QA 루트 `~/srv/dcx-agent-qa` · api 8401 · web 3401 · 사용자 LaunchAgent `ai.person-a.dcx-agent-qa.{deploy,api,web}`

| ID | 결과 | 근거 |
|---|---|---|
| QA-1 GitHub CI | PASS | PR #6 커밋 `1810ab9`: backend 7m34s pass(우분투에서 `-c constraints.txt` 설치 성공 포함) · frontend 52s pass. 이전 커밋 `c3221fc`도 둘 다 pass |
| QA-install (QA 루트) | PASS (2회차) | 1회차: main `2ba66eb`에 `constraints.txt`가 없어 빌드 실패 → 실제 결함으로 수정(수정 3, constraints 없는 커밋은 해시 분리 + `-c` 없이 설치). 설치 실패 시 hold 파일 · LaunchAgent 잔재 없음 확인. 2회차: 첫 릴리스 정식 빌드 · LaunchAgent 3개 등록 · `/health` ok · 3401 200 · `dcxctl status` maintenance clear · history 1줄 · `deployed installation:true` |
| QA-4 dcxctl status | PASS | 위 출력 |
| QA-6 운영 install --dry-run | PASS | LaunchDaemons 3개, 내릴 포트 3400 · 8400만, 건드리지 않음 3000 · 3310 · 3311 · 8310 · 8311, `NEXT_PUBLIC_API_URL=https://dcx-api.person-a.ai`, `CORS_ORIGINS=https://dcx.person-a.ai,http://localhost:3400` |
| 키 유출 | PASS | QA 루트 `logs/` · `releases/*/frontend/.next`에서 app.env 키 값 0건 |
| 다른 서버 | 주의 | 3000 · 3310 · 8310 · 3400 · 8400 · 3401 · 8401 응답. **3311 · 8311(사용자 데모)이 17:30 이후 종료됨** — QA 로그 · 테스트 포트에 근거 없음, 원인 미확인. 공개 주소는 이미 3400 · 8400이라 공개 사이트 영향 없음 |
| QA-2 · QA-3 · QA-5 (실제 자동 배포 · 롤백 · 빌드 실패) | 머지 후 | 수동 배포도 "main 푸시 CI 초록"만 통과시키므로 PR 커밋은 머지 전 배포할 수 없다(설계대로). 단위 테스트 120개(bash 3.2 포함)가 해당 경로를 덮음. 머지 뒤 QA 루트 폴러가 머지 커밋을 스스로 올리는지와 `dcxctl rollback`을 확인 |
| QA-7 운영 설치 · 재부팅 | UAT | 사용자 sudo |

## 발견 · 처리
- 운영 install 기본값이 localhost → 공개 사이트 깨짐: 수정 3에서 공개 주소 기본값 + 기존 runtime.env 보존.
- constraints 없는 옛 커밋 빌드 실패: 수정 3.
- 설치 중 상태 확인 대기 동안 `error` 로그가 여러 줄 남음(ERR trap 중복, 보류된 minor).
