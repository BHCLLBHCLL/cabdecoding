"""P1 快赢批 offscreen 测试: 收敛残差曲线 / flowviewer 跳转 / OBJ-DXF-MDL 出口。

fake-solver 模式沿用 test_m40 (QProcess 跑当前 python, processEvents 轮询)。
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import cab_gui
from cab_solver_proc import SolverProcess, parse_residual_line

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
    proc = getattr(win, "_solver_proc", None)
    if proc is not None and proc.is_running():
        proc.stop()
    win.close()


def _pump(qapp, cond, timeout=10.0):
    """processEvents 轮询直到 cond 为真 (默认 10s 超时)。"""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return cond()


def _run_fake(qapp, body: str) -> SolverProcess:
    """跑一个假求解器 (当前 python -c body) 并等待退出。"""
    proc = SolverProcess()
    assert proc.start(sys.executable, ["-c", body])
    assert _pump(qapp, lambda: not proc.is_running())
    return proc


# ------------------------------------------------------------- P1-1 解析器

def test_parse_residual_line_formats():
    assert parse_residual_line("cycle 1 residual 0.5") == (1, 0.5)
    assert parse_residual_line("CYCLE 12 | residual 3.4e-5") == (12, 3.4e-05)
    assert parse_residual_line("residual 1e-4") == (-1, 1e-4)
    assert parse_residual_line("iteration 7: residual=0.25") == (7, 0.25)


def test_parse_residual_line_negative_and_none():
    # 无 residual 数值 / 无关键词 -> None (静默容错)
    assert parse_residual_line("CYCLE 99 done") is None
    assert parse_residual_line("step A") is None
    assert parse_residual_line("") is None
    assert parse_residual_line("max residual change") is None


# ---------------------------------------------------- P1-1 SolverProcess 累积

def test_solver_residual_accumulation_and_signal(qapp):
    seen = []
    proc = SolverProcess()
    proc.residual_point.connect(lambda c, v: seen.append((c, v)))
    assert proc.start(sys.executable, ["-c", (
        "print('cycle 1 residual 1.0', flush=True)\n"
        "print('cycle 2 residual 0.1', flush=True)\n"
        "print('cycle 3 residual 1e-2', flush=True)\n"
        "print('done', flush=True)\n")])
    assert _pump(qapp, lambda: not proc.is_running())
    assert proc.residual_points() == [(1, 1.0), (2, 0.1), (3, 0.01)]
    assert seen == [(1, 1.0), (2, 0.1), (3, 0.01)]


def test_solver_residual_reset_on_restart(qapp):
    body = "print('cycle 1 residual 0.5', flush=True)\n"
    proc = _run_fake(qapp, body)
    assert proc.residual_points() == [(1, 0.5)]
    assert proc.start(sys.executable, ["-c", body])
    assert _pump(qapp, lambda: not proc.is_running())
    # 重启后清零重新累积, 不叠加
    assert proc.residual_points() == [(1, 0.5)]


# ------------------------------------------------- P1-1 ConvergenceWindow 渲染

def test_convergence_window_data_and_render_smoke(qapp):
    from cab_panes import ConvergenceWindow
    w = ConvergenceWindow()
    w.resize(420, 200)
    assert not w.grab().isNull()          # 占位提示分支
    w.set_points([(1, 1.0), (2, 0.1), (3, 0.01)])
    assert not w.grab().isNull()          # 曲线分支
    assert w.points() == [(1, 1.0), (2, 0.1), (3, 0.01)]
    w.add_point(4, 1e-3)
    assert w.points()[-1] == (4, 1e-3)
    # 单点/等值/非正值不崩 (占位 + 钳位分支)
    w.set_points([(1, 0.5)])
    assert not w.grab().isNull()
    w.set_points([(1, 0.5), (2, 0.5), (3, 0.5), (4, 0.0)])
    assert not w.grab().isNull()
    w.clear()
    assert w.points() == []


def test_convergence_window_zero_value_clamped(qapp):
    from cab_panes import ConvergenceWindow
    w = ConvergenceWindow()
    w.resize(300, 150)
    # 含 0/负值的序列: log10 钳位不抛异常
    w.set_points([(1, 1.0), (2, 0.0), (3, -1.0), (4, 1e-4)])
    assert not w.grab().isNull()


# ------------------------------------------------------- P1-1 GUI 接线闭环

def test_gui_convergence_curve_auto_show(viewer, monkeypatch, tmp_path, qapp):
    """求解器残差行 -> 曲线窗格自动显示 + 点累积 (含 View 菜单勾选同步)。"""
    assert viewer.conv_pane.isHidden()
    assert not viewer._act_conv.isChecked()
    script = tmp_path / "fake_solver.py"
    script.write_text(
        "print('cycle 1 residual 1.0', flush=True)\n"
        "print('cycle 2 residual 0.5', flush=True)\n",
        encoding="utf-8")
    monkeypatch.setattr("cab_options.get_setting",
                        lambda key, default=None: default)
    assert viewer._start_solver_monitor(
        sys.executable, [str(script)], None, str(script))
    proc = viewer._solver_proc
    assert _pump(qapp, lambda: not proc.is_running())
    assert viewer.conv_win.points() == [(1, 1.0), (2, 0.5)]
    assert not viewer.conv_pane.isHidden()      # 自动显示
    assert viewer._act_conv.isChecked()


def test_gui_convergence_cleared_between_runs(viewer, monkeypatch, qapp):
    """两次求解之间曲线清零 (不叠加上一轮)。"""
    body = "print('cycle 1 residual 0.5', flush=True)\n"
    for _ in range(2):
        assert viewer._start_solver_monitor(
            sys.executable, ["-c", body], None, "case.s")
        proc = viewer._solver_proc
        assert _pump(qapp, lambda: not proc.is_running())
    assert viewer.conv_win.points() == [(1, 0.5)]


# ---------------------------------------------------------- P1-2 flowviewer

def test_flowviewer_launch_with_fld_result(viewer, monkeypatch, tmp_path):
    """有 .fld 结果 -> 子进程命令 [python, fv_gui.py, fld]。"""
    launched = []
    monkeypatch.setattr(viewer, "_find_flowviewer_entry",
                        lambda: "X:/fv/fv_gui.py")
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda exe, args, cwd=None:
                        launched.append((exe, args)) or True)
    fld = tmp_path / "case.fld"
    fld.write_bytes(b"x")
    monkeypatch.setattr(viewer, "_solver_run",
                        (str(tmp_path), str(tmp_path / "case.s")))
    viewer._open_in_flowviewer()
    assert launched == [(sys.executable,
                         ["X:/fv/fv_gui.py", str(fld)])]


def test_flowviewer_launch_without_result(viewer, monkeypatch):
    """无结果文件 -> 无路径参数启动。"""
    launched = []
    monkeypatch.setattr(viewer, "_find_flowviewer_entry", lambda: "X:/fv.py")
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda exe, args, cwd=None:
                        launched.append((exe, args)) or True)
    monkeypatch.setattr(viewer, "_solver_run", (None, None))
    monkeypatch.setattr(viewer, "_last_result_pst", None, raising=False)
    viewer._open_in_flowviewer()
    assert launched == [(sys.executable, ["X:/fv.py"])]


def test_flowviewer_entry_missing_warns(viewer, monkeypatch):
    """入口缺失 -> WARN 日志且不启动。"""
    monkeypatch.setattr(viewer, "_find_flowviewer_entry", lambda: None)
    monkeypatch.setattr(viewer, "_launch_program",
                        lambda *a, **k: pytest.fail("should not launch"))
    n0 = len(viewer.message_win.text.toPlainText().splitlines())
    viewer._open_in_flowviewer()
    text = "\n".join(
        viewer.message_win.text.toPlainText().splitlines()[n0:])
    assert "flowviewer entry not found" in text


def test_flowviewer_entry_setting_wins(viewer, monkeypatch, tmp_path):
    """Environment Settings 'flowviewer_entry' 优先于兄弟仓默认。"""
    f = tmp_path / "custom_entry.py"
    f.write_text("")
    monkeypatch.setattr(
        "cab_options.get_setting",
        lambda key, default=None:
        str(f) if key == "flowviewer_entry" else default)
    assert viewer._find_flowviewer_entry() == str(f)


def test_flowviewer_entry_default_sibling(viewer, monkeypatch):
    """无设置时回退兄弟仓 ../flowviewer/fv_gui.py (存在才非 None)。"""
    monkeypatch.setattr("cab_options.get_setting",
                        lambda key, default=None: default)
    entry = viewer._find_flowviewer_entry()
    if entry is not None:  # CI 无兄弟仓时跳过存在性断言
        assert entry.replace("\\", "/").endswith("/flowviewer/fv_gui.py")


# ------------------------------------------------- P1-3 OBJ/DXF/MDL 出口

class _TetraMesh:
    """最小 duck-typed tess (points/triangles 属性即被 _merged_tess 接受)。"""

    def __init__(self):
        self.points = np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        self.triangles = np.array(
            [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64)


def _patch_save_dialog(monkeypatch, path, filt):
    monkeypatch.setattr(
        cab_gui.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(path), filt)))


def test_export_dialog_obj_dxf_mdl(viewer, monkeypatch, tmp_path):
    """File->Export 对话框三格式出口 (E1 helper 死代码接线)。"""
    import cab_import
    monkeypatch.setattr(viewer, "_cad_meshes", [_TetraMesh()])
    for ext, filt in ((".obj", "Wavefront OBJ (*.obj)"),
                      (".dxf", "DXF (*.dxf)"),
                      (".mdl", "Cradle MDL (*.mdl)")):
        out = tmp_path / f"mesh{ext}"
        _patch_save_dialog(monkeypatch, out, filt)
        viewer._export_dialog()
        assert out.exists(), out
    # OBJ 往返
    v, t = cab_import.parse_obj_file(tmp_path / "mesh.obj")
    assert v.shape == (4, 3) and t.shape == (4, 3)
    # DXF 3DFACE 计数
    pts, tris = cab_import.parse_dxf_meshish(tmp_path / "mesh.dxf")
    assert len(tris) == 4
    # MDL 与 OBJ 字节一致 (E1 语义)
    assert (tmp_path / "mesh.mdl").read_bytes() == \
        (tmp_path / "mesh.obj").read_bytes()


def test_export_dialog_typed_extension_wins(viewer, monkeypatch, tmp_path):
    """键入 .dxf 扩展名 (即使 filter 是 OBJ) -> 走 .dxf 出口。"""
    monkeypatch.setattr(viewer, "_cad_meshes", [_TetraMesh()])
    out = tmp_path / "mesh.dxf"
    _patch_save_dialog(monkeypatch, out, "Wavefront OBJ (*.obj)")
    viewer._export_dialog()
    assert out.exists()


def test_export_dialog_no_ext_defaults_obj(viewer, monkeypatch, tmp_path):
    """filter=OBJ 且无扩展名 -> 默认 .obj。"""
    monkeypatch.setattr(viewer, "_cad_meshes", [_TetraMesh()])
    out = tmp_path / "meshless"
    _patch_save_dialog(monkeypatch, out, "Wavefront OBJ (*.obj)")
    viewer._export_dialog()
    assert (tmp_path / "meshless.obj").exists()


def test_export_stl_unchanged(viewer, monkeypatch, tmp_path):
    """重构后 STL 出口回归不回退。"""
    monkeypatch.setattr(viewer, "_cad_meshes", [_TetraMesh()])
    out = tmp_path / "mesh.stl"
    _patch_save_dialog(monkeypatch, out, "STL (*.stl)")
    viewer._export_dialog()
    data = out.read_bytes()
    assert data[:5] == b"solid" or len(data) == 84 + 50 * 4  # ascii/binary