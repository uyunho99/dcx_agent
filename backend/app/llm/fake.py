import json
from pathlib import Path
from app.llm.base import LLMTask, LLMResult, failure, validate
from app.llm.compose import compose

class FakeBackend:
    fixture_dir = Path(__file__).resolve().parents[2] / 'tests/fixtures/llm'

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses

    def run(self, task: LLMTask) -> LLMResult:
        compose(task)
        try:
            if self.responses is not None:
                raw = self.responses[task.task]
            else:
                path = (self.fixture_dir / f'{task.task}.json').resolve()
                if not path.is_relative_to(self.fixture_dir.resolve()):
                    return failure('backend', 'Invalid fixture name')
                echo = self.fixture_dir / f'{task.task}.echo.json'
                if echo.exists() and (task.task == 'segment.dims' or task.attachments):
                    path = echo
                raw = path.read_text()
        except (KeyError, OSError):
            return failure('backend', 'Fake response unavailable')
        from app.llm.evidence_echo import BUILDERS
        builders = {**BUILDERS, 'segment.dims': _segment_echo,
                    **{name: _persona_echo for name in (
                        'persona.card', 'persona.summary', 'persona.prescribe',
                        'persona.constraint_check', 'insight.derive', 'insight.concept')}}
        try:
            echo = json.loads(raw) == {'echo': True}
        except (ValueError, TypeError):
            echo = False
        if echo and task.task in builders:
            try:
                raw = json.dumps(builders[task.task](task), ensure_ascii=False)
            except (ValueError, KeyError, IndexError, TypeError):
                return failure('schema', 'Invalid fake task input')
        return validate(task, raw)


def _persona_echo(task):
    """Echo only supplied Context IDs and evidence numbers; explicit responses win."""
    payload = json.loads(task.attachments[0].body)
    if task.task == 'persona.card':
        # The QA script marks exactly one confirmed identity, never production data.
        if '[QA-P6:invalid-card]' in payload.get('persona_name', ''):
            return {'contexts': []}
        rows = []
        for context in payload['context_evidence']:
            cid = context['context_id']
            cites = [key for key, ref in payload['evidence'].items() if ref['context_id'] == cid]
            rows.append(dict(context_id=cid, **{field: dict(
                text=context['situation'].get(field) if cites else None,
                cite=cites[:1] if context['situation'].get(field) is not None else [])
                for field in ('state', 'emotion', 'barrier')}))
        return dict(contexts=rows)
    if task.task == 'persona.summary':
        cite = list(payload['evidence'])[:1]
        return dict(intent=dict(text='쾌적한 생활을 원한다',
            basis_context_ids=payload['context_ids'], reserved_context_ids=payload['counter_context_ids']),
            usage_context=dict(text='실내 냉방 사용', cite=cite),
            jtbd=dict(text='편안하게 쉬기', cite=cite),
            journey=dict(pre_purchase=None, purchase=None, post_purchase=None),
            sensitivity=dict(price='상', brand='중', feature='상'), values=None, decision_style=None)
    if task.task == 'persona.prescribe':
        violating = payload['card_summary'].get('persona_id') == 'CL0-P0'
        return dict(direction='에어컨으로 질병을 치료한다고 안내한다' if violating else '예약 조절을 안내한다',
            target_metric='사용 만족도', contribution='조절 부담을 줄인다',
            journey_hypothesis='ENTRY 예약 안내 → EXPAND 사용 적응 → COMMIT 지속 사용')
    if task.task == 'persona.constraint_check':
        violating = '질병을 치료' in json.dumps(payload['prescription'], ensure_ascii=False)
        return dict(constraints=[dict(constraint=value, verdict='violates' if violating else 'ok',
            reason='의료적 효과를 단정함' if violating else '제약을 준수하는 가짜 응답')
            for value in payload['constraints']])
    if task.task == 'insight.derive':
        ids = [row['context_id'] for row in payload['contexts']]
        return dict(items=[dict(id=f'I{n+1}', title=f'냉방 조절 경험 개선 {n+1}',
            pain_point='냉방을 조절할 때 번거로움을 겪는다.', context_ids=[ids[n % len(ids)]],
            known_ki_id=None) for n in range(3)])
    return dict(persona_profile='편안한 실내 생활을 원하는 합성 사용자',
        pain_points=list(payload['evidence'])[:3],
        journey=[dict(context_id=row['context_id'], action=row['action'], feeling='번거롭다',
            service='예약 조절 안내', service_action='예약 방법을 안내한다', cx_4d='시스템')
            for row in payload['contexts']])


def _segment_echo(task):
    return {'items': [dict(doc_id=a.title, environment='여름 실내',
        internal_state='더위 걱정', task_goal='쾌적한 냉방', activity_response='예약 운전',
        resource_constraint='전기료 부담') for a in task.attachments]}
