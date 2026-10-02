- **Important — `backend/app/segment/dims.py:239`**: Valid stage-five exports can contain `tagProbs: null` when a model head is unavailable, even with usable vectors and confirmed Core labels. `_summary()` crashes with `AttributeError`, blocking segmentation and every resume. **Fix:** normalize nullable mappings and skip Act mismatch counting when probabilities are unavailable.

- **Important — `backend/app/routers/segment.py:222`**: Personas are read before their `run`. A concurrent reset can return old Persona rows tagged with the new generation, defeating stale-run protection when IDs are reused. Reproduced with an in-memory interleaving. **Fix:** read generation and rows from one SQLite snapshot.

- **Important — `backend/app/context/versions.py:303`**: Stage-six comparison scans `versions/vN/stage6/`, while results live in `versions/vN/segment/`. Different results—or completed versus reset versions—therefore report identical empty results. This breaks the comparison promised for historical versions under D-238. **Fix:** explicitly compare stage-six reports and saved confirmations.

- **Minor — `frontend/src/components/segment/SegmentScreen.tsx:76`**: Navigating away within the 600 ms autosave debounce cancels the pending save and silently loses the latest edits. The component registers no dirty-navigation protection. **Fix:** retain and flush pending edits on navigation, or guard navigation until saving completes.

Recommendation: fix before merge because valid exports can block segmentation, generation labeling can admit stale confirmations, and historical comparisons hide actual changes.
