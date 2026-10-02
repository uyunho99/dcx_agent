# T13 report — shared persona and insight components

Status: complete. Continued the existing uncommitted implementation and retained its working components. No backend edits, staging, commits, subagents, or Next build in this continuation.

## Requirements reviewed

Read `task-T13-brief.md` first, followed by `docs/development/dcx2-stage8/02-design.md`, the referenced stage6-8 design (particularly sections 5, 9, 10 and 14), and mockup screens s5/s6/s7. Reused Person A DS classes and tokens, T12 types/helpers and the existing DS provisional badge.

## Delivered components

- `GradeMark`: exact ● 관측 / ▲ 추론 / ✕ 추측 text and shapes; null displays 근거 부족.
- `ProvisionalBadge`: DS badge with exact 잠정 copy.
- `CCMTable`: Context columns, two-table folding above four Contexts using T12 foldColumns, fixed widths and wrapping, 반례 columns, native disclosure buttons with aria-expanded/aria-controls and evidence panels accepting ReactNode.
- `OpportunityMap`: SVG role=img with all six zone counts in aria-label, supplied baselines, five cluster shapes then circle plus cluster ID, three Persona tones, hollow counter points, ★, two-level toggle chips, unchanged overlapping coordinates with count tooltips. Added visible Korean zone labels matching the mockup. Hover/focus emphasis uses an outline; blue is reserved for selected or legend-chosen Personas.
- `ContextTable`: all eight sortable columns, opportunity descending by default, shared focus/hover highlighting and 카드 열기 callback. Overlapping Contexts each remain available.
- `HierarchyTree`: product → Cluster → Persona → Context, node area proportional to document count, visible counts and accessible summary.
- `Radar`: exact axes Computed / Connected / Shared and sentences 맞춤형 서비스가 필요해 / 실시간으로 직접 보고 싶어 / 함께 즐기고 싶어. Raw and percentile polygons differ by solid/dashed strokes; textual values and 잠정 are included.
- `OpportunityBars`: added descending ranking without mutating caller data; supplied mean appears as a labeled dashed line, with 잠정 and an empty state.
- `JourneyTable`: AS-IS / TO-BE headers, ⚪ 처방, and 정신적 / 물리적 / 문화적 / 시스템 counts. Preserves the approved mockup's Context-as-rows orientation; more than four Contexts split into two vertically stacked table sections with repeated headers. This reconciles the design's two-section requirement with the mockup's row orientation.
- `RevisionList`: native 판 보기 / 이 판으로 되돌리기 buttons, callbacks, current marker, and busy/current-revert disabled states.

## TDD and final validation

The prior worker's implementation and tests were already present. This continuation added seven regression tests before implementation changes. The first targeted run visibly failed: 3 failed / 26 passed, covering hover color and zone labels, journey splitting, and bar ordering. After fixes, the targeted run passed all 29 component tests.

Additional new assertions cover exact radar sentences and missing values, hierarchy accessibility and area scaling, revision disabled states, and evidence-panel switching. Existing coverage includes fold boundaries, all sort headers, legend toggles, native button activation handlers and both required review-focus tests:

- `test_ccm_ten_columns_fold_no_overflow`: two fixed-width tables, five Contexts each, wrapping and 100% width.
- `test_overlapping_points_table_lists_all`: identical point positions, overlap-count title and all Context rows.

Final commands, each run once in this continuation:

- `npm --prefix frontend test`: PASS — 54 files, 525 tests (29 component tests).
- `npm --prefix frontend run lint`: PASS — no warnings or errors.
- `cd frontend && ./node_modules/.bin/tsc --noEmit --incremental false`: PASS.

Next build was skipped as requested. The test runner printed Node's existing DEP0205 module.register deprecation warning.

## Integration contracts for T14/T15

Import named components from their individual files. Share `highlightedId` and `onHighlight` between map and table; pass `selectedPersonaId` for persistent selection and `onOpenCard(personaId, contextId)` for navigation.

CCM accepts `{id, name, counter?, cells}`; keys are action, state, emotion, barrier, keywords, artifact, satisfaction, opportunity. Cells contain text, optional grade and optional evidence ReactNode. The T12 folding helper accepts up to ten Contexts.

OpportunityMap accepts PersonaMap directly and derives presentation order from sorted cluster/Persona IDs. Legend toggles retain all points and change selection emphasis.

Tree, radar, bar and history wire formats remain intentionally opaque in T12. Screens must adapt them to exported presentation types: HierarchyNode (`id/name/doc_count/children`), RadarValues (raw and percentile for each axis; percentile 0–100), OpportunityBar (`id/label/value`), RevisionEntry. Revision mutations and error handling belong to the screens.

## Concerns and limits

- Tests use the repository's Node/static-render/direct-handler harness. The 1024px overflow assertion is structural/CSS coverage, not a browser measurement; native Enter/Space behavior and screen-reader output still need browser integration QA.
- JOURNEY uses Context rows as in the approved mockup, rather than transposing into Context columns as the design's folding sentence suggests; long journeys nevertheless split into two sections.
- Opaque API envelopes require the presentation adapters described above.
- Existing unrelated backend changes were left untouched.
