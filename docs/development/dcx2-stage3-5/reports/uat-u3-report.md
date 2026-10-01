PASS — U3 implemented; frontend tests and lint pass.

- Known Insight items now use bordered design-system cards with type/source badges, body text, and a footer with caption date left and small quiet 삭제 button right.
- Document text initially clamps to three lines; 펼치기/접기 toggles each item independently with aria-expanded and aria-controls. Existing delete names, disabled behavior, dialog focus handling, and shared focus outlines are preserved.
- Changes are limited to KnownInsightsDrawer.tsx, its adjacent CSS module and four rendering tests, plus this requested report. No commit.
- `npm --prefix frontend test -- --run`: passed, 43 files / 242 tests (including 4 new drawer tests). Node emitted a module.register deprecation warning.
- `npm --prefix frontend run lint`: passed, exit 0, no diagnostics.
- Browser interaction and visual layout were not manually verified.
