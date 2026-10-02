"""Write a local, offline 1,200-document LG air-conditioner QA session.

Usage: backend/.venv/bin/python backend/tests/scripts/make_segment_qa.py LOCAL_DATA_DIR
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
    args = parser.parse_args()
    session = make_segment_session(args.local_data_dir, clusters=5, personas=(2,) * 5,
                                   contexts=(3,) * 10, docs_per_context=40, seed=42)
    print(json.dumps(dict(sid=session.sid, version=session.version,
                         documents=session.expected['documents']), ensure_ascii=False))


if __name__ == '__main__':
    main()
