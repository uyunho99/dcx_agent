# DCX 2.0 CI/CD · 구현 계획 + QA 계획

> 구현은 Codex(`codex:codex-rescue`, `--wait --fresh`, 쓰기)에 위임하고 Claude는 분해 · 위임 · 리뷰 · 커밋만 한다(Codex 샌드박스는 worktree git 메타데이터에 쓸 수 없음). Task마다 RED → GREEN → 리팩터링, 보고서는 `docs/development/dcx2-cicd/reports/task-<ID>-report.md`.

**목표:** PR · main 푸시마다 GitHub Actions가 검증 명령 4개를 돌리고, 맥미니가 2분마다 main을 보다가 CI가 초록인 새 커밋을 `~/srv/dcx-agent`에 자동 배포 · 상태 확인 · 실패 시 롤백(세션 스냅샷 포함)한다. 서버 3개는 LaunchDaemon.
**설계:** `02-design.md` · 결정 `decision-log.md` D-400~D-416 · 기획 `01-brainstorm.md`(설계 차이: 폴링 1분 → 2분, D-408).
**설계와의 차이(엔지니어링 리뷰, 아래 Decision ledger):** 첫 릴리스는 손 clone 이전이 아니라 정식 빌드(F1) · 배포 순서는 중지 → 작업자 종료 → 스냅샷(+`work/`) → 교체 → 시작(F2 · F3 · F4) · 배포 단계 기록으로 중간 크래시 복구(F5) · 데몬 PATH 지정과 실행 파일 확인(F6) · `AUTHOR_SALT_PATH` 고정(F9) · 프론트 빌드 설정 해시와 `/sessions` 상태 확인(F10) · 의존성 `constraints.txt` 고정(R1).
**기술:** GitHub Actions(ubuntu-latest), bash(macOS 기본 bash 3.2 호환 · Linux에서도 테스트가 돌게), pytest(스크립트 테스트), launchd.

## 전역 제약
- 맥미니 로컬 전용. 서버는 127.0.0.1에만(D-410). 포트: api 8400 · web 3400.
- 배포 루트 기본값 `APP_ROOT=$HOME/srv/dcx-agent`. 모든 스크립트는 `APP_ROOT` 환경 변수로 바꿀 수 있어야 한다(테스트 · QA용).
- GitHub 비밀값 · 토큰 없음(D-408). 맥미니 키 `shared/app.env`는 빌드 환경 · 로그 · 명령 인자에 싣지 않는다.
- 사용자가 띄운 서버(3310 · 3311 · 8310 · 8311)와 internal-app(3000 · `~/srv/internal-app`)은 건드리지 않는다. 스크립트가 끝내는 프로세스는 api · web 잡의 pid 파일 자손과 **8400 · 3400 포트를 쥔 프로세스**뿐.
- 스크립트는 macOS 기본 `/bin/bash`(3.2)에서 돈다: 연관 배열 · `${var,,}` · `mapfile` 금지. GNU/BSD 차이(`mv -h` vs `mv -T`, `sha256sum` vs `shasum -a 256`, `date`)는 lib.sh의 작은 함수로 감싼다 — 테스트가 CI(우분투)에서도 돌아야 한다.
- 무거운 단계는 테스트 전용 환경 변수로 바꿔 끼운다: `DCX_BUILD_CMD`(릴리스 빌드), `DCX_RESTART_CMD`(api · web 재시작), `DCX_CI_API`(CI 조회 URL 앞부분), `DCX_HEALTH_API` · `DCX_HEALTH_WEB`(상태 확인 URL), `DCX_HEALTH_TIMEOUT`(초), `DCX_REPO_URL`, `DCX_API_PORT`(기본 8400) · `DCX_WEB_PORT`(기본 3400), `DCX_FORCE_UNHEALTHY_SHA`(그 sha의 상태 확인만 실패로 — QA 전용), `DCX_BASH`(테스트가 스크립트를 실행할 bash). 기본값은 운영 값.
- 로그는 `logs/deploy.log`에 한 줄 JSON `{"at","sha","decision", ...}`. decision 값: `up-to-date`(DRY 때만) · `known-failed` · `ci-pending` · `ci-stuck` · `ci-failed` · `ci-unknown` · `build-failed` · `deployed` · `unhealthy` · `unhealthy-both` · `rolled-back` · `error`.
- 기존 백엔드 1,507 · 프론트 356 테스트를 깨지 않는다.

