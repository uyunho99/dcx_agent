import os

from app.work.proc import pid_alive


def test_pid_alive_rejects_nonpositive():
    assert pid_alive(0) is False
    assert pid_alive(-1) is False
    assert pid_alive(os.getpid()) is True
    from app.crawl.control import pid_alive as control_alive
    from app.crawl.queue import _alive as queue_alive
    from app.llm.codex_exec import _alive as codex_alive
    assert control_alive is queue_alive is codex_alive is pid_alive


def test_pid_alive_os_errors(monkeypatch):
    def missing(*args):
        raise ProcessLookupError
    monkeypatch.setattr(os, 'kill', missing)
    assert pid_alive(123) is False
    def denied(*args):
        raise PermissionError
    monkeypatch.setattr(os, 'kill', denied)
    assert pid_alive(123) is True
