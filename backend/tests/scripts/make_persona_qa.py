"""Create an offline confirmed segment session and stage-eight input package.

Usage: backend/.venv/bin/python backend/tests/scripts/make_persona_qa.py LOCAL_DATA_DIR
Use --big-persona for the ten-Context chunking case. Start the app with the same
LOCAL_DATA_DIR and LLM_BACKEND=fake. Stage-eight UI/workers land in later tasks.
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
    args = parser.parse_args()
    session = write_session_with_package(args.local_data_dir, seed=args.seed,
                                        big_persona_contexts=10 if args.big_persona else None)
    print(json.dumps(dict(sid=session.sid, version=session.version,
        package=str(args.local_data_dir.resolve() / 'sessions' / session.sid /
                    'versions' / session.version / 'evidence/package.json')), ensure_ascii=False))


if __name__ == '__main__':
    main()