## Review Focus
1. **배포 도중 맥미니 재부팅 · kill**(잠금 디렉터리 남음, `current.tmp` 남음) → 다음 틱이 죽은 잠금을 가져오고 정상 진행 → T2 `test_stale_lock_taken` · `test_leftover_current_tmp`.
2. **롤백 대상 릴리스가 정리돼 없음 / 이력 1줄뿐** → `dcxctl rollback`이 "되돌릴 버전 없음"으로 끝내고 아무것도 바꾸지 않음 → T3 `test_rollback_without_previous`.
3. **CI API가 HTML · 빈 응답 · 403(제한)** → `ci-unknown`, 배포 안 함 → T2 `test_ci_api_garbage`.
4. **requirements.txt가 바뀐 커밋** → 새 해시 가상환경을 만들고, 설치 실패 시 그 폴더를 지워 다음 시도가 깨진 환경을 재사용하지 않음 → T2 `test_venv_hash_and_cleanup`.
5. **스냅샷 대상 `sessions`가 없음(빈 데이터)** → 스냅샷 단계가 실패하지 않고 빈 스냅샷 · 롤백 시 그대로 → T2 `test_snapshot_without_sessions`.

## 파일 소유 · 의존 관계

| Task | 내용 | 의존 | 소유 파일(C 새로 · M 수정) |
|---|---|---|---|
| T1 | CI 워크플로 · `/health` release · 버전 고정 | — | C `.github/workflows/ci.yml` · M `backend/app/main.py`(`/health`만) · M `backend/requirements-dev.txt`(`pyyaml`) · C `backend/constraints.txt`(R1) · M `backend/tests/test_health.py`(F7) · C `backend/tests/ops/__init__.py` · C `backend/tests/ops/test_ci_workflow.py` · C `backend/tests/ops/test_health_release.py` |
| T2 | 배포 판단 · 빌드 · 교체 · 상태 확인 · 자동 롤백 | — | C `ops/macmini/env.sh` · C `ops/macmini/lib.sh` · C `ops/macmini/deploy.sh` · C `backend/tests/ops/conftest.py` · C `backend/tests/ops/test_deploy.py` |
| T3 | 수동 명령 · 실행 잡 · 설치 | T2 | C `ops/macmini/dcxctl` · C `ops/macmini/run-api.sh` · C `ops/macmini/run-web.sh` · C `ops/macmini/install.sh` · C `ops/macmini/launchd/ai.person-a.dcx-agent.{deploy,api,web}.plist` · C `ops/macmini/README.md` · M `scripts/deploy.sh`(머리 주석 1줄) · C `backend/tests/ops/test_dcxctl.py` · C `backend/tests/ops/test_install.py` |

- **웨이브:** 1차 T1 · T2(파일 서로소, 병렬) → 2차 T3.

## 계약

### lib.sh 함수 (T2 → T3)
```
log <decision> [extra-json]         # deploy.log에 한 줄 JSON 추가
current_sha                          # current 링크의 sha, 없으면 ""
acquire_lock / release (trap)        # shared/deploy.lock, 죽은 주인은 가져옴
switch_to <sha>                      # current 원자 교체(Darwin: mv -fh, Linux: mv -fT)
build_release <sha>                  # releases/<sha> 생성: git archive · .env 링크 · venv 해시 링크 · 프론트 빌드 (DCX_BUILD_CMD로 대체 가능)
snapshot_sessions <sha>              # shared/snapshots/<UTC>-<sha>/sessions, 최근 5개 유지, 경로 출력
restore_sessions <snapshot-dir>      # 지금 sessions → <UTC>-<sha>-failed 로 옮기고 스냅샷 복사
restart_services                     # api · web 재시작 (DCX_RESTART_CMD로 대체 가능)
wait_healthy <seconds> <sha>         # /health release == sha 이고 web 200
ci_status <sha>                      # success | failed:<id>:<attempt> | pending | unknown
prune_releases                       # 이력 최근 3개 + current만 남김
```
`deploy-history` 한 줄 형식: `<sha> <snapshot-dir 또는 ->`.

