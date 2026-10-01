"""Cooperative three-second worker, registered only by the test subprocess."""
import time


def run(context):
    if context.args.get('sleep'):
        time.sleep(context.args['sleep'])
        return
    elapsed = 0.0
    while elapsed < context.args.get('duration', 3):
        context.heartbeat(elapsed / context.args.get('duration', 3), {'elapsed': elapsed})
        if context.should_stop():
            return
        time.sleep(.05)
        elapsed += .05
    if context.args.get('fail'):
        raise RuntimeError('fake failure')
