"""Create an offline confirmed segment session and stage-eight input package.

Usage: backend/.venv/bin/python backend/tests/scripts/make_persona_qa.py LOCAL_DATA_DIR
Use --big-persona for the ten-Context chunking case. Start the app with the same
LOCAL_DATA_DIR and LLM_BACKEND=fake. Use --second-session to create another session with the same bk and no stage-eight results.
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
with patch('pydantic_settings.sources.DotEnvSettingsSource.__call__', return_value={}):
    from tests.fixtures.evidence_package import write_session_with_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('local_data_dir', type=Path)
    parser.add_argument('--big-persona', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--second-session', action='store_true', help='Create another same-product session without stage-eight results')
    args = parser.parse_args()
    session = write_session_with_package(args.local_data_dir, seed=args.seed, qa_failed_persona=3,
                                        big_persona_contexts=10 if args.big_persona else None)
    output = dict(sid=session.sid, version=session.version,
        package=str(args.local_data_dir.resolve() / 'sessions' / session.sid /
                    'versions' / session.version / 'evidence/package.json'))
    if args.second_session:
        second = write_session_with_package(args.local_data_dir, seed=args.seed + 1)
        output['second_sid'] = second.sid
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