### dcxctl (T3)
- `dcxctl status` → `current`, `/health` 응답, `last-failed-sha`, `deploy-history` 마지막 3줄, `deploy.log` 마지막 5줄.
- `dcxctl deploy [sha]` → `DEPLOY_SHA=<sha>`로 deploy.sh 실행(없으면 origin/main). `last-failed-sha`가 그 sha면 지우고 시도.
- `dcxctl rollback` → 이력 하나 전 릴리스 + 지금 릴리스 배포 직전 스냅샷으로 복원, 재시작, 상태 확인, `last-failed-sha`에 롤백 전 sha, `rolled-back` 로그.

## Task별 단계

### T1 CI 워크플로 · `/health` release
- [ ] **RED** `test_ci_workflow.py`(PyYAML로 `.github/workflows/ci.yml` 읽음):
  - `test_triggers` — `on.pull_request.branches == ["main"]`, `on.push.branches == ["main"]`.
  - `test_permissions_read_only` — 최상위 `permissions == {"contents": "read"}`, 파일 어디에도 `secrets.` 문자열 없음.
  - `test_backend_job` — job `backend`: `runs-on: ubuntu-latest`, `actions/setup-python` with `python-version: "3.12"`, 단계 중 `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`와 `python -m pytest backend/tests -q -p no:cacheprovider`가 있다.
  - `test_frontend_job` — job `frontend`: `actions/setup-node` with `node-version: "26"`, `npm ci --prefix frontend`, `npm --prefix frontend run lint`, `npm --prefix frontend test`, `npm --prefix frontend run build` 순서.
  - `test_concurrency` — `concurrency.group`에 `github.ref` 포함, `cancel-in-progress`가 `${{ github.event_name == 'pull_request' }}`.
- [ ] **RED** `test_health_release.py` — `DCX_RELEASE_SHA=abc123` → `GET /health` = `{"status":"ok","release":"abc123"}`, 없음 → `"release":"dev"`.
- [ ] 실패 확인: `backend/.venv/bin/python -m pytest backend/tests/ops/test_ci_workflow.py backend/tests/ops/test_health_release.py -q -p no:cacheprovider` → FAIL.
- [ ] **GREEN** `ci.yml`(설계 2장, 설치는 `-c backend/constraints.txt`), `main.py` `/health`(`os.environ.get("DCX_RELEASE_SHA", "dev")`), `requirements-dev.txt`에 `pyyaml`, `test_health.py` 기대값 갱신(F7), `constraints.txt` = 개발 폴더 venv `pip freeze`(맥 전용 표시 R1). `test_backend_job`에 `-c backend/constraints.txt` 단언 추가.
- [ ] 통과: 위 명령 PASS + `backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` PASS.

### T2 배포 판단 · 빌드 · 교체 · 상태 확인 · 자동 롤백
- [ ] **RED** `conftest.py` 픽스처 `macmini(tmp_path)`: 임시 `APP_ROOT`(설계 3장 구조), 로컬 bare 저장소(커밋 2개: A · B, 저장소 루트에 `backend/requirements.txt` · `frontend/` 빈 폴더)를 `DCX_REPO_URL`로, `repo/`는 그 clone. 가짜 명령 폴더를 `PATH` 앞에 둠:
  - `curl` 가짜: URL이 `DCX_CI_API`면 환경 변수 `FAKE_CI`(JSON 문자열) 출력, 상태 확인 URL이면 `FAKE_HEALTH_<sha>` 또는 `FAKE_HEALTH` 값.
  - `DCX_BUILD_CMD` = `releases/<sha>/BUILT` 파일을 만드는 스크립트(`FAKE_BUILD_FAIL=1`이면 실패). `DCX_RESTART_CMD` = 호출 기록만. `DCX_HEALTH_TIMEOUT=3`.
  - 헬퍼 `run_deploy(env)` → (exit, deploy.log 마지막 줄 dict).
