"""P2 external-tools batch offscreen tests: WindTool / PICLS / scConverter /
HeatPathView launch wiring.

Reuses test_p1's offscreen + CabViewer fixture; every _launch_program is
mocked - no real external EXE is spawned.
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import cab_gui

pytestmark = pytest.mark.skipif(
    not cab_gui._HAS_GUI_DEPS, reason="PyQt5/vtk not installed")

HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def viewer(qapp):
    win = cab_gui.CabViewer(CAB, enable_3d=False)
    yield win
    win.close()


def _tool_actions(viewer):
    menus = [a for a in viewer.menuBar().actions() if a.menu()]
    tools = next(m for m in menus if m.text().startswith("Tools"))
    return [a.text() for a in tools.menu().actions()]


# ------------------------------------------------------ Tools 菜单接线

def test_tools_menu_external_actions(viewer):
    texts = _tool_actions(viewer)
    assert "Execute WindTool…" in texts
    assert "Execute PICLS…" in texts
    assert "Execute scConverter…" in texts
    assert "Execute HeatPathView…" in texts


# ------------------------------------------------------ EXE 定位

def test_external_tool_exe_cab_tools_first(viewer, monkeypatch):
    monkeypatch.setattr(
        "cab_tools.find_cradle_tool",
        lambda key: Path("X:/Cradle") / (key + ".exe"))
    assert viewer._external_tool_exe("windtool") == \
        str(Path("X:/Cradle/windtool.exe"))


def test_external_tool_exe_fallback_find_program(viewer, monkeypatch):
    monkeypatch.setattr("cab_tools.find_cradle_tool", lambda key: None)
    monkeypatch.setattr(
        viewer, "_find_program", lambda names: "Y:/" + names[0])
    assert viewer._external_tool_exe("picls") == "Y:/PICLS_Bx64net.exe"


# --------------------------------------------------------- P2-1 WindTool

def _fake_launch(launched):
    def _l(exe, args, cwd=None):
        launched.append((exe, list(args), cwd))
        return True
    return _l


def test_run_windtool_launches_with_info(viewer, monkeypatch, tmp_path):
    launched = []
    flds = [str(tmp_path / f"w{i:02d}.fld") for i in range(16)]
    monkeypatch.setattr(viewer, "_external_tool_exe",
                        lambda key: "X:/WindTool_Bx64.exe")
    monkeypatch.setattr(viewer, "_launch_program", _fake_launch(launched))
    assert viewer._run_windtool("X:/proj.cab", flds)
    exe, args, cwd = launched[0]
    assert exe == "X:/WindTool_Bx64.exe"
    assert args[0] == "X:/proj.cab"
    info = Path(args[1])
    assert info.exists()
    text = info.read_text(encoding="utf-8")
    assert text.startswith("INPUT_FLD_FILES")
    assert all(p in text for p in flds)


def test_run_windtool_requires_16_fld(viewer, monkeypatch):
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda *a, **k: pytest.fail("should not launch"))
    assert viewer._run_windtool("X:/p.cab", ["a.fld"]) is False
    assert viewer._run_windtool("X:/p.cab", list(range(17))) is False


def test_run_windtool_no_exe_false(viewer, monkeypatch):
    monkeypatch.setattr(viewer, "_external_tool_exe", lambda key: None)
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda *a, **k: False)
    flds = [f"w{i}.fld" for i in range(16)]
    assert viewer._run_windtool("X:/p.cab", flds) is False


# --------------------------------------------------------- P2-2 PICLS

def test_run_picls_cwd_injection(viewer, monkeypatch):
    launched = []
    monkeypatch.setattr(viewer, "_external_tool_exe",
                        lambda key: "X:/PICLS_Bx64net.exe")
    monkeypatch.setattr(viewer, "_launch_program", _fake_launch(launched))
    assert viewer._run_picls("D:/work")
    exe, args, cwd = launched[0]
    assert exe == "X:/PICLS_Bx64net.exe"
    assert args == []           # 空参 (无公开 CLI 文档, B 级定档)
    assert cwd == "D:/work"     # 目录注入


def test_run_picls_no_exe_false(viewer, monkeypatch):
    monkeypatch.setattr(viewer, "_external_tool_exe", lambda key: None)
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda *a, **k: False)
    assert viewer._run_picls("D:/work") is False


# ------------------------------------------------- P2-3 scConverter / HeatPathView

def test_run_scconverter_args(viewer, monkeypatch):
    launched = []
    monkeypatch.setattr(viewer, "_external_tool_exe",
                        lambda key: "X:/scConverter_Sx64net.exe")
    monkeypatch.setattr(viewer, "_launch_program", _fake_launch(launched))
    assert viewer._run_scconverter("a.fld", "b.csv")
    assert launched[0][0] == "X:/scConverter_Sx64net.exe"
    assert launched[0][1] == ["a.fld", "b.csv"]


def test_run_heatpathview_args(viewer, monkeypatch):
    launched = []
    monkeypatch.setattr(viewer, "_external_tool_exe",
                        lambda key: "X:/HeatPathView_Bx64.exe")
    monkeypatch.setattr(viewer, "_launch_program", _fake_launch(launched))
    assert viewer._run_heatpathview("X:/res.pst")
    assert launched[0][1] == ["X:/res.pst"]
    assert viewer._run_heatpathview("")
    assert launched[1][1] == []


def test_launch_program_logs_missing(viewer, monkeypatch):
    monkeypatch.setattr(viewer, "_external_tool_exe", lambda key: None)
    n0 = len(viewer.message_win.text.toPlainText().splitlines())
    assert viewer._run_heatpathview("X:/res.pst") is False
    out = "\n".join(viewer.message_win.text.toPlainText().splitlines()[n0:])
    assert "Program not found" in out
