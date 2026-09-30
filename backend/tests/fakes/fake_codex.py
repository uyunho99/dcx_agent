#!/usr/bin/env python3
"""Executable shebang fake; no real codex installation is required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

instructions = sys.argv[-1]
answer = Path(instructions.splitlines()[0].split('`')[1])
with Path('invocations').open('a') as stream:
    stream.write(str(os.getpid()) + '\n')
if 'SLEEP_MODE' in instructions:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    Path('child.pid').write_text(str(child.pid))
    # Reap the child when the whole process group receives SIGTERM.
    import signal
    def stop(*_):
        child.wait(timeout=3)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    time.sleep(60)
answer.write_text(json.dumps({'value': 'bad' if 'BAD_MODE' in instructions else 1}))
answer.rename(answer.with_suffix(''))