- [ ] **RED** `test_deploy.py`:
  - `test_up_to_date_silent` — current = origin/main → 로그 줄 없음(DRY에서만 `up-to-date`).
  - `test_ci_pending_then_stuck` — FAKE_CI in_progress → `ci-pending` 없이 대기(로그 없음), `ci-pending-since`를 31분 전으로 만든 뒤 → `ci-stuck` 한 번만.
  - `test_ci_failed_once` — failure → `ci-failed`, 같은 run 재실행 없이 두 번째 틱 → 로그 추가 없음, current 그대로.
  - `test_ci_api_garbage` — `<html>` · 빈 문자열 · `{"message":"API rate limit exceeded"}` → 각각 `ci-unknown`, current 그대로. (RF3)
  - `test_success_deploys` — CI success + 상태 확인 OK → current = B, `deploy-history` 마지막 줄 `B <스냅샷경로>`, 재시작 호출 1회, `deployed`, 스냅샷 폴더에 sessions 복사본.
  - `test_build_failed_marks_and_keeps` — FAKE_BUILD_FAIL → `build-failed`, `last-failed-sha` = B, current = A, 다음 틱 `known-failed`(로그 없음), `releases/B` 없음.
  - `test_unhealthy_rolls_back_with_snapshot` — B 상태 확인 실패, A는 정상 → current = A, sessions가 스냅샷 내용으로 복원, 배포 중 바뀐 sessions는 `*-B-failed/`에 있음, `unhealthy` + `rolled_back_to: A`, `releases/B` 삭제.
  - `test_unhealthy_both` — 둘 다 실패 → `unhealthy-both`, `last-failed-sha` = B, `releases/B` 남음.
  - `test_first_deploy_unhealthy` — current 없음 + 실패 → `unhealthy` + `rolled_back_to: null`.
  - `test_snapshot_keeps_five` — 배포 7번 후 스냅샷 5개. `test_snapshot_without_sessions` — sessions 없음 → 성공, 빈 스냅샷. (RF5)
  - `test_prune_keeps_three_plus_current`.
  - `test_stale_lock_taken` — `deploy.lock/pid`에 없는 pid → 진행. 살아 있는 pid(현재 테스트 프로세스) → 즉시 0 종료, 로그 없음. `test_leftover_current_tmp` — `current.tmp` 남아 있어도 교체 성공. (RF1)
  - `test_venv_hash_and_cleanup` — 운영 빌드 함수를 `DCX_PIP_CMD` 가짜로 돌려: 같은 requirements → 같은 `shared/venvs/<hash>` 재사용, 바뀐 requirements → 새 해시 폴더, 설치 실패 → 그 폴더 삭제 + `build-failed`. (RF4)
  - `test_secrets_not_in_build_env` — `app.env`에 `OPENAI_API_KEY=sk-test`를 두고 가짜 빌드가 환경을 덤프 → 덤프에 `sk-test` 없음, `NEXT_PUBLIC_API_URL` 있음. 로그 파일에도 `sk-test` 없음.
  - `test_runs_on_bash32_syntax` — macOS에서는 테스트 전체가 `/bin/bash`(3.2)로 스크립트를 실행(`DCX_BASH` 픽스처 기본 `/bin/bash`), 추가로 `declare -A` · `mapfile` · `${x,,}` grep (F11).
  - `test_stop_snapshot_switch_start_order` — 재시작 가짜가 호출 순서를 기록: `stop` → 스냅샷 → 교체 → `start` (F2). 스냅샷에 `work/` 포함(F4).
  - `test_workers_killed` — `releases/A/backend`를 cwd로 띄운 가짜 작업자(`sleep` 래퍼) → 배포 후 종료됨, `releases/` 밖 프로세스는 살아 있음 (F3).
  - `test_resume_after_crash_mid_switch` — `deploy-state`가 `switching B A <snap>`인 채 시작 → 상태 확인 → 실패면 A로 롤백, 성공이면 이력 기록 · 상태 파일 삭제 (F5).
  - `test_legacy_release_health` — `/health`에 `release`가 없는 응답(`{"status":"ok"}`)은 그 릴리스가 이력의 첫 줄일 때만 통과 (F1).
  - `test_frontend_rebuild_on_config_change` — `.build-config` 해시가 다르면 다시 빌드 (F10). 상태 확인은 `/health` · `/sessions` · web 200 셋 다.
  - `test_preflight_missing_binary` — `PATH`에서 `npm`을 빼면 `error` 로그 `missing: npm`, 아무것도 안 바뀜 (F6).
