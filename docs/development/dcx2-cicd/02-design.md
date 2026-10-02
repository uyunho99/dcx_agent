# 02 · 설계 — DCX 2.0 CI/CD

- 실행: `dcx2-cicd` · 승인된 기획: `01-brainstorm.md`(제품 승인 2026-10-02)
- 결정: `decision-log.md` D-400~D-405 (이 설계에서 D-406~ 추가, 모두 "제안")
- 화면(UI) 변경: **없음.** 사용자에게 보이는 것은 기존 화면 그대로이고, 배포 상태는 API(`/health`)와 로그 파일로 본다. 그래서 디자인 리뷰(plan-design-review)는 해당하지 않는다.

## 1. 전체 구조

```
GitHub (공개 저장소 uyunho99/dcx_agent)
  PR · main 푸시 ──► Actions: .github/workflows/ci.yml
                       job backend : pytest backend/tests -q
                       job frontend: npm ci · lint · test · build
                                │
맥미니 (들어오는 연결 없음)       │ 공개 API로 결과만 읽음 (토큰 없음)
  launchd ai.person-a.dcx-agent.deploy (2분마다)
     └─ ~/srv/dcx-agent/ops/deploy.sh
          fetch main → CI 초록? → 스냅샷 → 릴리스 빌드 → current 교체
          → api · web 재시작 → /health 확인 → (실패 시) 롤백
  launchd ai.person-a.dcx-agent.api  (KeepAlive) → run-api.sh → uvicorn 127.0.0.1:8400
  launchd ai.person-a.dcx-agent.web  (KeepAlive) → run-web.sh → next start 127.0.0.1:3400
```

### 1.1 저장소에 새로 들어가는 파일

| 파일 | 역할 |
|---|---|
| `.github/workflows/ci.yml` | CI |
| `ops/macmini/env.sh` | 경로 · 포트 · 저장소 이름 상수 |
| `ops/macmini/lib.sh` | 공용 함수(로그, 잠금, 릴리스 전환, 재시작, 상태 확인, 스냅샷, 정리) |
| `ops/macmini/deploy.sh` | 폴러(launchd 2분) — 자동 배포 |
| `ops/macmini/dcxctl` | 수동 명령: `status` · `deploy [sha]` · `rollback` |
| `ops/macmini/run-api.sh` · `run-web.sh` | launchd KeepAlive 잡의 진입점 |
| `ops/macmini/install.sh` | 첫 설치(사용자가 `sudo`로 실행) |
| `ops/macmini/launchd/ai.person-a.dcx-agent.{deploy,api,web}.plist` | LaunchDaemon 정의(설치 때 경로 채움) |
| `backend/app/main.py` (수정) | `/health`에 `release` 필드 추가 |
| `backend/tests/ops/` | 스크립트 테스트(임시 폴더 · 가짜 명령) |
| `scripts/deploy.sh` (EC2용) | 손대지 않음. 머리에 "1.0 EC2용, 2.0은 ops/macmini" 한 줄만 추가 |

## 2. CI (`.github/workflows/ci.yml`)

- 트리거: `pull_request`(대상 main) · `push`(main). `concurrency: ci-${{ github.ref }}`, PR은 `cancel-in-progress: true`, main 푸시는 취소하지 않음(배포 판단이 그 결과를 기다림).
- 권한: `permissions: contents: read`. 비밀값 사용 없음.
- `backend` job: ubuntu-latest · Python 3.12 · `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`(pip 캐시) · `python -m pytest backend/tests -q -p no:cacheprovider`. 환경: 테스트가 이미 가짜 백엔드로 도는지 그대로 둔다(키 없음).
- `frontend` job: ubuntu-latest · Node 26(맥미니와 같음, D-406) · `npm ci --prefix frontend`(npm 캐시) · `lint` · `test` · `build`.
- 이름: 워크플로 파일 이름 `ci.yml`로 찾는다(이름 문자열로 찾지 않음 — internal-app이 겪은 문제).
- main 브랜치 보호(머지 전 CI 필수)는 GitHub 설정이라 이 작업에서 바꾸지 않는다. 필요하면 사용자가 켠다(backlog).

## 3. 맥미니 배포 폴더

```
~/srv/dcx-agent/
  repo/                    git clone (fetch만, 체크아웃은 하지 않음)
  releases/<sha>/          git archive로 푼 커밋별 트리 + frontend 빌드 산출물
     .env -> ../../shared/app.env
     backend/.venv -> ../../../shared/venvs/<requirements 해시>
  current -> releases/<sha>
  shared/
    app.env                키(권한 600). 개발 폴더 .env 복사본
    runtime.env            실행 설정(STORAGE · LOCAL_DATA_DIR · LABEL_GPT_BACKEND · JEV_BACKEND · CORS_ORIGINS · NEXT_PUBLIC_API_URL)
    data/                  데이터(LOCAL_DATA_DIR)
    venvs/<hash>/          requirements.txt 내용 해시별 가상환경 (D-407)
    snapshots/<UTC시각>-<sha>/sessions   배포 직전 세션 스냅샷 (최근 5개, D-403)
    deploy-history         배포 이력(한 줄에 sha, 맨 아래가 current)
    last-failed-sha        빌드 · 상태 확인에 실패한 커밋
    deploy.lock/           동시 실행 잠금(pid)
  ops/                     install.sh가 복사해 둔 운영 스크립트(릴리스 밖, 롤백과 무관)
  logs/  deploy.log · api.log · web.log
```

