"""Stage-five entropy passthrough and local KNU dictionary scoring."""
import json
from pathlib import Path

import numpy as np
import pytest

from app.lexicon import knu
from app.segment.inputs import SegmentInput
from app.segment.signals import document_signals


def test_pred_entropy_copied_from_export():
    docs = {'new': {'pred_entropy': .123456789, 'tagProbs': {'act': .5}},
            'old': {'pred_entropy': 0, 'tagProbs': {'act': .5}}}
    source = SegmentInput(['new', 'old'], np.eye(2),
                          {'new': ['좋다'], 'old': ['짜증']}, {}, docs, {})
    result = document_signals(source)
    assert result == {'new': {'pred_entropy': .123456789, 'sentiment': 1.0},
                      'old': {'pred_entropy': 0, 'sentiment': -1.0}}
    assert result['old']['pred_entropy'] is docs['old']['pred_entropy']
    assert 'sentiment' not in docs['new']
    assert document_signals(SegmentInput([], np.empty((0, 2)), {}, {}, {}, {})) == {}


def test_knu_real_dictionary():
    assert knu.polarity(['정말', '좋다']) > 0
    assert knu.polarity(['정말', '짜증']) < 0
    assert knu.polarity(['좋다', '짜증']) == 0
    assert knu.polarity(['없는토큰xyz']) == 0
    assert knu.polarity([]) == 0
    entries = json.loads(Path(knu.__file__).with_name('knu_senti.json').read_text())
    assert len(entries) == 14854


def test_knu_roots_fallback_mean_and_cache(monkeypatch):
    entries = [{'word': 'positive', 'word_root': 'root', 'polarity': '2'},
               {'word': 'mild', 'word_root': 'other', 'polarity': '1'},
               {'word': 'negative', 'word_root': 'bad', 'polarity': '-2'},
               {'word': 'root', 'word_root': 'bad', 'polarity': '-2'}]
    opens = []
    original = Path.open

    def open_dictionary(path, *args, **kwargs):
        if path.name == 'knu_senti.json':
            import io
            opens.append(path)
            return io.StringIO(json.dumps(entries))
        return original(path, *args, **kwargs)

    knu._load.cache_clear()
    try:
        monkeypatch.setattr(Path, 'open', open_dictionary)
        assert knu.polarity(['root']) == 1  # roots take precedence over word aliases
        assert knu.polarity(['positive', 'mild', 'unknown']) == .75
        assert knu.polarity(['root', 'root', 'bad']) == pytest.approx(1 / 3)
        assert len(opens) == 1
    finally:
        knu._load.cache_clear()
