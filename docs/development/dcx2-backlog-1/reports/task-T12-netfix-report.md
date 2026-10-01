# T12 network isolation fix

Status: PASS — RED reproduced before fixes; full backend suite GREEN after fixes.

## Changes

- `backend/tests/conftest.py`: function-scoped autouse fixture defaults `settings.autocomplete_backend` to `fake` for every test. Adapter tests can still explicitly select `http` and supply `httpx.MockTransport`.
- A second autouse fixture guards `socket.socket.connect`, rejecting non-loopback AF_INET/AF_INET6 destinations with `pytest.fail`. This failure escapes application exception handlers instead of becoming an unavailable/failed coverage result. Loopback IP addresses, `localhost`, and Unix sockets delegate to the original method. Monkeypatch cleanup preserves existing test-local socket patches.
- `backend/tests/test_no_network.py`: commits rounds 1 and 2 with synchronous background execution, asserts zero external connection attempts, and verifies connected autocomplete coverage. Additional cases verify external IPv4, IPv6, private IP, and hostname rejection, plus delegation for IPv4/IPv6 loopback, localhost, and Unix sockets.
- No application code changed. No commit created. Existing unrelated workspace changes were left intact.

## RED evidence

Before editing `conftest.py`, ran from the repository root:

```text
backend/.venv/bin/python -m pytest backend/tests/test_no_network.py -q
FAILED backend/tests/test_no_network.py::test_round_two_commit_makes_zero_external_connects
1 failed, 1 warning in 22.20s
```

The zero-connect assertion recorded 21 attempts to port 443. The regression test replaces DNS resolution with the documentation address `203.0.113.1` and intercepts socket connections before raising `OSError`, so RED sends no real DNS or HTTPS traffic. The commit still returned HTTP 200, reproducing the hidden network failure path. The test does not override the autocomplete backend.

## GREEN evidence

After adding both fixtures:

```text
backend/.venv/bin/python -m pytest backend/tests/test_no_network.py -q
9 passed, 1 warning in 2.35s

backend/.venv/bin/python -m pytest backend/tests -q
1370 passed, 1 deselected, 2 warnings in 133.48s (0:02:13)
```

Both commands exited 0. The full suite includes the five affected W1 cases, HTTP adapter tests, tests with their own socket patches, and both multiprocess crawl tests (`test_concurrent_writers_no_locked_error` and `test_author_hash_concurrent_process_creation`). The requested command retains its configured deselection. Warnings concern Pydantic class-based configuration and joblib physical-core detection. `git diff --check` also passed.
