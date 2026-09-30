import re
from pathlib import Path
from app.context.labels import LABELS


def test_ts_labels_match_python():
    source = (Path(__file__).resolve().parents[3] / 'frontend/src/lib/contextLabels.ts').read_text()
    groups = re.findall(r'"(\w+)":\s*\{([^}]+)\}', source)
    actual = {group: dict(re.findall(r'"([^"]+)": "([^"]+)",', body)) for group, body in groups}
    assert actual == LABELS
