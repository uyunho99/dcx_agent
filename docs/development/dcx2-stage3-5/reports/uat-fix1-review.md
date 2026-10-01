**U1: Addressed.**
- `CoveragePanel.tsx:6-11` adds `coverageInterpretation`, which returns the exact R-114 copy only when `status === 'unconnected'`. That matches the backend flag at `rounds.py:364`.
- The round copy is unchanged. Connected coverage with 0 queries still shows "누락 쿼리 0개…", and the tests cover that (`CoveragePanel.test.ts`).
- The brief said "humanQueries empty / unconnected". The code keys on status only, and R-114's "(사람 쿼리 0개)" is satisfied because unconnected always means 0.

**U2: Addressed.**
- `QueueCard.tsx:66-87` has four labelled rows: 대상 경험, 6차원, 상황, and 신호 · Non 사유 with two labelled `Select`s.
- `queueCard.css`:
  - Gap is 8px between buttons and 16px between rows (the spec asked for at least 8 and 12).
  - Chips have `min-height:36px`.
  - Pressed chips are filled with `--action`, and a focus-visible outline is added.
  - The `.queue-card-controls .ds-chip` selectors outrank `.ds-chip` in `ds.css:56-57`.
- Keyboard and aria behavior is kept. `TagToggle` is untouched (`aria-pressed` and the `<kbd>` shortcut hints remain), and `aria-live` is intact.
- New tests check the group names, 8 toggles, the shortcuts and `aria-live`.

**U3: Addressed.**
- `KnownInsightsDrawer.tsx:13-26` makes each item a `ds-card` with badges on top, a body, and a footer with the date on the left and a small quiet "삭제" on the right.
- Doc items clamp to 3 lines (`.module.css` `.clamped`). The 펼치기/접기 toggle has `aria-expanded` and `aria-controls` tied to the body id.
- The delete button keeps its `aria-label` and its disabled state. The warning keeps `role=status`. The date is now a `<time>` element.
- Tests cover the disclosure, the footer order, and the disabled delete.

**U4: Addressed.**
- `base.py:30-35` filters `naver_shopping` and `naver_searchad` out of `integration_status()`, so the "0/N" count updates too.
- The `INTEGRATIONS` dict, env names and adapters are untouched, which respects D-023.
- Test edits are narrow: they swap the name-set assertions (`test_api.py`, `test_final_w4.py`) and add a name-list assertion in `test_integration_stage0_2.py`.
- The secret-non-exposure assertions are unchanged, including `sentinel not in …` and `settings value not in response.text`.
- In `test_final_w4.py` the shopping-specific assertions (`not connected`, `env_vars == []`, '종료' in `last_error`) were removed. That is correct now that the entry is gone. The `youtube` and `naver_search` exclusion is kept.

**New issues**

Critical: none.

Important: none.

Minor:
1. `IntegrationsDrawer.tsx:11,66,73` and `__fixtures__/integrations.json` still carry naver_shopping/naver_searchad special cases. This is dead code that is harmless but stale. It is arguably fine to keep for D-023 and the fixture.
2. In `QueueCard.tsx:80`, the Non 사유 select now always renders and is disabled unless `level === 'non'`. Before, it appeared only for Non. This is a small, reasonable layout choice. It is unspecified in the brief but tested.
3. The row label "대상 경험" and the toggle "대상 경험" are visually duplicated. This is only a UI nit, since the group `aria-label` and the button name stay distinct from the visible span.

Verdict: Approved
