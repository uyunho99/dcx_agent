Status: PASS — U4 complete.

- Filtered `naver_shopping` and `naver_searchad` from the backend `/integrations` response builder. The drawer and connection count now use only OpenAI and Claude (0/2 when unconfigured).
- Preserved adapter code, integration configuration, environment names, and secret-non-exposure assertions. Updated related backend listing tests for configured and unconfigured credentials. No frontend edits were needed.
- Verification from repository root: `backend/.venv/bin/python -m pytest backend/tests -q` — **1279 passed, 2 warnings**, 133.33s. Warnings concern Pydantic class-based config deprecation and joblib physical-core detection.
- No commit created.
