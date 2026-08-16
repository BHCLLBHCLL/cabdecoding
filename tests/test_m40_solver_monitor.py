"""R6 / M40: 求解闭环监控 offscreen 测试.

假求解器: monkeypatch _find_program 返回当前 python.exe,
_export_temp_s_files 返回假脚本路径 -> QProcess 执行 python script,
分别验证正常退出 / 异常退出码 / 输出 tail / 运行中重复启动被拒。
QProcess 事件用 QApplication.processEvents 轮询驱动。
"""

import os
import sys
import time

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
    # 兜底清理: 停止仍在运行的求解进程, 避免孤儿 python
    proc = getattr(win, "_solver_proc", None)
    if proc is not None and proc.is_running():
        proc.stop()
    win.close()


def _messages(win) -> list:
    return win.message_win.text.toPlainText().splitlines()


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


def _auto_execute(monkeypatch):
    """让 Execute Solver 对话框自动点击 Execute (200ms 后兜底 reject,
    覆盖启动被拒不 accept 的场景, 防止 offscreen 下卡死在 exec_)。"""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QDialog, QPushButton
    orig = QDialog.exec_

    def fake_exec(self):
        for b in self.findChildren(QPushButton):
            if b.text() == "Execute":
                QTimer.singleShot(0, b.click)
                break
        QTimer.singleShot(200, self.reject)
        return orig(self)

    monkeypatch.setattr(QDialog, "exec_", fake_exec)


def _setup_fake_solver(viewer, monkeypatch, tmp_path, body: str):
    """假求解器: exe=当前 python, sfile=临时假脚本 (输出/退出码可控)。"""
    script = tmp_path / "fake_solver.py"
    script.write_text(body, encoding="utf-8")
    monkeypatch.setattr(viewer, "_find_program",
                        lambda names: sys.executable)
    monkeypatch.setattr(viewer, "_export_temp_s_files",
                        lambda: str(script))
    # 隔离用户持久化配置 (workdir / env / restart 全走默认)
    monkeypatch.setattr("cab_options.get_setting",
                        lambda key, default=None: default)
    monkeypatch.setattr("cab_options.set_setting",
                        lambda key, value: None)
    return str(script)


def test_solver_exit_zero_logs_success(viewer, monkeypatch, tmp_path, qapp):
    """正常退出 0 -> 输出行 tail 进日志 + success 提示, 无 ERROR。"""
    n0 = len(_messages(viewer))
    _auto_execute(monkeypatch)
    _setup_fake_solver(viewer, monkeypatch, tmp_path,
                       "print('cycle 1 residual 0.5', flush=True)\n"
                       "print('iteration complete', flush=True)\n")
    viewer._execute_solver()
    proc = viewer._solver_proc
    assert proc is not None and proc.is_running()
    assert _pump(qapp, lambda: not proc.is_running())
    text = "\n".join(_messages(viewer)[n0:])
    assert "[solver] cycle 1 residual 0.5" in text
    assert "Solver finished" in text and "exitCode=0" in text
    assert "ERROR" not in text


def test_solver_exit_two_logs_error(viewer, monkeypatch, tmp_path, qapp):
    """退出码 2 -> ERROR 日志 (含 exitCode=2), 不发 success。"""
    n0 = len(_messages(viewer))
    _auto_execute(monkeypatch)
    _setup_fake_solver(viewer, monkeypatch, tmp_path,
                       "print('about to fail', flush=True)\n"
                       "import sys\nsys.exit(2)\n")
    viewer._execute_solver()
    proc = viewer._solver_proc
    assert proc is not None
    assert _pump(qapp, lambda: not proc.is_running())
    text = "\n".join(_messages(viewer)[n0:])
    assert "ERROR" in text
    assert "Solver failed" in text and "exitCode=2" in text
    assert "Solver finished" not in text


def test_solver_output_tail_multi_line(viewer, monkeypatch, tmp_path, qapp):
    """多行输出逐行进入 Message pane, tail_lines 保留最近输出。"""
    n0 = len(_messages(viewer))
    _auto_execute(monkeypatch)
    _setup_fake_solver(viewer, monkeypatch, tmp_path,
                       "print('step A', flush=True)\n"
                       "print('residual 1e-4', flush=True)\n"
                       "print('CYCLE 99 done', flush=True)\n")
    viewer._execute_solver()
    proc = viewer._solver_proc
    assert proc is not None
    assert _pump(qapp, lambda: not proc.is_running())
    text = "\n".join(_messages(viewer)[n0:])
    for expected in ("step A", "residual 1e-4", "CYCLE 99 done"):
        assert f"[solver] {expected}" in text
    assert "step A" in proc.tail_lines(10)


def test_solver_reject_duplicate_start(viewer, monkeypatch, tmp_path, qapp):
    """运行中再次 Execute 被拒 (WARN), 不替换当前求解进程。"""
    _auto_execute(monkeypatch)
    _setup_fake_solver(viewer, monkeypatch, tmp_path,
                       "import time\n"
                       "print('cycle 0 residual 1.0', flush=True)\n"
                       "time.sleep(2.0)\n")
    viewer._execute_solver()
    proc1 = viewer._solver_proc
    assert proc1 is not None and proc1.is_running()

    n0 = len(_messages(viewer))
    viewer._execute_solver()  # 运行中的第二次启动
    text = "\n".join(_messages(viewer)[n0:])
    assert "already running" in text
    assert viewer._solver_proc is proc1  # 未被替换

    assert _pump(qapp, lambda: not proc1.is_running(), timeout=15.0)
    tail = "\n".join(_messages(viewer))
    assert "Solver finished" in tail
