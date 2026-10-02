# Task T6 report

Status: COMPLETE — implementation and automated verification passed; browser QA remains the separately scheduled follow-up.

## Files changed

- `frontend/src/app/pipeline/start/page.tsx` — rebuilt stage-0 form and Markdown preview, integrated the committed T4/T5 helpers/components and T1 warning response.
- `frontend/src/app/pipeline/compare/page.tsx:17` — changed only the `fieldNames` line, adding `taskMode: '과제 유형'` and `personaSeeds: '생각하는 페르소나'`.
- `.superpowers/sdd/03-plan/task-T6-report.md` — this explicitly requested report.

No backend/T3 files, shared logic, components, types, labels, CSS, or test expectations were changed. No agents dispatched; no git add/commit performed.

## Brief implementation map

All start-page references below are to `frontend/src/app/pipeline/start/page.tsx`.

| Brief requirement | Implementation and line references |
|---|---|
| Separate task card above 0-A; exact descriptions and summary | Lines 227–235 use `ChoiceCards` with the two exact Korean descriptions, explanatory copy, and dynamic required/optional summary. `aria-labelledby` and `aria-describedby` connect the heading and summary. Committed ChoiceCards supplies keyboard behavior and responsive cards. Only `taskMode` changes when selected, preserving entered values. |
| 0-A order and research templates | Lines 236–263 order product/one-liner → full-width project type → research question → metrics → constraints/positioning → channels/known insights. Line 240 calls `researchTemplates(form.taskMode, form.bk)` and saves the template id/text. |
| Remove analysis-purpose controls; preserve legacy data | `single()` accepts only `projectType` at line 206 and is used at line 238. No analysis-purpose controls remain. Draft/server loading still uses `mergeStartForm` (lines 124, 132); saving sends the whole form (line 157), preserving loaded `analysisGoal`. Preview emits its line only when present (line 48). |
| Three metric inputs and add/delete | Lines 243–254 render metric name/source/question in `md:grid-cols-3`, exact mode-specific guidance, conditional group error, disabled add for blank names, and stored-row deletion. Lines 140–143 add a structured metric and clear all three inputs. Line 247 permits Enter in the name input. |
| Optional positioning, presets, custom input and clearing | Lines 74–91 use single `ChoiceChips` and `choosePositionPreset` (which applies the committed toggle behavior). Custom input uses `setPositionText`, 40-character input bounds, IME-safe Enter, and default/quiet buttons. The custom chip includes an axis-specific ✕ button with exact “가격대 직접 입력 지우기” / “시장 위치 직접 입력 지우기” accessible names (line 87). Line 257 uses native details/summary for metric mode, open when existing values require it; explore mode is expanded. |
| Persona card between 0-A and 0-B | Lines 264–275 render the exact card title/description, input, add button and seed badge. `addPersonaSeed` handles empty/duplicate/limit at lines 145–150. Empty and duplicate are silently ignored; 20 items disable entry/add and show the exact limit notice (lines 266–267). |
| Persona dimensions, missing perspectives, checkbox | Line 31 supplies the four short labels. Lines 268–273 render single chips labelled “{text} 디멘션”, use `toggleChoice` to clear tags, provide quiet deletion, and use `missingDimensions` (line 139) with full labels or “네 관점이 모두 있습니다.” only when seeds exist. Line 274 uses DS Checkbox with the exact label. |
| Persona responsive layout and keyboard entry | Lines 268–271 put name/tags/delete on one desktop row and name/delete above tags below md. Tag buttons have min-height 36px and use the existing wrapping chips. Lines 32–36 use `popoverKeyAction` for IME-safe Enter, called by persona, metric-name and custom positioning inputs. |
| Existing-session info banner based on original server context | Line 133 retains raw `data.projectContext` in `returned`, separately from the merged form. Line 222 calls `isPreTaskModeContext(returned)` and renders the exact info banner below the screen header. Real saves update `returned` (lines 170–173); draft saves do not. Session/version/reload changes clear old returned state at line 120. |
| Validation, field errors, first-invalid focus | Line 137 uses `validateStartForm(form)` directly. Product/one-liner (237), question (241), project type (206–208), metric group (243–252), and channels (260) consume returned errors. Native fieldsets retain accessible labels/descriptions and focusable group errors. Lines 153–155 retain first-invalid scroll/focus for submission. Metrics only receive an error in metric mode via the committed helper; positioning has no errors. |
| Section-3 Markdown preview | Lines 37–73 match the section structure and Korean renderer wording: task line after product, template, original project-type label, optional legacy analysis goal, structured metrics including source/question, positioning axes only with values, product classification/source, persona list/empty/missing dimensions and exploreBeyond instructions, baseline, known insights. Line 42 calls `mergeStartForm` only to normalize metrics; raw task/persona absence is retained for saved legacy previews. Line 287 continues to prefer saved server context for internal-tool preview. |
| R1-after-change info banner | Lines 172–173 capture `putContext` response warnings and updated context. Line 223 shows the exact requested info banner whenever warnings are nonempty. A later warning-free save replaces the array; session/version changes clear it (120). Saving remains allowed. |
| 0-B unchanged; one primary action | The 0-B JSX at lines 276–283 is byte-identical to the prior source, checked directly against HEAD. Line 285 is the sole `variant="primary"`, labelled “키워드 생성 시작하기”. All new buttons use default/quiet styling. |
| Version comparison labels | `frontend/src/app/pipeline/compare/page.tsx:17` adds only the two required labels. |

