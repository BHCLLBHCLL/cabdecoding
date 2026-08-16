"""外部工具定位器 — 找到 Cradle CFD 安装目录里的可执行程序。

WindTool 前置/求解/后处理需要调用 Cradle 自带 EXE（WindTool、scConverter、
scPOST、HeatPathView、PICLS、STpre、STsolver 等）。本模块只做**路径定位**，
不解析任何程序接口；路径不存在时返回 ``None`` 而不抛异常。
"""

from __future__ import annotations

from pathlib import Path

# 工具名 -> Programs_x64 目录下的实际文件名（Cradle 2025.2 实测）。
# STsolver 的 ProgID 是 ``STsolver_Bx64net.Application.2025``，但进程镜像名
# 为 stsol_*（单精度 Sx64net / 双精度 Dx64net），WindTool 用单精度 S。
_CRADLE_TOOL_FILES = {
    "stpre": "STpre_Bx64net.exe",
    "stsolver": "stsol_Sx64net.exe",
    "windtool": "WindTool_Bx64.exe",
    "heatpathview": "HeatPathView_Bx64.exe",
    "picls": "PICLS_Bx64net.exe",
    "scconverter": "scConverter_Sx64net.exe",
    "stpost": "scPOST_Sx64net.exe",
}


def _cradle_programs_dirs() -> list[Path]:
    """返回候选的 ``.../CradleCFD*/Programs_x64`` 目录（新版本在前）。"""
    import glob
    import os

    candidates: list[Path] = []
    env = os.environ.get("CRADLE_PROGRAMS_X64")
    if env:
        candidates.append(Path(env))

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pattern = os.path.join(pf, "Cradle", "CradleCFD*", "Programs_x64")
    try:
        for p in sorted(glob.glob(pattern), reverse=True):
            candidates.append(Path(p))
    except Exception:
        pass
    return candidates


def find_cradle_tool(name: str):
    """定位外部工具 EXE，返回 ``Path`` 或 ``None``（不存在时不抛异常）。

    ``name`` ∈ {stpre, stsolver, windtool, heatpathview, picls, scconverter,
    stpost}。优先 ``CRADLE_PROGRAMS_X64`` 环境变量，其次按版本号从新到旧
    扫描 ``%ProgramFiles%\\Cradle\\CradleCFD*\\Programs_x64``。
    """
    key = str(name).strip().lower()
    if key not in _CRADLE_TOOL_FILES:
        return None
    for base in _cradle_programs_dirs():
        path = base / _CRADLE_TOOL_FILES[key]
        if path.is_file():
            return path
    return None