- [ ] 실패 확인: `backend/.venv/bin/python -m pytest backend/tests/ops/test_deploy.py -q -p no:cacheprovider` → FAIL.
- [ ] **GREEN** `env.sh`(PATH · 포트 · `AUTHOR_SALT_PATH` 기본값, F6 · F9) · `lib.sh` · `deploy.sh`(설계 4 · 5장 + 이 장부의 F1 · F2 · F3 · F5 · F10 보정, 계약 그대로). `DEPLOY_DRY_RUN=1`이면 결정만 로그하고 종료, `DEPLOY_SHA`로 대상 지정.
- [ ] 통과: `… -m pytest backend/tests/ops -q -p no:cacheprovider` PASS(macOS · Linux 둘 다 — Linux는 CI에서 확인).

### T3 수동 명령 · 실행 잡 · 설치
- [ ] **RED** `test_dcxctl.py`(T2 픽스처 재사용):
  - `test_status_prints` — current · release · last-failed · 이력 · 로그 줄이 출력에 있다.
  - `test_deploy_explicit_sha_clears_failed` — `last-failed-sha` = B 상태에서 `dcxctl deploy B` → 배포, `last-failed-sha` 비움.
  - `test_rollback` — 이력 A→B, current B → `dcxctl rollback` → current A, sessions = B 배포 직전 스냅샷, `last-failed-sha` = B, `rolled-back`.
  - `test_rollback_without_previous` — 이력 1줄 · 또는 이전 릴리스 폴더 없음 → 0 아닌 종료 + "되돌릴 버전이 없습니다", 아무것도 안 바뀜. (RF2)
- [ ] **RED** `test_install.py` — `install.sh --dry-run`(sudo · launchctl 호출 없이):
  - 출력에 만들 경로 · 잡 3개 · 내릴 포트(3400 · 8400)와 "건드리지 않음: 3000 3310 3311 8310 8311" 문구.
  - 렌더된 plist 3개(임시 폴더에 출력)가 `plutil -lint`(macOS) 또는 XML 파싱(Linux)을 통과, `UserName` · `HOME` · `APP_ROOT` 채움, api · web `KeepAlive` true, deploy `StartInterval` 120 · `RunAtLoad` true, `__` 자리표시자 없음.
  - `y` 이외 입력 → 아무것도 하지 않고 종료.
  - 첫 설치 계획 출력에 "main 머리 커밋을 정식 빌드해 첫 릴리스로 · 손 clone은 설치 후 삭제"(F1)와 `runtime.env`의 `AUTHOR_SALT_PATH`(F9) 포함.
  - `--qa` 모드: 라벨 `ai.person-a.dcx-agent-qa.*`의 LaunchAgent plist를 `~/Library/LaunchAgents`용으로 렌더(sudo 없음), 포트 3401 · 8401 (F11).
  - `run-api.sh` · `run-web.sh`: `--print-cmd` 옵션으로 실제 실행 명령 출력 → api는 `--host 127.0.0.1 --port 8400`과 `DCX_RELEASE_SHA=<current>`, web은 `-H 127.0.0.1 -p 3400`. web 명령 환경에 `app.env` 키 없음.
- [ ] 실패 확인: `… -m pytest backend/tests/ops/test_dcxctl.py backend/tests/ops/test_install.py -q -p no:cacheprovider` → FAIL.
- [ ] **GREEN** `dcxctl` · `run-api.sh` · `run-web.sh` · `install.sh`(설계 6 · 9장) · plist 3개 · `ops/macmini/README.md`(설치 · 명령 · 로그 보는 법, 한국어) · `scripts/deploy.sh` 머리 주석.
- [ ] 통과: `… -m pytest backend/tests/ops -q -p no:cacheprovider` PASS + 전체 백엔드 PASS.

## 검증 명령
```
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend test
```

## QA 계획 (실기, UI 변경 없음)
UI 변경이 없어 브라우저 시나리오는 "배포된 화면이 뜨는가" 확인만 한다. 실제 운영 폴더를 건드리기 전에 **QA 전용 루트**로 먼저 돌린다.

- QA 루트: `APP_ROOT=~/srv/dcx-agent-qa`, 포트 api 8401 · web 3401. `install.sh --qa`로 사용자 LaunchAgent 3개(라벨 `…-qa`, sudo 없음)를 올려 실제 KeepAlive 재시작을 검증하고, QA가 끝나면 `launchctl bootout`으로 내린다(F11). launchd 아래 `codex --version` 성공 확인(F6).
- 데이터: `shared/data`에 `~/srv/dcx-agent/shared/data/sessions`만 복사(크롤 수집본 제외).

