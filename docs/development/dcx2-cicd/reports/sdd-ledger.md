# SDD ledger — plan: docs/development/dcx2-cicd/03-plan.md

Baseline: 55b2a07 (tree = 2ba66eb code) · backend 1507 · frontend 356 · lint · build OK
Executor: codex (codex:codex-rescue --wait --fresh --write), controller commits (Codex sandbox cannot write worktree git metadata)
Ruling: T1 · T2 병렬(소유 파일 서로소, 사용자 '동시에' 선호) → T3
Task T1: implemented by codex (a84c2a6c0e5a56bca), commit 91ffb39 by controller. constraints macOS dry-run 통과(controller), Linux 바이너리 전용 확인은 kiwipiepy_model(sdist 전용) 때문에 방법 한계 — QA-1에서 실제 CI로 확인
Task T1: minor (deferred): Linux torch가 CUDA 판(nvidia-* 수 GB) — CI 느림, CPU 인덱스 추가 검토
Task T1: minor (deferred): 액션 버전이 SHA 고정 아님(v4/v5)
Task T1: minor (deferred): constraints에 테스트 전용 패키지 포함(무해)
Task T1: minor (deferred): CI job timeout-minutes 없음
Task T1: minor (deferred): 설치 명령 단언이 부분 문자열
Task T1: complete (commits 55b2a07..91ffb39, review clean; ⚠️ Ubuntu 설치는 QA-1)
Task T2: implemented by codex (a5e0cd5a0346db5d2), commit c6a60d8 by controller. Ruling: T3를 T2 리뷰와 병렬 시작 — T3는 T2 파일을 수정하지 않음, 리뷰 수정이 T2 계약을 바꾸면 T3 재조정 — 틀리면 T3 수정 1회
Task T2: review (opus) → Critical 1: launchctl gui/<uid> 도메인으로 stop/start — LaunchDaemon(system, 사용자 권한)과 맞지 않아 운영에서 매 틱 실패 또는 KeepAlive가 스냅샷 중 옛 api를 되살림
Ruling: 보류 파일 방식으로 교정 — shared/maintenance가 있으면 run-api.sh/run-web.sh가 잠깐 쉬고 종료, stop = 파일 생성 + 종료, start = 파일 삭제 + 종료(launchd가 재기동), 스냅샷 전 8400/3400 빈 포트 · 작업자 0 확인. T2 lib.sh + T3 run 스크립트를 한 번에 고치므로 T3 완료 뒤 수정 1회로 — D-402(LaunchDaemon)를 지키는 유일한 무root 경로 — 틀리면 재시작 방식만 교체
Task T2: minor → fix로 포함: build_release가 current 릴리스를 지울 수 있음(minor 3), dcxctl pipefail(minor 8)
Task T2: minor (deferred): ERR trap 중복 로그, 재부팅 후 pid 재사용 잠금, ci-unknown 매 틱 로그, venv/ci-stuck/-failed 잔재 정리 없음, ps/lsof 실프로세스 테스트 없음(QA에서), 실패 반복 시 서비스 정지 상태 유지(설계 10장에 표시 필요)
Task T3: implemented by codex (a7c2519a879b0bc95), commit e172cdb by controller; T3도 같은 launchd 권한 문제를 concern으로 보고 + 수동 롤백 크래시 복구 없음
Task T2/T3: fix round 1 (codex, interrupted by user but complete on disk), commit c3221fc; 73 ops tests pass. Draft PR uyunho99/dcx_agent#6 opened for real CI (QA-1)
Task T2/T3: fix round 1 re-review (opus) all ADDRESSED; out-of-scope 3 + low 2 → fix round 2
QA-pre: QA 설치가 main 2ba66eb(constraints.txt 없음) 빌드에서 실패 → 실제 결함, fix round 3(missing constraints) 위임. 설치 실패 시 hold · LaunchAgent 잔재 없음 확인. 동시에 install.sh 운영 기본값이 localhost라 공개 사이트를 깨뜨리는 문제 → fix round 3(public URLs) 위임
Task T2/T3: fix round 2 re-review (opus) 1~7 ADDRESSED. High: install.sh localhost 기본값(이미 fix round 3 public URLs로 위임)
minor (deferred): dry-run이 보호 포트 오류를 deploy.log에 씀; 보호 포트 판정이 $HOME 경로 문자열 비교; restore rename이 다른 볼륨에서 실패(안전 실패); 빈 deploy-state + hold 영구 정지 가능성; pid 재사용; 롤백 시 .build-config 불일치 미검사; Linux next-server 이름 미탐지
fix round 3 (public URLs): codex aa1734e7bf9ef9947 done, 120 ops pass
QA: 데모 3311/8311 프로세스(19010/19325)가 17:30 이후 종료된 것을 발견 — QA 로그·테스트 포트에 근거 없음, 원인 미확인. 공개 사이트는 3400/8400이라 영향 없음. 사용자에게 보고
