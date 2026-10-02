"""Display spacing is derived, lossless, cached, and never mutates keywords."""
from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def display():
    module = import_module('app.keywords.display')
    module.display_form.cache_clear()
    yield module
    module.display_form.cache_clear()


@pytest.mark.parametrize('kw,expected', [
    ('귀촌휴식죄책감', '귀촌 휴식 죄책감'),
    ('귀촌부부온도차', '귀촌 부부 온도차'),
    ('농가미완성감', '농가 미완성감'),
    ('층간소음스트레스', '층간 소음 스트레스'),
    ('전원혼자시간', '전원 혼자 시간'),
    ('아산병원초진후기', '아산 병원 초진후기'),
    ('아산병원첫방문', '아산 병원 첫 방문'),
    ('아산병원약수령', '아산 병원 약 수령'),
    ('진료전도착시간', '진료 전 도착 시간'),
    ('진료후다음절차', '진료 후 다음 절차'),
    ('아산병원선결제후결제', '아산 병원 선결제 후 결제'),
    ('아산병원암병원접수처', '아산 병원 암병원 접수처'),
    ('주차비정산등록', '주차비 정산 등록'),
    ('진료의뢰서안가져', '진료 의뢰서 안 가져'),
    ('진료예약노쇼불이익', '진료 예약 노쇼 불이익'),
    ('셔틀버스승차장', '셔틀버스 승차장'),
])
def test_real_spacing(display, kw, expected):
    result = display.display_form(kw)
    assert result == expected
    assert ''.join(result.split()) == kw


def test_department_suffix_stays_attached(display):
    result = display.display_form('진료과이전')
    assert result.startswith('진료과 ')
    assert result.replace(' ', '') == '진료과이전'


@pytest.mark.parametrize('kw', ['귀촌 후회', '귀촌\t후회', 'ABC', 'ABCD', '귀촌', '귀촌감', ''])
def test_bypass_does_not_initialize_kiwi(display, monkeypatch, kw):
    factory = Mock(side_effect=AssertionError('must not initialize'))
    monkeypatch.setattr(display, '_kiwi', None)
    monkeypatch.setattr(display, 'Kiwi', factory)
    assert display.display_form(kw) == kw
    factory.assert_not_called()


@pytest.mark.parametrize('spaced,expected', [
    ('층 간 소음 스트레스', '층간 소음 스트레스'),
    ('귀촌 부부 온도 차', '귀촌 부부 온도차'),
    ('전 원 혼자 시간', '전원 혼자 시간'),
    ('귀 촌 휴 식', '귀촌휴식'),
    ('다른 단어', '귀촌휴식'),
    ('', '귀촌휴식'),
])
def test_merge_and_lossless_fallback(display, monkeypatch, spaced, expected):
    kw = ''.join(spaced.split()) if spaced not in ('다른 단어', '') else '귀촌휴식'
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value=spaced), tokenize=Mock(return_value=[])))
    result = display.display_form(kw)
    assert result == expected
    assert ''.join(result.split()) == kw
    assert all(len(segment) > 1 for segment in result.split())


@pytest.mark.parametrize('single', ['전', '후', '중', '약', '앱', '길', '날'])
def test_keep_characters(display, monkeypatch, single):
    spaced = f'진료 {single} 방문'
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value=spaced), tokenize=Mock(return_value=[])))
    assert display.display_form(spaced.replace(' ', '')) == spaced


@pytest.mark.parametrize('tag', ['MM', 'MAG', 'MAJ', 'NR', 'NNB', 'NP', 'VV', 'VA', 'VX', 'IC'])
def test_keep_tags_override_prefix(display, monkeypatch, tag):
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value='병원 첫 방문'),
        tokenize=Mock(return_value=[SimpleNamespace(start=2, len=1, tag=tag)])))
    assert display.display_form('병원첫방문') == '병원 첫 방문'


@pytest.mark.parametrize('single', ['선', '암', '타', '재', '초', '입', '노', '회', '가', '미', '제', '첫'])
def test_prefix_merges_forward(display, monkeypatch, single):
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value=f'병원 {single} 방문'), tokenize=Mock(return_value=[])))
    assert display.display_form(f'병원{single}방문') == f'병원 {single}방문'


def test_covering_token_and_offsets_after_merges(display, monkeypatch):
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value='층 간 소음 별 방문 첫 예약'),
        tokenize=Mock(return_value=[
            SimpleNamespace(start=3, len=2, tag='XPN'),
            SimpleNamespace(start=7, len=1, tag='MM'),
        ])))
    assert display.display_form('층간소음별방문첫예약') == '층간 소음 별방문 첫 예약'


def test_tokenize_exception_returns_original(display, monkeypatch):
    monkeypatch.setattr(display, '_kiwi', Mock(
        space=Mock(return_value='귀촌 휴식'),
        tokenize=Mock(side_effect=RuntimeError('tokenization failed'))))
    assert display.display_form('귀촌휴식') == '귀촌휴식'


@pytest.mark.parametrize('during_init', [False, True])
def test_kiwi_exception_returns_original(display, monkeypatch, during_init):
    broken = Mock(side_effect=RuntimeError('Kiwi unavailable'))
    monkeypatch.setattr(display, '_kiwi', None if during_init else Mock(space=broken))
    monkeypatch.setattr(display, 'Kiwi', broken)
    assert display.display_form('귀촌휴식죄책감') == '귀촌휴식죄책감'
    broken.assert_called_once()


def test_lazy_singleton_and_cache(display, monkeypatch):
    kiwi = Mock(space=Mock(side_effect=lambda kw: kw), tokenize=Mock(return_value=[]))
    factory = Mock(return_value=kiwi)
    monkeypatch.setattr(display, '_kiwi', None)
    monkeypatch.setattr(display, 'Kiwi', factory)
    for kw in ['귀촌휴식', '귀촌휴식', '전원생활']:
        assert display.display_form(kw) == kw
    factory.assert_called_once_with()
    assert kiwi.space.call_count == 2
    assert kiwi.tokenize.call_count == 2
    assert display.display_form.cache_info().maxsize == 4096


def test_with_display_copies_every_dict(display):
    original = [{'kw': '귀촌휴식죄책감', 'id': 'one'}, {'kw': None}, {'id': 'missing'}]
    before = deepcopy(original)
    result = display.with_display(original)
    assert original == before
    assert result is not original
    assert all(new is not old for new, old in zip(result, original))
    assert result[0] == {**original[0], 'display': '귀촌 휴식 죄책감'}
    assert result[1:] == original[1:]
    assert display.with_display([]) == []