| ID | 시나리오 | 기대 | AC |
|---|---|---|---|
| QA-1 | 이 기능 PR을 열면 GitHub Actions가 돈다 | backend · frontend job 초록, PR 화면에 체크 표시 | AC-01 |
| QA-2 | QA 루트에서 `DEPLOY_SHA=<PR 머리 커밋> dcxctl deploy` (CI 조회는 PR 커밋이라 `DCX_CI_API` 기본값 대신 실제 결과 확인) | 릴리스 빌드(실제 pip · npm) · 교체 · `/health` release = 그 커밋 · `http://localhost:3401/pipeline/start` 화면 뜸 | AC-02 |
| QA-3 | QA 루트에서 `DCX_FORCE_UNHEALTHY_SHA=<두 번째 커밋>`(그 커밋만 상태 확인 실패)으로 두 번째 배포 | 직전 릴리스로 롤백 · 세션 스냅샷 복원 · `unhealthy` 로그 | AC-04 |
| QA-4 | `dcxctl rollback` · `dcxctl status` | 설계 5장대로 | AC-08 |
| QA-5 | 빌드 실패 커밋 흉내(`DCX_BUILD_CMD=false`) | `build-failed`, 떠 있던 버전 유지 | AC-03 |
| QA-6 | `install.sh --dry-run` (운영 루트) | 할 일 목록 · 건드리지 않는 포트 출력, 변경 없음 | AC-07 |
| QA-7 | (UAT 단계, 사용자) `sudo ~/Desktop/…/ops/macmini/install.sh` 실제 설치 → 머지 후 자동 배포 확인 → 재부팅 후 `/health` | 세 잡 기동, 3400 · 8400 응답, 재부팅 후에도 응답 | AC-02 · AC-05 · AC-06 |

- 키 유출 확인: QA 중 `logs/*.log` · `releases/*/frontend/.next`에서 `app.env`의 키 값 grep → 0건(AC-06).
- 개발 서버 3310 · 3311 · 8310 · 8311 · 3000이 QA 전후로 그대로인지 `lsof`로 확인(AC-07).

## 수용 기준 연결
| AC | 근거 |
|---|---|
| 01 | T1 · QA-1 |
| 02 | T1 `/health` · T2 `test_success_deploys` · QA-2 · QA-7 |
| 03 | T2 `test_ci_failed_once` · `test_build_failed_marks_and_keeps` · QA-5 |
| 04 | T2 `test_unhealthy_*` · QA-3 |
| 05 | T3 plist 테스트 · QA-7 |
| 06 | T2 `test_secrets_not_in_build_env` · QA 키 grep |
| 07 | 전역 제약 · T3 install 출력 · QA-6 · lsof 확인 |
| 08 | T3 `test_dcxctl.py` · QA-4 |

## 되돌리기
- 코드: main 머지 커밋 `git revert -m 1`. CI는 워크플로 파일이 사라지면 멈춘다.
- 맥미니: `sudo launchctl bootout system/ai.person-a.dcx-agent.{deploy,api,web}` 후 plist 3개 삭제. `~/srv/dcx-agent/shared`(키 · 데이터 · 스냅샷)는 남는다. 손 실행으로 돌아가려면 `current`에서 지금처럼 uvicorn · next start를 띄운다.

## Decision ledger (plan-eng-review, 2026-10-02)

### Scope record
feature answers: 축소 제안 없음; structure: 원래 3 Task 유지(파일 17개는 대부분 작은 운영 스크립트 · 테스트, 더 줄이면 lib.sh 공용 함수가 deploy · dcxctl에 중복됨) — 질문 생략 사유: 줄일 수 있는 배치가 승인된 기능을 유지하지 못함; accepted scope: T1~T3; pending remedies: R1

