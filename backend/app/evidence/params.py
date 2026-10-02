"""Stage-seven tuning values (D-211); record used values in result params."""
QUERY_DIMS = ('Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome', 'Counter', 'Residual')
FORBIDDEN = r'페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은'
TOP_PER_QUERY = 15          # 4.2
CANDIDATES_M = 50           # 4.2
CORE_BONUS = 0.05           # 4.2 (Counter 제외)
TAG_BATCH = 8               # 4.3
TAG_BODY_CHARS = 1500; TAG_COMMENTS = 10; TAG_COMMENT_CHARS = 300; KI_SUMMARY_CHARS = 200
SELECT_N = 10               # 4.4
W_RARITY = 0.3              # 잠정
DPP_SIGMA = 0.3             # 잠정
COVERAGE_MIN = 4            # /6, 미만이면 보충
COVERAGE_EXTRA = 15
TAG_PROB_ON = 0.5
RARE_MIN = 2
DUP_COSINE = 0.95           # 4.5 ⓒ
NEW_EXPAND = 50; NEW_EXPAND_MAX = 3
NOVELTY_SHOW = ('high', 'very_high')   # 잠정 임계
NOVELTY_CORE_REPS = 5
COUNTER_POLARITY_GAP = 0.3; COUNTER_TOP = 5; RARE_TOP = 5; DESIRE_TOP = 5
UNDIFF_COSINE = 0.8; UNDIFF_MIN = 3
CONCURRENCY = 4             # D-250, settings.evidence_llm_concurrency로 덮어씀
PROVISIONAL = ('W_RARITY', 'DPP_SIGMA', 'NOVELTY_SHOW', 'odi', 'persona_metrics')
