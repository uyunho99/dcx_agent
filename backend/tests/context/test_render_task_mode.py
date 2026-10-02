from pathlib import Path

from app.context.render import render_context_md
from test_render import make_context


DIMENSIONS = '디멘션: 사회적 외부 페르소나 · 개인 취향·활동 · 신체 외부 동선 · 내부 바이오'
BEYOND = '예시는 출발점일 뿐이다. 네 디멘션 각각에서 예시와 비슷한 페르소나에 머물지 말고, 예시와 다른 페르소나와 맥락을 우선 발굴할 것'


def test_legacy_bytes_identical():
    assert render_context_md(make_context(), ['두 번째 발견', '첫 번째 발견']).encode() == Path(__file__).with_name('fixtures').joinpath('legacy_context.md').read_bytes()


def test_metric_render():
    ctx = make_context(bk='서울아산병원', taskMode='metric', analysisGoal=None, positioning={},
                       keyMetrics=[{'name': '환자경험 점수', 'source': '보건복지부 환자경험평가', 'item': '수납 대기 시간이 적절했다'}],
                       personaSeeds={'items': [{'text': '초진 보호자', 'dimension': 'social'}, {'text': '간병인', 'dimension': 'social'}, {'text': '만성 통증 환자', 'dimension': 'bio'}]})
    md = render_context_md(ctx, [])
    lines = ['- 제품명: 서울아산병원', '- 과제 유형: 지표 개선형 — 외부·사내 평가 지표를 올리는 과제. 지표가 떨어지는 순간을 우선 탐색',
             '- 핵심 지표 (방향 지시자, 측정값 아님): 환자경험 점수 (출처: 보건복지부 환자경험평가 · 문항: 수납 대기 시간이 적절했다)',
             '## 생각하는 페르소나 · 디멘션', '- 초진 보호자 (사회적 외부 페르소나)', '- 간병인 (사회적 외부 페르소나)', '- 만성 통증 환자 (내부 바이오)',
             '- 아직 적지 않은 디멘션: 개인 취향·활동, 신체 외부 동선', DIMENSIONS, BEYOND, '## 0-B']
    offsets = [md.index(line) for line in lines]
    assert offsets == sorted(offsets)
    assert lines[0] + '\n' + lines[1] in md
    for absent in ('분석 목표', '가격 포지셔닝', '시장 포지셔닝', 'None'):
        assert absent not in md


def test_explore_custom_positioning():
    md = render_context_md(make_context(taskMode='explore', positioning={'priceText': '중상가 · 구독형', 'market': 'new'}), [])
    assert '- 가격 포지셔닝: 중상가 · 구독형' in md
    assert '- 시장 포지셔닝: 신규 진입자' in md
    assert '- 과제 유형: 탐색·기획형 — 아직 드러나지 않은 맥락과 기회를 찾는 과제. 넓게 탐색' in md
    md = render_context_md(make_context(taskMode='explore', positioning={'marketText': '틈새 전문 브랜드'}), [])
    assert '- 시장 포지셔닝: 틈새 전문 브랜드' in md
    assert '가격 포지셔닝' not in md


def test_metric_partial_details():
    md = render_context_md(make_context(keyMetrics=[{'name': '출처만', 'source': 'X'}, {'name': '문항만', 'item': 'Y'}, {'name': '이름'}]), [])
    assert ': 출처만 (출처: X), 문항만 (문항: Y), 이름\n' in md


def test_persona_empty_and_off():
    md = render_context_md(make_context(personaSeeds={'items': []}), [])
    assert '## 생각하는 페르소나 · 디멘션\n\n- 없음\n' in md
    assert '아직 적지 않은' not in md
    assert DIMENSIONS in md and BEYOND in md
    md = render_context_md(make_context(personaSeeds={'items': [{'text': '응급실 재방문자'}], 'exploreBeyond': False}), [])
    assert '- 응급실 재방문자\n' in md
    assert '예시는 참고 시드이며 제약이 아니다. 범위 밖 발견도 배제하지 말 것\n\n## 0-B' in md
    md = render_context_md(make_context(personaSeeds={'items': [{'text': tag, 'dimension': tag} for tag in ('social', 'taste', 'movement', 'bio')]}), [])
    assert '아직 적지 않은' not in md


def test_legacy_metric_whitespace_preserved():
    golden = Path(__file__).with_name('fixtures').joinpath('legacy_context.md').read_bytes()
    expected = golden.replace('편의성, 만족도'.encode(), ' 편의성 , 만족도'.encode())
    assert render_context_md(make_context(keyMetrics=[' 편의성 ', '만족도']), ['두 번째 발견', '첫 번째 발견']).encode() == expected