### 리뷰 발견 (Codex 바깥 의견 + Claude 확인)
| # | 심각도 | 위치 | 내용 | 처리 |
|---|---|---|---|---|
| F1 | P1 | 설계 3장 첫 릴리스 이전 · `~/srv/dcx-agent/repo/backend/.venv/bin/uvicorn:1`(절대 경로 shebang) · 손 실행 main.py에 `release` 없음 | clone을 옮기면 venv가 깨지고, 옛 릴리스는 새 상태 확인을 통과 못함 | 보정: 첫 설치는 main 머리 커밋을 **정식 빌드**(venv 해시 폴더 새로 생성)해 첫 릴리스로 삼는다. 손 clone은 설치가 끝난 뒤 지운다. 상태 확인은 `release` 필드가 없으면(옛 릴리스) `status == ok`만 본다 |
| F2 | P1 | 설계 4장 6 · 5장 · `backend/app/label/store.py:42`(세션 안 SQLite) | 서버가 살아 있는 채 스냅샷 · 복원 → SQLite 깨짐 위험 | 보정: 순서를 **api · web 중지(KeepAlive 잠시 끔: `launchctl disable`) → 작업자 종료 → 스냅샷 → 교체 → 시작**으로. 복원도 중지 상태에서. SQLite 파일은 `sqlite3 .backup` 대신 중지 후 `cp -a`(쓰는 프로세스 없음 보장) |
| F3 | P1 | `backend/app/work/runner.py:34` · `backend/app/crawl/control.py:133`(`start_new_session=True`) · `backend/app/main.py:30`(기동 복구는 키워드 라운드만) | 작업자는 별도 세션이라 api 재시작으로 안 죽고, 옛 코드로 계속 돈다. "기동 때 중단 처리"도 사실이 아님 | 보정(D-401 구현): 배포 · 롤백 때 `APP_ROOT/releases/` 아래 경로에서 실행된 python 프로세스(작업자)를 찾아 TERM → 20초 → KILL. 작업 상태는 기존 상태 갱신(죽은 작업자 감지 → `interrupted`)에 맡기고, 상태 확인 단계에서 `/sessions` 응답이 오는지만 본다. 테스트: 가짜 작업자 프로세스 종료 확인 |
| F4 | P1 | 설계 5장 · `work/<sid>/runs.sqlite` · 판정 캐시 · 모델 | 롤백은 세션만 되돌리고 작업 DB · 캐시 · 모델은 새 상태 그대로 | D-403(세션만) 범위 안. 설계에 한계를 명시: "롤백은 코드 + 세션만 되돌린다. 롤백 뒤 화면이 이상하면 그 세션을 새 버전으로 다시 시작". `work/` 폴더(작은 SQLite)는 스냅샷에 **포함**(같은 SQLite 위험 대응, 용량 작음) — D-403의 "큰 파일 제외" 취지 안 |
| F5 | P1 | 설계 4장 7~9 | `current` 교체 뒤 죽으면 다음 틱이 `sha == current`로 보고 검증 · 롤백 없이 영원히 멈춤 | 보정: `shared/deploy-state`에 단계(`switching <sha> <prev> <snapshot>`)를 기록하고 끝나면 지운다. 다음 틱 시작 때 남아 있으면 상태 확인부터 다시(실패면 롤백). 테스트 추가 `test_resume_after_crash_mid_switch` |
| F6 | P1 | 설계 6장 · `/Users/persona1/srv/internal-app/ops/env.sh:10`(PATH 지정) · `backend/app/llm/codex_exec.py:79` | 데몬 PATH에 Homebrew `node` · `npm` · `python3.12` · `codex`가 없음 | 보정: `env.sh`가 `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`을 지정. `install.sh`와 `deploy.sh` 시작에 실행 파일 확인(`node npm python3.12 codex git curl`), 없으면 `error` 로그. QA에 launchd 아래 `codex --version` 확인 추가 |
| F7 | P1 | `backend/tests/test_health.py:5`(정확한 응답 단언) | T1이 기존 테스트를 깨는데 소유 파일에 없음 | 보정: T1 소유 파일에 `backend/tests/test_health.py` 추가, 기대값을 `{"status":"ok","release":"dev"}`로 |
| F8 | P2 | `backend/requirements.txt:1`(버전 고정 없음) | 같은 글자여도 CI(우분투)와 맥미니 venv가 다른 버전을 받을 수 있음 | **R1 — 질문** |
| F9 | P2 | `backend/app/config.py:37`(`author_salt_path` 기본값이 cwd 기준) · 지금 데모는 `AUTHOR_SALT_PATH=…/asan-demo/.author_salt` | 릴리스마다 새 salt가 생길 수 있음 → 작성자 해시 불일치 | 보정: `runtime.env`에 `AUTHOR_SALT_PATH=$APP_ROOT/shared/data/.author_salt`(데모에서 복사된 값). 손 실행 8400도 2026-10-02에 이 값으로 다시 띄움 |
| F10 | P2 | 설계 4장 5 · 9 · `frontend/src/lib/api.ts:1` | 프론트 재사용이 sha만 봄(NEXT_PUBLIC 값 바뀌면 틀린 빌드 재사용), web 200은 API 연결을 증명 못함 | 보정: 빌드 마커 `releases/<sha>/.build-config`에 `NEXT_PUBLIC_*` 값 해시, 다르면 다시 빌드. 상태 확인에 `GET 127.0.0.1:8400/sessions` 200 추가(화면이 부르는 API) |
| F11 | P2 | QA 계획 · `DCX_FORCE_UNHEALTHY` 전역 | launchd 없는 QA는 재시작을 검증 못함, 전역 스위치는 복원된 릴리스도 실패시킴 | 보정: QA 루트도 launchd **사용자 에이전트**(`~/Library/LaunchAgents`, sudo 불필요, 라벨 `…-qa`)로 돌리고 끝나면 내림. 스위치를 `DCX_FORCE_UNHEALTHY_SHA=<sha>`(그 커밋만 실패)로. bash 3.2 확인은 grep 대신 테스트 전체를 `/bin/bash`로 실행(macOS에서), CI(우분투)는 bash 5 |
| F12 | P3 | `backend/tests/label/test_label_api.py:56`(50ms 단언) | CI에서 느린 러너로 가끔 실패할 수 있음 | 기록만(기존 테스트, 이번 범위 밖). CI 실패 시 재실행으로 대응, 반복되면 backlog |

