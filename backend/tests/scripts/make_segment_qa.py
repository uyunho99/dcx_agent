"""Write a local, offline 1,200-document LG air-conditioner QA session.

Includes granularity and counter-context cases. LLM_BACKEND=fake uses the
optional segment.dims.echo.json fixture to bind dims to attached document IDs.

Usage: backend/.venv/bin/python backend/tests/scripts/make_segment_qa.py LOCAL_DATA_DIR [--confirm-all]

--confirm-all runs stage six offline and confirms all layers for stage-seven QA.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['EMBED_BACKEND'] = 'fake'
os.environ['LLM_BACKEND'] = 'fake'
# Same .env isolation used by tests/conftest.py.
with patch('pydantic_settings.sources.DotEnvSettingsSource.__call__', return_value={}):
    from tests.fixtures.segment_synth import make_segment_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('local_data_dir', type=Path)
    parser.add_argument('--confirm-all', action='store_true',
                        help='Run stage six and confirm all clusters, personas, and contexts')
    parser.add_argument('--fail-context', help='With --confirm-all, omit fake tag responses for this Context; remove qa-evidence.json to retry successfully')
    args = parser.parse_args()
    if args.fail_context and not args.confirm_all:
        parser.error('--fail-context requires --confirm-all')
    if args.confirm_all:
        from tests.fixtures.evidence_synth import make_evidence_session
        session = make_evidence_session(args.local_data_dir, qa=True, seed=42)
    else:
        session = make_segment_session(args.local_data_dir, qa=True, seed=42)
    if args.fail_context:
        from app.config import settings
        from app.context.store import root_dir, write_json
        from app.segment.store import SegmentStore
        with patch.object(settings, 'local_data_dir', str(args.local_data_dir.resolve())):
            store = SegmentStore.open(session.sid, session.version)
            if args.fail_context not in {r['context_id'] for r in store.contexts()}:
                parser.error('Unknown Context: ' + args.fail_context)
            with store._db() as db:
                ids = [r[0] for r in db.execute('SELECT doc_id FROM docs WHERE context_id=?', (args.fail_context,))]
            write_json(root_dir(session.sid) / 'qa-evidence.json', dict(fail_context=args.fail_context, fail_doc_ids=ids))
    print(json.dumps(dict(sid=session.sid, version=session.version,
                         documents=session.expected['documents']), ensure_ascii=False))


if __name__ == '__main__':
    main()
