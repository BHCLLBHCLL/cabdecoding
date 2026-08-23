"""R6 求解闭环监控: 用 QProcess 封装 stsol 求解器进程。

纯 Qt 信号槽实现 (不依赖 STpre COM), 提供:
  - start(exe, args, cwd) 异步启动 + 同步确认启动成功;
  - stdout/stderr 按行 tail (缓存上限 MAX_TAIL_LINES, 避免无限增长);
  - finished -> exitCode==0 发 success, 非 0 / 崩溃发 error(exitCode, msg);
  - 输出行含迭代/残差特征词 (cycle / residual / iteration, 不区分大小写)
    时额外发 progress 信号; stsol 本机可能不存在, 解析必须容错。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

# tail 缓存上限 (行): 长时间求解时只保留最近输出
MAX_TAIL_LINES = 2000

# 迭代/残差特征词 (小写包含匹配), 命中的行额外发 progress 信号
_PROGRESS_KEYWORDS = ("cycle", "residual", "iteration")

# P1-1 收敛曲线: 从一行求解器输出提取 (cycle, residual)。
# cycle 标签缺失时用 -1 (由调用方按序号绘); 只认 residual 关键字后的首个数。
_CYCLE_RE = re.compile(r"\b(?:cycle|iteration)\D*?(\d+)", re.IGNORECASE)
_RESID_RE = re.compile(
    r"\bresidual\D*?(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)", re.IGNORECASE)


def parse_residual_line(line: str) -> Optional[Tuple[int, float]]:
    """解析一行输出中的 (cycle, residual); 无残差值时返回 None。

    容错设计: 求解器输出格式不受控 (stsol 本机可能不存在),
    任何解析失败都静默返回 None, 不影响 tail/progress 链路。
    """
    m = _RESID_RE.search(line)
    if m is None:
        return None
    value = float(m.group(1))
    c = _CYCLE_RE.search(line)
    cycle = int(c.group(1)) if c else -1
    return (cycle, value)


class SolverProcess(QObject):
    """求解器进程封装: 启动 / 输出 tail / 退出码 / 异常检测 / stop。"""

    output_line = pyqtSignal(str)   # 每行输出 (stdout+stderr 合并)
    progress = pyqtSignal(str)      # 含迭代/残差特征的输出行
    residual_point = pyqtSignal(int, float)  # P1-1: (cycle, residual)
    launched = pyqtSignal()         # 进程已成功启动
    success = pyqtSignal()          # 正常退出 (exitCode == 0)
    error = pyqtSignal(int, str)    # 异常终态: (exitCode, 说明)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._proc = QProcess(self)
        # stderr 合并进 stdout, 统一按行 tail
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_ready_read)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error_occurred)
        self._tail: list[str] = []
        self._partial = ""      # 尚未遇到换行的残余片段
        self._reported = False  # 终态 (success/error) 只报告一次
        self._residuals: list[tuple] = []  # P1-1 收敛曲线点

    # ------------------------------------------------------------------ API

    def start(self, exe: str, args: list,
              cwd: Optional[str] = None) -> bool:
        """启动求解器; 同步确认启动 (可执行不存在时立刻报 error)。"""
        if self.is_running():
            return False
        self._reported = False
        self._tail = []
        self._partial = ""
        self._residuals = []
        if cwd:
            self._proc.setWorkingDirectory(cwd)
        self._proc.start(exe, args or [])
        # 短暂同步等待: 捕获 FailedToStart (exe 不存在 / 无执行权限)
        if not self._proc.waitForStarted(5000):
            return False
        self.launched.emit()
        return True

    def stop(self) -> None:
        """停止进程: terminate -> (2s 后仍存活则) kill。"""
        if self._proc.state() == QProcess.NotRunning:
            return
        self._proc.terminate()
        if not self._proc.waitForFinished(2000):
            self._proc.kill()
            self._proc.waitForFinished(2000)

    def is_running(self) -> bool:
        return self._proc.state() in (QProcess.Starting, QProcess.Running)

    def tail_lines(self, n: int = 50) -> list[str]:
        """最近 n 行输出 (失败摘要 / 调试用)。"""
        return list(self._tail[-max(1, n):])

    def residual_points(self) -> list[tuple]:
        """P1-1: 本次运行累积的 (cycle, residual) 序列。"""
        return list(self._residuals)

    # ------------------------------------------------------------------ 槽

    def _on_ready_read(self) -> None:
        data = bytes(self._proc.readAllStandardOutput())
        if not data:
            return
        # 解码必须容错: 求解器输出编码不受控, 坏字节替换而非抛异常
        text = self._partial + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._partial = lines.pop()  # 最后一段可能不完整, 留待下轮
        for raw in lines:
            self._emit_line(raw.rstrip("\r"))

    def _on_finished(self, exit_code: int, status) -> None:
        # finished 信号发出时缓冲里可能还有未 readyRead 的数据
        self._on_ready_read()
        if self._partial:  # flush 末尾未换行的输出
            self._emit_line(self._partial.rstrip("\r"))
            self._partial = ""
        if self._reported:
            return
        self._reported = True
        if status == QProcess.CrashExit:
            self.error.emit(exit_code, f"solver crashed, exitCode={exit_code}")
        elif exit_code == 0:
            self.success.emit()
        else:
            self.error.emit(
                exit_code, f"solver exited abnormally, exitCode={exit_code}")

    def _on_error_occurred(self, error) -> None:
        if self._reported:
            return
        if error == QProcess.FailedToStart:
            # 启动失败时 finished 不会发出, 在此报告终态
            self._reported = True
            self.error.emit(
                -1, "solver failed to start (program missing / no exec bit)")
        # Crashed 交给 finished (CrashExit) 统一报告;
        # ReadError / WriteError / Timedout 为暂时性 IO 毛刺, 不作终态

    # ------------------------------------------------------------------ 内部

    def _emit_line(self, line: str) -> None:
        self._tail.append(line)
        if len(self._tail) > MAX_TAIL_LINES:
            del self._tail[:len(self._tail) - MAX_TAIL_LINES]
        if not line.strip():
            return  # 空行只进 tail, 不发信号刷日志
        self.output_line.emit(line)
        # 防御性迭代/残差识别: 仅小写包含匹配, 解析失败无副作用
        low = line.lower()
        if any(k in low for k in _PROGRESS_KEYWORDS):
            self.progress.emit(line)
            # P1-1 收敛曲线: 同一行尝试提取 (cycle, residual)
            pt = parse_residual_line(line)
            if pt is not None:
                self._residuals.append(pt)
                self.residual_point.emit(pt[0], pt[1])