### R1: 의존성 버전 고정 (F8)
Finding: F8 (P2, Codex)
Plan baseline: 고정 없음, venv는 requirements.txt 해시로 재사용(D-407)
Runtime evidence: `backend/requirements.txt` 항목에 버전 고정 없음
Question D1: 백엔드 라이브러리 버전 고정 (A 지금 맥미니 버전으로 고정 · B 고정하지 않음)
State: approved
Actual answer: A 지금 맥미니 버전으로 고정 (D1 답변, 2026-10-02)
Accepted scope: T1에서 `backend/constraints.txt`(개발 폴더 `backend/.venv`의 `pip freeze`, 맥 전용 패키지는 `; sys_platform == "darwin"` 표시)를 만들고 CI · 맥미니 모두 `pip install -r backend/requirements.txt -c backend/constraints.txt`. venv 해시 키 = sha256(requirements.txt + constraints.txt + `python3.12 --version`). CI가 우분투에서 이 constraints로 설치 성공해야 T1 완료.

Approval readiness: PASS — Scope record · R1(D1 "A"). F1~F7 · F9~F11은 승인된 설계(D-401 · D-402 · D-403 · D-410)와 계획 실행 가능성을 위한 보정, F12는 기록만.

## 엔지니어링 리뷰 결과 (plan-eng-review, 2026-10-02)
- 섹션: 아키텍처 4건(F1 · F2 · F3 · F5) · 코드 품질 3건(F6 · F9 · F10) · 테스트 3건(F7 · F11 · F12) · 성능 0건 · 의존성 1건(F8 → R1).
- 바깥 의견: Codex(완료, 11건 + 참고 1건) — 모두 코드로 확인. Claude는 F9(데모의 `AUTHOR_SALT_PATH`가 손 배포 8400에 빠져 있음)를 실제 프로세스 환경으로 재확인하고 즉시 고침.
- 비판적 공백(테스트 · 처리 · 표시 모두 없음): 0개(보정 반영 후).
- NOT in scope: 맥미니 밖 접속, Slack 알림, main 브랜치 보호 설정(사용자 GitHub 설정), 50ms 단언 테스트 손질(F12).
- 병렬화: T1 · T2 병렬 → T3.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | codex via `/plan-eng-review` | Independent 2nd opinion | 1 | completed | 11 findings (P1 7 · P2 4), 모두 반영 또는 사용자 결정 |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 12 issues, 0 critical gaps (미결 0) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | UI 변경 없음 |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex · plan-review · completed · 11 findings.
- **VERDICT:** ENG 발견 12건 모두 처리(보정 10 · 사용자 결정 1 · 기록 1), 구현 진행 가능. 대시보드 상태는 발견이 있었으므로 issues_open.

NO UNRESOLVED DECISIONS
