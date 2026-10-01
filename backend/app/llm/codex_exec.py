"""Local codex workers. Each backend instance retains its run ID for retries."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid

from app.config import settings
from app.work.proc import pid_alive as _alive
from app.llm.base import LLMTask, LLMResult, failure, validate
from app.llm.compose import compose


def _safe(text: str) -> str:
    for key in (settings.openai_api_key, settings.claude_api_key):
        if key:
            text = text.replace(key, '[REDACTED]')
    return text


def _answer(task, path):
    result = validate(task, path.read_text())
    if not result.ok:
        bad = path.parent / 'bad' / path.name
        path.replace(bad)
        bad.with_suffix('.reason.txt').write_text(result.error.message)
    return result


def _stop(process):
    # A separate session lets us terminate descendants as well as the worker.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=0.5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
    # Also kill descendants if the leader exited before them.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return output


def _worker(task, root, n):
    answer = root / f'answers/task-{n}.json'
    lock = root / f'locks/task-{n}.pid'
    process = None
    owned = False
    # Lock the persistent log inode: removing PID files cannot split the lock.
    with (root / f'logs/worker-{n}.log').open('a+') as handle:
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return failure('interrupted', 'Worker is already running')
            pid = lock.read_text().strip() if lock.exists() else ''
            if pid.isdigit() and _alive(int(pid)):
                return failure('interrupted', 'Worker is already running')
            owned = True
            if answer.exists():
                return _answer(task, answer)
            system, user = compose(task)
            schema = json.dumps(task.output_schema.model_json_schema(), ensure_ascii=False)
            prompt = f'{system}\n\n{user}\n\n출력 JSON 스키마:\n{schema}'
            instructions = f'답만 `answers/task-{n}.json.part`에 쓰고 rename하라\n{prompt}'
            (root / f'prompts/task-{n}.txt').write_text(instructions)
            with (root / f'logs/worker-{n}.log').open('a') as log:
                log.write('\n--- attempt ---\n')
                log.flush()
                process = subprocess.Popen(
                    [settings.codex_bin, 'exec', '--profile', settings.codex_profile,
                     '--skip-git-repo-check', '-C', str(root), instructions],
                    cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, start_new_session=True,
                )
                lock.write_text(str(process.pid))
                try:
                    output, _ = process.communicate(timeout=settings.codex_timeout_s)
                except subprocess.TimeoutExpired:
                    log.write(_safe(_stop(process)))
                    return failure('timeout', 'Codex worker timed out')
                log.write(_safe(output))
                if process.returncode != 0:
                    return failure('backend', 'Codex worker failed')
            if not answer.exists():
                return failure('backend', 'Codex worker did not write an answer')
            return _answer(task, answer)
        except (KeyboardInterrupt, InterruptedError):
            if process is not None:
                _stop(process)
            return failure('interrupted', 'Codex worker interrupted')
        except Exception:
            if process is not None and process.poll() is None:
                _stop(process)
            return failure('backend', 'Codex worker failed')
        finally:
            if owned:
                lock.unlink(missing_ok=True)


def run_many(tasks: list[LLMTask], run_id: str, concurrency: int) -> list[LLMResult]:
    if not run_id or Path(run_id).name != run_id or run_id in ('.', '..'):
        raise ValueError('Invalid run ID')
    if concurrency < 1:
        raise ValueError('Concurrency must be positive')
    root = (Path(settings.local_data_dir) / 'llm_runs' / run_id).resolve()
    for folder in ('prompts', 'answers/bad', 'locks', 'logs'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    manifest = []
    for task in tasks:
        system, user = compose(task)
        payload = json.dumps({'system': system, 'user': user, 'schema': task.output_schema.model_json_schema(), 'max_tokens': task.max_tokens}, ensure_ascii=False, sort_keys=True)
        manifest.append({'task': task.task, 'sid': task.sid,
                         'backend': {'name': 'codex_exec', 'bin': settings.codex_bin,
                                     'profile': settings.codex_profile, 'timeout_s': settings.codex_timeout_s},
                         'input_hash': hashlib.sha256(payload.encode()).hexdigest()})
    manifest_path = root / 'manifest.json'
    # Exclusive creation preserves the original run definition on reruns.
    try:
        with manifest_path.open('x') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
    except FileExistsError:
        if json.loads(manifest_path.read_text()) != manifest:
            return [failure('backend', 'Run ID already has different inputs or settings') for _ in tasks]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda item: _worker(item[1], root, item[0]), enumerate(tasks)))


class CodexExecBackend:
    def __init__(self, run_id: str | None = None):
        self.run_id = run_id or uuid.uuid4().hex

    def run(self, task: LLMTask) -> LLMResult:
        return run_many([task], self.run_id, 1)[0]
