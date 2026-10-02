# T3 구현 보고서

## 상태

T3 소유 파일 구현 완료. T2 파일은 변경하지 않았으며 git add/commit, 실제 설치, 서버 재시작, LaunchDaemon/LaunchAgent 등록은 실행하지 않았습니다. 아래 운영 권한 concern은 컨트롤러/T2 리뷰에서 해결해야 합니다.

## RED / GREEN

- RED: `backend/.venv/bin/python -m pytest backend/tests/ops/test_dcxctl.py backend/tests/ops/test_install.py -q -p no:cacheprovider` → **16 failed, 1 passed**. 스크립트 생성 전 실패 확인. 잠금 테스트의 부정 종료 단언만 스크립트 부재에서도 통과했습니다.
- GREEN: 같은 명령 → **19 passed**, 12.55초. 추가한 API 실행 테스트도 처음에는 테스트용 Python 링크의 venv 인식 문제로 실패했으며, 실제 테스트 인터프리터를 직접 실행하는 래퍼로 수정했습니다.
- GREEN: `backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider` → **64 passed**, 72.68초.
- 전체 backend: 실행 중, 완료 결과를 아래에 갱신합니다.
- macOS 기본 `/bin/bash` **3.2.57**로 스크립트 테스트 실행. 각 새 진입점의 `bash -n` 통과. 생성 plist 3개는 운영/QA 모두 `plistlib` 파싱 및 macOS `plutil -lint` 통과.
- Linux에서는 테스트가 XML/plist 파싱 경로를 사용합니다. 이 작업에서는 Linux 실행 환경 자체를 구동하지 않았습니다.
- `git diff --check` 통과. T2 소유 5개 파일의 `git diff --exit-code` 통과. 기존 `scripts/deploy.sh`는 머리 주석 한 줄만 추가했습니다.

## 변경 파일

- `ops/macmini/dcxctl`: 상태 조회, SHA 정규화·실패 표시 해제 후 T2 배포 호출, 잠금과 T2 중지/복원/교체/시작/상태 확인 함수를 사용하는 수동 롤백. sessions와 work 복원, 이력 제거, 실패 SHA 기록.
- `ops/macmini/run-api.sh`: 현재 릴리스 고정, dotenv 데이터 파싱, release/PID 설정, localhost uvicorn 실행. QA launchd 시작 시 codex 버전 기록.
- `ops/macmini/run-web.sh`: 공개 runtime 설정과 PORT만 전달하는 제한된 환경, localhost Next 실행, PID 및 명령 미리보기.
- `ops/macmini/install.sh`: 계획 출력, 대화형 y 확인, dry-run 출력 디렉터리 렌더, 운영/QA 라벨·포트·도메인 구분, 정식 첫 빌드와 상태 확인 뒤 손 clone 삭제, 사용자 권한 빌드, 기존 salt 필수 확인, 지정 runtime 값 작성, 운영 스크립트 복사와 잡 등록.
- `ops/macmini/launchd/ai.person-a.dcx-agent.deploy.plist`: 120초, RunAtLoad, UserName/HOME/APP_ROOT/PATH 및 도메인·포트 템플릿.
- `ops/macmini/launchd/ai.person-a.dcx-agent.api.plist`, `ops/macmini/launchd/ai.person-a.dcx-agent.web.plist`: KeepAlive, 사용자 환경, 릴리스 외부 진입점, 로그 경로.
- `ops/macmini/README.md`: 한국어 설치·수동 명령·로그·QA·데이터 복원 한계 및 운영 권한 concern.
- `scripts/deploy.sh`: DCX 1.0 EC2용이며 2.0은 ops/macmini라는 주석 한 줄.
- `backend/tests/ops/test_dcxctl.py`, `backend/tests/ops/test_install.py`: 기존 T2 macmini 픽스처 재사용. 실패 SHA, 롤백 이력/데이터, 스냅샷 부재, 잠금, health 실패, dry-run, 비동의/파이프 y 거부, plist/runtime, 실제 가짜 API/web 실행 환경 검증.
- 이 보고서: 사용자가 별도로 지정한 보고 경로.

## Concerns / 수정하지 않은 lib.sh 요구

1. **운영 LaunchDaemon 제어 권한(P1):** 설계대로 deploy plist는 UserName으로 일반 사용자 권한에서 실행되고, `DCX_LAUNCH_DOMAIN=system`을 전달합니다. 그러나 현재 lib.sh의 `stop_services`/`start_services`는 권한 상승 없이 system 도메인의 `launchctl disable/enable/kickstart`를 직접 호출합니다. macOS 운영 자동 재시작의 권한 경계를 해결·검증해야 합니다. 공용 제어 함수에 제한된 권한 helper를 도입하는 등의 별도 설계가 필요하며, T3에서 임의 sudoers 변경이나 T2 수정은 하지 않았습니다. QA는 자신의 gui 도메인을 사용합니다.
2. **수동 롤백의 강제 종료 복구:** T2 deploy.sh의 deploy-state 복구는 자동 배포/자동 롤백용입니다. T3 수동 롤백은 잠금과 올바른 중지 순서를 사용하지만, 복원·이력 갱신 도중 kill/재부팅까지 원자적으로 복구하는 공용 트랜잭션 계약은 없습니다. 수동 롤백까지 같은 강제 종료 보장을 요구하면, T2 recovery에 수동 이력 확정 처리를 추가하는 별도 변경이 필요합니다. lib.sh/deploy.sh는 수정하지 않았습니다.
3. **실기 검증 범위:** 실제 sudo/launchctl/프로세스 종료, 로그인 전 부팅, QA 에이전트 등록은 금지 범위에 따라 실행하지 않았습니다. 설치기의 real-mode는 미리보기·취소 경로와 구분되어 있으며 테스트는 real-mode 작업 경계에 진입하지 않습니다. 위 권한 문제 해결 후 별도 운영 QA가 필요합니다.

외부 참조 ops 파일은 읽기만 했습니다. `/Users/persona1/srv/*`, `~/Library/LaunchAgents`, `/Library/LaunchDaemons` 또는 실행 중인 서버에 쓰기/제어 작업을 하지 않았습니다.
