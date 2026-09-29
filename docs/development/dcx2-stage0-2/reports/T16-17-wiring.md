# T16–T17 wiring follow-up

## Changes

- Registered `youtube`, `clien`, and `ppomppu`, matching backend context channel IDs and frontend `channelNames`. Naver remains unregistered. Factories construct adapters only when called; fixture configuration is read at call time. The real adapters have no global enable flags or required API keys in `config.py`: YouTube availability checks the local yt-dlp dependency, and community availability is local-only.
- Reviewed design sections 2.3 and 6.2 and both adapter reports. Availability now deliberately exposes the three real channels in crawl status/settings, and `projectContext.channels` defaults select their available intersection. The existing frontend already supports these IDs; no frontend change is needed. Fixture remains gated by its enable flag and corpus. Added a real-registry API test with mocked spawning that verifies the available list and excludes unimplemented Naver from project defaults.
- Workers use an ExitStack with try/finally cleanup for optional adapter `close()`, including coordinator errors, partial factory construction, and run initialization failures. Healthcheck closes after successful or failed list/detail work; availability closes its temporary adapters too. Existing adapters without close remain supported.
- Community populated dates are calendar-only `YYYY-MM-DD`, including Ppomppu JSON comments and rendered comments. Missing dates retain None/empty-string conventions. Tests assert lengths and exact captured dates for list items, documents, and comments.
- YouTube DownloadError bot-confirmation messages with straight or curly apostrophes now raise AdapterBlocked in list and fetch. HTTP 403/429 handling remains; an unrelated DownloadError still propagates.
- Appended T17's Follow-up documenting that Ppomppu pagination beyond page 1 is inferred from synthetic links, not verified real captures.

## TDD and offline verification

1. Added failing tests before production edits for registration, availability cleanup, worker/healthcheck lifecycle, community dates, and synthetic YouTube bot errors.
2. RED targeted run: **23 failed, 65 passed; rc=1**. One overly strict assertion included missing Ppomppu list dates; narrowed that assertion to populated dates, preserving the existing missing-date contract.
3. GREEN targeted run: **88 passed; rc=0**.
4. Added worker setup-failure coverage (**4 passed; rc=0**) and a real-registry status/project-default test. Initial full run: **1 failed, 665 passed; rc=1** due to incomplete context in the new test setup. Corrected the test's stored session setup and ensured yt-dlp loads before the test replaces subprocess.Popen (yt-dlp subclasses it). The API test then passed independently: **1 passed; rc=0**.
5. Crawl tests now fail before real socket connections. Adapter tests use committed captures, MockTransport, or synthetic yt-dlp errors. Existing integration tests block network and select fixture through config. Audited worker callers: changed the active-collection location test to explicitly select fixture; subprocess tests select fixture from their manifest/snapshot and use fake registration hooks. Existing settings tests that intentionally inject fixture-only availability retain that contract.
6. Required full command: `cd backend && .venv/bin/python -m pytest -q; echo rc=$?` — **666 passed, 2 warnings in 37.22s; rc=0**. The final API-test import-order adjustment was also verified independently (rc=0).
   `git diff --check` — **rc=0**.
7. Frontend was not touched; conditional vitest command was not run.

## Concerns

- No live-site validation was performed. Ppomppu later-page behavior remains inferred; recorded page 1 has no next-page links.
- Existing timed-out detail calls use abandoned daemon threads; Python cannot forcibly terminate them. Cleanup closes adapter resources when the worker exits, and any late results remain discarded by the existing worker logic.
- Existing Pydantic configuration deprecation and joblib physical-core fallback warnings remain.
- The pre-existing `.DS_Store` modification was left untouched. No git add or commit was performed.