- 지금 손으로 띄운 `~/srv/dcx-agent/repo`(작업 트리 있는 clone)는 설치 때 `releases/2ba66eb…`로 옮겨 첫 릴리스로 삼는다(재빌드 없이). 이후 `repo/`는 fetch 전용으로 다시 만든다.

## 4. 배포 판단 (`deploy.sh`, 2분마다)

1. 잠금(`shared/deploy.lock`) — 다른 deploy · rollback이 돌면 이번 틱은 쉰다. 주인이 죽은 잠금은 가져온다.
2. `git -C repo fetch origin main` → `sha = origin/main`.
3. `sha == current` → 끝(로그 안 남김). `sha == last-failed-sha` → 끝.
4. CI 결과: `GET https://api.github.com/repos/uyunho99/dcx_agent/actions/workflows/ci.yml/runs?head_sha=<sha>&event=push&branch=main&per_page=1` (토큰 없음, D-408).
   - `completed/success` → 5로.
   - `completed/failure|timed_out|startup_failure` → `ci-failed` 로그(같은 시도는 한 번만), 끝.
   - 진행 중 · 없음 · 취소 → 대기. 30분 넘게 그러면 `ci-stuck` 로그 한 번.
   - API 오류(제한 · 네트워크) → `ci-unknown` 로그, 끝(배포 안 함).
5. 릴리스 빌드(이미 빌드된 릴리스면 건너뜀):
   - `git archive <sha> | tar -x -C releases/<sha>`, `.env` 링크.
   - 가상환경: `sha256(backend/requirements.txt)` 해시 폴더가 없으면 `python3.12 -m venv` + `pip install -r`(+ 실패 시 그 폴더 삭제). 있으면 링크만.
   - 프론트: `runtime.env`의 `NEXT_PUBLIC_*`만 실어 `npm ci` · `npm run build`. 서버 키(app.env)는 빌드 환경에 싣지 않는다.
   - 실패 → `build-failed` 로그 · `last-failed-sha` 기록 · 떠 있던 버전 유지.
6. 세션 스냅샷: `shared/data/sessions` → `shared/snapshots/<UTC>-<sha>/sessions` (`cp -a`, 지금 1.3MB). 최근 5개 외 삭제.
7. `current` 원자 교체(`ln -sfn` 임시 링크 + `mv -fh`).
8. api · web 재시작: 각 pid 파일과 포트를 쥔 프로세스를 TERM → 20초 → KILL. launchd KeepAlive가 새 `current`로 다시 띄운다. **돌던 작업은 중단됨 처리(D-401)** — 백엔드가 기동 때 기존 로직으로 `interrupted`를 기록한다.
9. 상태 확인(120초): `GET 127.0.0.1:8400/health`가 `{"status":"ok","release":"<sha>"}`이고 `GET 127.0.0.1:3400/pipeline/start`가 200.
10. 성공 → `deploy-history`에 추가, `deployed` 로그, 오래된 릴리스 정리(이력 최근 3개 + current만 남김).
11. 실패 → 롤백(5장).

## 5. 롤백

- 자동(9 실패): 직전 릴리스로 `current` 교체 → 세션 복원(지금 `sessions`를 `snapshots/<UTC>-<sha>-failed/`로 옮기고 이번 배포 직전 스냅샷을 `sessions`로 복사) → 재시작 → 상태 확인.
  - 직전 버전 정상 → 실패한 릴리스 삭제, `unhealthy` 로그(`rolled_back_to`, `snapshot`).
  - 직전 버전도 실패 → `unhealthy-both` 로그. `last-failed-sha` 유지. 사람이 원인을 본 뒤 그 파일을 지우면 다시 시도.
  - 직전 버전이 없음(첫 배포) → `unhealthy` 로그, 롤백 없음.
- 수동: `dcxctl rollback` — 이력에서 하나 전 릴리스 + 그 릴리스로 배포하기 직전 스냅샷(같은 규칙)으로. `last-failed-sha`에 지금 커밋을 적어 폴러가 다시 올리지 않게 한다. 다시 올리려면 `dcxctl deploy <sha>`.

## 6. 실행 잡

| 잡 | 진입점 | 내용 |
|---|---|---|
| `…api` | `run-api.sh` | `app.env` · `runtime.env` 싣고 `cd current/backend`, `DCX_RELEASE_SHA=<current sha>`, `exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8400`. pid 파일 기록 |
| `…web` | `run-web.sh` | `runtime.env`의 `NEXT_PUBLIC_*`, `PORT`만 싣고 `cd current/frontend`, `exec node_modules/.bin/next start -H 127.0.0.1 -p 3400` |
| `…deploy` | `deploy.sh` | `StartInterval 120`, `RunAtLoad` |

