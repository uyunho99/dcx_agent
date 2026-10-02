"""Stage-eight constants; provisional values are recorded with generated output."""

CARD_CHUNK = 4                       # D-302
TRACE_MIN = 0.5                      # 5.3 Traceable Support 하향 임계(잠정)
OBSERVED_FIELDS = ('state', 'barrier', 'usage_context')
INFERRED_FIELDS = ('emotion', 'jtbd', 'unmet_need')
S_LINE = 0.5                         # 5.5 가로 기준선
STAR_NOVELTY = ('high', 'very_high'); STAR_MIN = 2
RADAR_AXES = {'Computed': '맞춤형 서비스가 필요해', 'Connected': '실시간으로 직접 보고 싶어', 'Shared': '함께 즐기고 싶어'}
INSIGHT_RANGE = (3, 8)
CX_4D = ('정신적', '물리적', '문화적', '시스템')
PROVISIONAL = ('odi', 'persona_metrics', 'TRACE_MIN', 'RADAR_AXES')
