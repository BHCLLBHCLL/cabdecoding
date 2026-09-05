"""I4: COM-process leak guard — session reaper skips baseline pids and
kills only processes launched during the guarded window."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conftest


class _FakeProc:
    def __init__(self, pid):
        self._pid = pid

    def kill(self):
        conftest._KILLED.append(self._pid)


def test_preprocessor_pids_returns_mapping(monkeypatch):
    class _P:
        info = {"pid": 1, "name": "STpre_Bx64net.exe"}

        def __iter__(self):
            return iter([self])

    monkeypatch.setattr(conftest, "_LEAK_TARGETS", ("stpre",))
    monkeypatch.setattr("psutil.process_iter", lambda args: iter([]))
    assert conftest._preprocessor_pids() == {}


def test_reap_kills_only_new_pids(monkeypatch):
    """Baseline pids (user-opened) survive; new pids are killed."""
    conftest._KILLED = []
    monkeypatch.setattr(
        conftest, "_preprocessor_pids",
        lambda: {100: "STpre_Bx64net.exe", 200: "scFLOWpre_Bx64net.exe"})

    import psutil
    monkeypatch.setattr(psutil, "Process", _FakeProc)
    reaped = conftest._reap_leaked_com_processes({100: "STpre_Bx64net.exe"})
    assert conftest._KILLED == [200]
    assert reaped == [(200, "scFLOWpre_Bx64net.exe")]


def test_reap_tolerates_kill_failure(monkeypatch):
    conftest._KILLED = []

    class _Boom:
        def __init__(self, pid):
            pass

        def kill(self):
            raise PermissionError("refused")

    import psutil
    monkeypatch.setattr(psutil, "Process", _Boom)
    monkeypatch.setattr(conftest, "_preprocessor_pids",
                        lambda: {300: "STpre_Bx64net.exe"})
    assert conftest._reap_leaked_com_processes({}) == []
