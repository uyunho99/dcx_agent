"""Kind registry and cooperative checkpoints with a ten-second heartbeat.

Kinds must call heartbeat at safe checkpoints and honor should_stop. Pausing
blocks the checkpoint until resumed; stop leaves the run interrupted for retry.
"""
import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from threading import Event, Thread
import time

from app.work.status import ACTIVE, HEARTBEAT_INTERVAL, transaction


@dataclass
class Context:
    sid: str
    version: str
    kind: str
    args: dict
    run_id: str

    def _row(self):
        with transaction(self.sid) as db:
            return db.execute('SELECT * FROM runs WHERE run_id=?', (self.run_id,)).fetchone()

    def should_pause(self) -> bool:
        row = self._row()
        return row is not None and row['action'] == 'pause'

    def should_stop(self) -> bool:
        row = self._row()
        return row is None or row['state'] not in ACTIVE or row['action'] == 'stop'

    def _pulse(self):
        with transaction(self.sid) as db:
            db.execute('''UPDATE runs SET heartbeat_at=? WHERE run_id=? AND pid=?
                AND state IN ('running','paused')''', (time.time(), self.run_id, os.getpid()))

    def heartbeat(self, progress, detail):
        while True:
            with transaction(self.sid) as db:
                row = db.execute('SELECT * FROM runs WHERE run_id=?', (self.run_id,)).fetchone()
                if row is None or row['state'] not in ACTIVE or row['action'] == 'stop':
                    return
                paused = row['action'] == 'pause'
                db.execute('''UPDATE runs SET state=?,progress=?,detail=?,heartbeat_at=?
                    WHERE run_id=? AND pid=?''',
                           ('paused' if paused else 'running', progress, json.dumps(detail),
                            time.time(), self.run_id, os.getpid()))
            if not paused:
                return
            time.sleep(.1)


KINDS: dict[str, Callable[[Context], None]] = {}


def execute(context: Context):
    finished = Event()

    def pulse():
        while not finished.wait(HEARTBEAT_INTERVAL):
            context._pulse()

    thread = Thread(target=pulse, daemon=True)
    state, error = 'done', None
    thread.start()
    try:
        context.heartbeat(0, {})
        if not context.should_stop():
            KINDS[context.kind](context)
        if context.should_stop():
            state = 'interrupted'
    except Exception as exc:
        # Exception messages may contain provider credentials or document text.
        state, error = 'failed', type(exc).__name__
    finally:
        finished.set()
        thread.join()
        with transaction(context.sid) as db:
            db.execute('''UPDATE runs SET state=?,error=?,heartbeat_at=?
                WHERE run_id=? AND pid=? AND state IN ('running','paused')''',
                       (state, error, time.time(), context.run_id, os.getpid()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind')
    parser.add_argument('--sid', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--args-json', required=True)
    args = parser.parse_args()
    execute(Context(args.sid, args.version, args.kind, json.loads(args.args_json),
                    os.environ['DCX_WORK_RUN_ID']))


if __name__ == '__main__':
    main()
