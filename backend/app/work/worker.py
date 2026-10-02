"""Kind registry and cooperative checkpoints with a ten-second heartbeat.

Kinds must call heartbeat at safe checkpoints and honor should_stop. Pausing
blocks the checkpoint until resumed; stop leaves the run interrupted for retry.
"""
import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import logging
import os
from threading import Event, Thread
import time

from app.work.status import ACTIVE, HEARTBEAT_INTERVAL, transaction

logger = logging.getLogger(__name__)


@dataclass
class Context:
    sid: str
    version: str
    kind: str
    args: dict
    run_id: str
    _heartbeat_callback: Callable[[], None] | None = field(default=None, init=False, repr=False)

    def _refresh_leases(self):
        callback = self._heartbeat_callback
        if callback is not None:
            try:
                callback()
            except Exception as exc:
                # Keep the heartbeat alive; retry next time without logging payloads.
                logger.warning('Vote lease refresh failed (%s)', type(exc).__name__)

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
            updated = db.execute('''UPDATE runs SET heartbeat_at=? WHERE run_id=? AND pid=?
                AND state IN ('running','paused')''', (time.time(), self.run_id, os.getpid()))
        if updated.rowcount:
            self._refresh_leases()

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


def _prep(context: Context):
    from app.routers.prep import run_worker
    run_worker(context)


def _judge(context: Context):
    from app.label.judge import run_worker

    try:
        run_worker(context)
    finally:
        context._heartbeat_callback = None


def _train(context: Context):
    from app.routers.training_v2 import run_worker
    run_worker(context)


def _infer(context: Context):
    from app.model.infer import run_worker
    run_worker(context)


def _monitor(context: Context):
    from app.model.monitor import run_worker
    run_worker(context)


def _segment(context: Context):
    from app.segment.pipeline import run
    run(context)


def _persona(context: Context):
    from app.persona.pipeline import run
    run(context)


def _insight(context: Context):
    from app.persona.insight_pipeline import run
    run(context)


def _evidence(context: Context):
    from app.evidence.pipeline import run
    run(context)


KINDS: dict[str, Callable[[Context], None]] = {
    'prep': _prep, 'judge': _judge, 'train': _train, 'infer': _infer, 'monitor': _monitor, 'segment': _segment, 'evidence': _evidence, 'persona': _persona, 'insight': _insight}


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
    except BaseException as exc:
        # Exception messages may contain provider credentials or document text.
        from app.context.store import StoreError
        stale_evidence = context.kind == 'evidence' and isinstance(exc, StoreError) and exc.kind == 'stale_run'
        state, error = ('interrupted' if stale_evidence or not isinstance(exc, Exception) else 'failed'), type(exc).__name__
        if not isinstance(exc, Exception):
            raise
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