- 세 잡 모두 LaunchDaemon(`/Library/LaunchDaemons`), `UserName`=사용자, `HOME` 지정 — `codex exec` 라벨러가 사용자 홈의 Codex 로그인을 그대로 쓴다.
- 127.0.0.1에만 묶는다(밖에서 접속은 제외 범위).

## 7. 데이터 · API 변경

- `GET /health` → `{"status": "ok", "release": "<DCX_RELEASE_SHA 또는 \"dev\">"}`. 기존 `status` 필드는 그대로(호환).
- 그 밖의 백엔드 · 프론트 코드는 바꾸지 않는다.

## 8. 권한 · 비밀값

- GitHub 쪽 비밀값 없음. 맥미니는 공개 API를 토큰 없이 부른다(2분 간격 = 시간당 30회, 제한 60회).
- `shared/app.env` 권한 600, 빌드 환경 · 로그 · 명령 인자에 키를 싣지 않는다. 로그는 결정 · sha · 시각만.
- `install.sh`만 `sudo`가 필요하다(LaunchDaemon 등록). 사용자가 직접 실행한다(D-402). 스크립트는 무엇을 할지 먼저 출력하고 `y`를 받아야 진행.

## 9. 설치 (`install.sh`)

1. 확인 출력: 만들 경로, 등록할 잡 3개, 내릴 프로세스(3400 · 8400을 쥔 손으로 띄운 프로세스), 건드리지 않는 것(3310 · 3311 · 8310 · 8311 · 3000).
2. 지금 `repo/`를 첫 릴리스로 옮김(3장), `shared/runtime.env` 생성(지금 손 실행 값 그대로).
3. `ops/macmini/*` → `~/srv/dcx-agent/ops/` 복사, plist에 경로 채워 `/Library/LaunchDaemons`에 두고 `launchctl bootstrap system`.
4. 손으로 띄운 3400 · 8400 프로세스 종료 → 잡이 뜨는지 상태 확인.
5. 운영 스크립트가 바뀌어도 폴러가 스스로 덮어쓰지 않는다. 새 릴리스의 `ops/macmini`가 설치본과 다르면 `deployed` 로그에 `ops_outdated: true` — 사용자가 `install.sh`를 다시 실행.

## 10. 실패 상태 요약

| 상황 | 결과 | 사용자가 볼 곳 |
|---|---|---|
| CI 빨강 | 배포 안 함, 떠 있던 버전 유지 | GitHub PR · Actions, `deploy.log` `ci-failed` |
| CI 30분 넘게 안 끝남 | 대기 | `ci-stuck` |
| GitHub API 오류 | 이번 틱 건너뜀 | `ci-unknown` |
| 맥미니 빌드 실패 | 유지, 그 커밋 재시도 안 함 | `build-failed` |
| 새 버전 상태 확인 실패 | 직전 버전 + 스냅샷으로 롤백 | `unhealthy` |
| 직전 버전도 실패 | 실패 표시 유지, 사람 확인 | `unhealthy-both` |
| 배포 중 긴 작업 실행 중 | 중단됨, 화면에서 이어서 하기 | 기존 화면 |
| 재부팅 | 로그인 없이 세 잡이 뜸 | `/health` |

## 11. 테스트 설계 (계획에서 Task로)

- **CI 파일:** YAML 구조 검사(트리거 · 권한 · 명령) — `backend/tests/ops/test_ci_workflow.py`(PyYAML로 읽어 단언).
- **배포 스크립트:** `backend/tests/ops/test_deploy.py` — 임시 `APP_ROOT`, 로컬 bare git 저장소를 `origin`으로, 가짜 `curl`(CI 응답 · 상태 확인)과 가짜 빌드 명령을 `PATH`에 두고 `deploy.sh`를 실행. 상황별: up-to-date, ci 대기 · 실패 · stuck, 빌드 실패, 성공(교체 · 이력 · 정리), 상태 확인 실패 → 롤백 + 세션 복원, 둘 다 실패, 잠금 충돌, `dcxctl rollback` · `status`.
  - 스크립트는 `DCX_BUILD_CMD` · `DCX_RESTART_CMD` 같은 테스트 전용 환경 변수로 무거운 단계를 바꿔 끼울 수 있게 만든다(운영 기본값은 실제 명령).
- **`/health`:** `release` 필드 — `DCX_RELEASE_SHA` 있음 · 없음.
- **실기 확인(QA):** 맥미니에서 설치 → PR 머지 → 자동 배포 · 롤백(일부러 상태 확인이 실패하는 커밋은 `DCX_FORCE_UNHEALTHY` 같은 테스트 스위치로) · 재부팅 후 기동.
