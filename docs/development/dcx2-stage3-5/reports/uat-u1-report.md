PASS — U1 completed; no commit.

- Added `coverageInterpretation` in `CoveragePanel.tsx` and used it for the interpretation text. `status === 'unconnected'` shows the exact requested Korean message; other statuses retain the existing text.
- Wrote `CoveragePanel.test.ts` first: six helper cases cover unconnected coverage with empty/absent queries and unchanged wording for other statuses.
- Test-first run: six new tests failed because the helper was not implemented; 230 existing tests passed.
- Final `npm --prefix frontend test -- --run`: 42 test files, 236 tests passed (exit 0).
- Writes limited to the component, its test file, and this requested report.
