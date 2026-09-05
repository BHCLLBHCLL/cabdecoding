"""STpreSession ownership guard: never hide/quit a user-open STpre."""
from __future__ import annotations

import pytest  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _com_leak_guard(com_guard):
    """I4: reap any preprocessor process leaked by this module."""
    yield

import subprocess

import pytest


class _Flag:
    def _FlagAsMethod(self, name):
        return self


class _QuitRecorder(_Flag):
    def __init__(self):
        self.quit_calls = 0
        self.visible = True

    def Quit(self):
        self.quit_calls += 1


def test_stpre_process_running_detects_tasklist(monkeypatch):
    import cab_stpre_api
    pytest.importorskip("win32com.client")

    def fake_run(cmd, **kw):
        return type("R", (), {"stdout": "STpre_Bx64net.exe  1234 Console\n"})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cab_stpre_api._stpre_process_running() is True

    def empty_run(cmd, **kw):
        return type("R", (), {"stdout": ""})()

    monkeypatch.setattr(subprocess, "run", empty_run)
    monkeypatch.setattr(
        "win32com.client.GetActiveObject",
        lambda progid: (_ for _ in ()).throw(RuntimeError("not running")))
    assert cab_stpre_api._stpre_process_running() is False


def test_ensure_open_refuses_when_attach_disabled(monkeypatch):
    import cab_stpre_api
    monkeypatch.setattr(cab_stpre_api, "_stpre_process_running",
                        lambda: True)

    def _no_dispatch(progid):
        raise AssertionError("must not attach to a running instance")

    monkeypatch.setattr("win32com.client.Dispatch", _no_dispatch)
    # attach=False keeps the legacy refusal
    session = cab_stpre_api.STpreSession(attach=False)
    assert session.ensure_open("relay.cab") is False
    assert session._owned is False
    assert session._app is None
    assert "already running" in (cab_stpre_api.last_error or "")


def test_ensure_open_attaches_to_running_instance(monkeypatch):
    """Unfrozen policy: default attach=True drives the running instance
    via GetActiveObject and never marks it owned (so close() won't quit it).
    """
    import cab_stpre_api
    monkeypatch.setattr(cab_stpre_api, "_stpre_process_running",
                        lambda: True)

    class FakeDoc(_Flag):
        def __init__(self):
            self.opened = []

        def OpenCabFile(self, path):
            self.opened.append(path)
            return 1

        def GetMesher(self):
            return _Flag()

    class FakeApp(_Flag):
        def __init__(self):
            self.doc = FakeDoc()

        def GetDocument(self):
            return self.doc

        def Quit(self):
            raise AssertionError("attached instance must not be quit")

    fake_app = FakeApp()
    monkeypatch.setattr("win32com.client.GetActiveObject",
                        lambda progid: fake_app)
    session = cab_stpre_api.STpreSession()  # attach=True by default
    assert session.ensure_open("relay.cab") is True
    assert session._owned is False          # attached, not owned
    assert session._app is fake_app
    assert fake_app.doc.opened == ["relay.cab"]
    session.close()                          # must NOT call Quit


def test_close_only_quits_owned_instance(monkeypatch):
    import cab_stpre_api
    session = cab_stpre_api.STpreSession()
    recorder = _QuitRecorder()
    session._app = recorder
    session._owned = False
    session.close()
    assert recorder.quit_calls == 0
    assert session._app is None

    recorder = _QuitRecorder()
    session._app = recorder
    session._owned = True
    session.close()
    assert recorder.quit_calls == 1


def test_start_hides_and_owns_new_instance(monkeypatch):
    import cab_stpre_api
    pytest.importorskip("win32com.client")
    monkeypatch.setattr(cab_stpre_api, "_stpre_process_running",
                        lambda: False)
    recorder = _QuitRecorder()

    class FakeDoc(_Flag):
        def __init__(self):
            self.mesher = _Flag()
            self.saved = []

        def OpenCabFile(self, path):
            self.saved.append(path)
            return 1

        def GetMesher(self):
            return self.mesher

    class FakeApp(_Flag):
        def __init__(self):
            self.doc = FakeDoc()

        Visible = True

        def GetDocument(self):
            return self.doc

        def Quit(self):
            recorder.quit_calls += 1

    fake_app = FakeApp()
    monkeypatch.setattr("win32com.client.Dispatch",
                        lambda progid: fake_app)
    session = cab_stpre_api.STpreSession()
    assert session.ensure_open("relay.cab") is True
    assert session._owned is True
    assert fake_app.Visible is False
    assert session.is_open is True
    session.close()
    assert recorder.quit_calls == 1
