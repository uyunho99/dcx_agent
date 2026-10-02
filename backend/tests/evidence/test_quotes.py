import pytest
from app.evidence.quotes import locate
from app.segment.inputs import _join


@pytest.mark.parametrize('field,idx', [('title', None), ('body', None), ('comment', 1)])
def test_original_offsets(field, idx):
    text = '앞  아침\n\t 냉방  뒤 아침 냉방'
    doc = dict(title=text, body=text, comments=[{'text': '다른 댓글'}, {'text': text}])
    result = locate(dict(field=field, idx=idx, text='아침 냉방'), doc)
    assert result == dict(field=field, idx=idx, text='아침 냉방', start=3, end=10, verified=True)
    assert text[result['start']:result['end']] == '아침\n\t 냉방'


@pytest.mark.parametrize('quote', [dict(field='body', text='없음'), dict(field='body', text='  '),
    dict(field='comment', idx=-1, text='댓글'), dict(field='comment', idx=4, text='댓글')])
def test_unverified(quote):
    result = locate(quote, dict(body='본문', comments=[{'text': '댓글'}]))
    assert result['verified'] is False and result['start'] is None and result['end'] is None


def test_comment_index_from_prepared_order():
    prepared = dict(comments=[{'text': '첫 댓글'}, {'text': '둘째 댓글'}])
    doc = _join(dict(comments=list(reversed(prepared['comments']))), prepared)
    assert locate(dict(field='comment', idx=1, text='둘째 댓글'), doc)['verified']
    assert not locate(dict(field='comment', idx=0, text='둘째 댓글'), doc)['verified']