## Commands and results

- `npm --prefix frontend run lint` — final PASS, exit 0, no warnings/errors. Initial run found three explicit role=group/aria-invalid lint warnings; switching those input groups to native labelled fieldsets resolved them.
- `npm --prefix frontend test` — final PASS, exit 0: 50 test files, 355 tests. Re-run after the final accessibility markup change. Existing T4 start-form (35 tests) and T5 ChoiceCards (13 tests) suites pass. No test expectations changed.
- `npm --prefix frontend run build` — default Turbopack stayed at “Creating an optimized production build ...” without progress; interrupted with Ctrl-C (exit 130).
- `npm --prefix frontend run build -- --webpack` — PASS, exit 0: compilation, TypeScript, page data, 14/14 static pages and build traces completed.
- `git diff --check` — PASS.
- Read-only Python assertions against `git show HEAD:frontend/src/app/pipeline/start/page.tsx` — PASS: 0-B JSX unchanged, exactly one primary button, no analysis-goal control invocation.
- `git status --short` before writing this report — only the two owned source files modified.

No browser session, live API save, backend tests, or React render tests were run. Verification used the existing frontend suites; no keys or live network requests were needed for them.

## Concerns / follow-up

- Browser QA (QA-S1–S10), including live legacy-session loading/saving, warning-banner lifecycle, keyboard/IME interaction and mobile layout, remains for the user's later QA phase. Automated frontend tests are not React render tests.
- The brief uses shorthand `positioningOpen(form)`, but the committed helper signature is `positioningOpen(taskMode, position)`. The page calls that exact existing signature at line 257; no shared-file addition was needed.
- Turbopack stalled; webpack fallback passed. Node emitted the existing DEP0205 `module.register()` deprecation warning during tests/build; it did not fail verification.
- No blocking implementation concerns or required shared-component/logic changes remain.

## Fix round 1

Status: COMPLETE — Important 1 fixed; all three required verification commands passed.

### What changed

- `frontend/src/app/pipeline/start/page.tsx:99` stores positioning expansion independently from form values, initialized with `positioningOpen`.
- Lines 127 and 136 reset expansion from the loaded local draft or server context in the existing load effect (sid/legacy/reload/version dependencies at line 139).
- Lines 233–236 initialize expansion from current positioning when switching into metric mode. Selecting the already active metric mode does not reset it.
- Line 263 binds `<details>` to that expansion state and synchronizes native toggles through `onToggle`. Deselecting the last preset or clearing custom text no longer recomputes expansion or collapses the section.

### Commands and output summaries

- `npm --prefix frontend run lint` — PASS, exit 0; ESLint reported no warnings or errors.
- `npm --prefix frontend test` — PASS, exit 0; 50 test files and 355 tests passed, including 35 start-form tests.
- `npm --prefix frontend run build -- --webpack` — PASS, exit 0; compilation, TypeScript, page data, 14/14 static pages, optimization and build traces completed.
- `git diff --check` — PASS, exit 0; no whitespace errors.
- Read-only `git diff`, `git status --short`, and source/design inspection confirmed the narrow change and line references.

Concerns: No blocking concerns. Tests/build emitted the existing Node DEP0205 `module.register()` deprecation warning. Browser interaction QA was not run; existing automated suites do not exercise this native details interaction. Only the authorized start page and this report append were changed; no agents dispatched and no git add/commit performed.
