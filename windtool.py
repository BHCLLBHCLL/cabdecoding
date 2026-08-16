"""WindTool 前置接口 — 16 风向 / Weibull 表 / info 文件 / 幂律参数 / 边界判定。

纯 Python（不依赖 STpre COM，便于单测）。复刻 Cradle 2025.2 WindTool 的
前处理侧逻辑，来源：

* ``STpre_STsolver_eng.vbs`` — 16 风向入口/出口/自由滑移挂接判定、power-law
  幂律风速廓线入口（``SetFluxPower2`` 11 参数）、``SetNorthAngle``、初始速度；
* ``STtools_eng.vbs`` — info 文件格式（``ReadInfoFile`` 分节解析）；
* ``WeibullParameter_eng.csv`` — 16 风向 Weibull 频率/尺度/形状参数。

本模块不做 .fld 后处理、STsolver 求解、PICLS 互连（无文档，见任务说明）。
"""

from __future__ import annotations

from pathlib import Path

# 16 风向（气象"来向"命名，顺序与 WeibullParameter_eng.csv 的 DIRECTION 一致）
WIND_DIRECTIONS = [
    "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S",
    "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW", "N",
]

# 条件名（与 STpre_STsolver_eng.vbs 的 CondIn/CondOut/CondFree/CondInit* 一致）
COND_IN = "Tool_Flux1_"          # power-law 入口
COND_OUT = "Tool_Flux_SPres0"    # 出口压力（SetFluxPres 0.0,0.0）
COND_FREE = "Tool_Wall_FreeSlip" # 自由滑移墙
COND_INIT_U = "Tool_Init_U"      # 初始速度 UNOR
COND_INIT_V = "Tool_Init_V"      # 初始速度 VNOR

# 内置东京 Weibull 表（WeibullParameter_eng.csv, POINT=Tokyo）。
# FREQ=Di（频率 %）、CPARAM=Ci（尺度参数）、KPARAM=Ki（形状参数），
# 顺序与 WIND_DIRECTIONS 一一对应。
_TOKYO_FREQ = [
    4.270, 5.940, 6.844, 3.887, 3.942, 1.889, 0.876, 16.890,
    3.285, 10.129, 0.411, 0.164, 0.493, 4.708, 27.211, 9.061,
]
_TOKYO_CPARAM = [
    5.948, 5.975, 5.891, 5.756, 5.468, 4.983, 4.673, 6.312,
    6.915, 7.309, 5.078, 8.042, 6.345, 7.797, 7.556, 6.961,
]
_TOKYO_KPARAM = [
    4.416, 5.332, 5.296, 6.050, 5.526, 7.606, 6.216, 4.421,
    3.712, 4.008, 6.108, 2.484, 2.608, 3.275, 4.387, 2.882,
]


def wind_theta(i: int) -> float:
    """第 ``i`` 风向（1..16）的入口风向角 ``Theta``（风**吹向**，度）。

    公式 ``Theta = 180 + i*360/16``，归一到 ``[0, 360)``。例如 i=1（NNE）
    -> 202.5、i=5（SE）-> 292.5、i=8（S）-> 0、i=16（N）-> 180。
    """
    if not 1 <= int(i) <= 16:
        raise ValueError(f"风向序号必须在 1..16，得到 {i!r}")
    return (180.0 + int(i) * 360.0 / 16.0) % 360.0


def _coerce_text(src) -> str:
    """把文件路径 / 字节 / 已含换行的 CSV 文本统一成 str。"""
    if isinstance(src, Path):
        return src.read_text(encoding="utf-8-sig")
    if isinstance(src, bytes):
        return src.decode("utf-8-sig")
    s = str(src)
    if "\n" in s or "\r" in s:
        return s
    return Path(s).read_text(encoding="utf-8-sig")


def load_weibull_table(path_or_csv_text) -> dict[str, dict[str, tuple[float, float, float]]]:
    """解析 WeibullParameter CSV 为 ``{城市: {direction: (freq, c, k)}}``。

    CSV 格式（多城市重复，每城市 5 行一组）：

        POINT,城市名
        DIRECTION,16 风向(逗号分隔)
        FREQ,16 个 Di 值
        CPARAM,16 个 Ci 值
        KPARAM,16 个 Ki 值

    ``path_or_csv_text`` 可为文件路径（str/Path）或已读入的 CSV 文本。
    """
    import csv
    from io import StringIO

    table: dict[str, dict[str, tuple[float, float, float]]] = {}
    city = None
    directions = None
    freq = c = k = None

    for row in csv.reader(StringIO(_coerce_text(path_or_csv_text))):
        if not row or not row[0].strip():
            continue
        tag = row[0].strip().upper()
        if tag == "POINT":
            city = row[1].strip() if len(row) > 1 else ""
            directions = None
            freq = c = k = None
        elif tag == "DIRECTION":
            directions = [v.strip() for v in row[1:] if v.strip()]
        elif tag == "FREQ":
            freq = [float(v) for v in row[1:] if v.strip()]
        elif tag == "CPARAM":
            c = [float(v) for v in row[1:] if v.strip()]
        elif tag == "KPARAM":
            k = [float(v) for v in row[1:] if v.strip()]
            if city is not None and directions and freq and c and k:
                table[city] = {
                    d: (f, ci, ki)
                    for d, f, ci, ki in zip(directions, freq, c, k)
                }
    return table


def default_weibull() -> dict[str, tuple[float, float, float]]:
    """内置东京 Weibull 表：``{direction: (freq, c, k)}``，16 向有序。"""
    return {
        d: (f, c, k)
        for d, f, c, k in zip(
            WIND_DIRECTIONS, _TOKYO_FREQ, _TOKYO_CPARAM, _TOKYO_KPARAM)
    }


def _fmt(v) -> str:
    """把参数值格式化为 info 文件里的文本行（浮点用最短表示）。"""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def build_windtool_info(fld_paths, gust_factor="AUTO", boundary_velocity=None,
                        reference_velocity=None, weibull=None) -> str:
    """生成 WindTool info 文件文本（UTF-8，四节 + 末尾 ``/``）。

    * ``fld_paths``          — 16 个 .fld 结果路径（按风向 1..16 顺序）；
    * ``gust_factor``        — ``"AUTO"`` 或数值；
    * ``boundary_velocity``  — 仅 ``gust_factor="AUTO"`` 时写入（边界层风速）；
    * ``reference_velocity`` — 参考风速（RefVelocity）；
    * ``weibull``            — 16 个 ``(freq/Di, c/Ci, k/Ki)`` 三元组；
      缺省用 :func:`default_weibull`。

    格式与 ``STtools_eng.vbs`` 的 ``ReadInfoFile`` 一致（``/`` 为节结束）。
    """
    if len(fld_paths) != 16:
        raise ValueError(f"fld_paths 必须 16 个，得到 {len(fld_paths)}")
    if weibull is None:
        weibull = list(default_weibull().values())
    if len(weibull) != 16:
        raise ValueError(f"weibull 必须 16 个三元组，得到 {len(weibull)}")

    lines = ["INPUT_FLD_FILES"]
    for idx, p in enumerate(fld_paths, 1):
        lines.append(f"{idx},{p}")
    lines.append("/")

    lines.append("GUST_FACTOR")
    if str(gust_factor).strip().upper() == "AUTO":
        lines.append("AUTO")
        if boundary_velocity is None:
            raise ValueError("gust_factor='AUTO' 时必须提供 boundary_velocity")
        lines.append(_fmt(boundary_velocity))
    else:
        lines.append(_fmt(gust_factor))

    lines.append("REFERENCE_VELOCITY")
    lines.append(_fmt(reference_velocity))

    lines.append("WEIBULL_PARAMETER")
    lines.append(",".join(_fmt(t[0]) for t in weibull))
    lines.append(",".join(_fmt(t[1]) for t in weibull))
    lines.append(",".join(_fmt(t[2]) for t in weibull))
    lines.append("/")

    return "\n".join(lines)


def power_law_params(*, exponent=3.7037, ref_vel=5.0, grd_hei=0.0,
                     ref_hei=74.5, turb_type="zg", ke_param1=550,
                     ke_param2=0, north_angle=0.0) -> dict:
    """返回默认 power-law 风速廓线参数 dict 并做基本校验。

    默认值与 ``STpre_STsolver_eng.vbs`` 的 Tool 变量一致：
    Exponent=3.7037 / RefVel=5.0 / GrdHei=0.0 / RefHei=74.5 /
    TurbType="zg" / KEParam1=550 / KEParam2=0。
    """
    if exponent <= 0:
        raise ValueError(f"exponent 必须 > 0，得到 {exponent!r}")
    if ref_vel <= 0:
        raise ValueError(f"ref_vel 必须 > 0，得到 {ref_vel!r}")
    if ref_hei <= 0:
        raise ValueError(f"ref_hei 必须 > 0，得到 {ref_hei!r}")
    if grd_hei < 0:
        raise ValueError(f"grd_hei 不能为负，得到 {grd_hei!r}")
    if ke_param1 < 0:
        raise ValueError(f"ke_param1 不能为负，得到 {ke_param1!r}")
    if ke_param2 < 0:
        raise ValueError(f"ke_param2 不能为负，得到 {ke_param2!r}")
    if not isinstance(turb_type, str) or not turb_type:
        raise ValueError(f"turb_type 必须是非空字符串，得到 {turb_type!r}")
    return {
        "north_angle": float(north_angle),
        "exponent": float(exponent),
        "ref_vel": float(ref_vel),
        "grd_hei": float(grd_hei),
        "ref_hei": float(ref_hei),
        "roughness": 0.0,
        "turb_type": turb_type,
        "ke_param1": ke_param1,
        "ke_param2": ke_param2,
    }


def _set_angle(flow_angle, north_angle) -> float:
    """复刻 VBS ``SetAngle``：``FlowAngle = NorthAngle + Theta`` 归一到 ``[0, 360]``。

    与 VBS 一致保留 360（``> 360`` 才减 360，``= 360`` 不动），边界判定里
    ``FlowAngle = 360 OR 0`` 两者等价处理。
    """
    fa = float(north_angle) + float(flow_angle)
    for _ in range(10):
        if fa < 0:
            fa += 360.0
        elif fa > 360:
            fa -= 360.0
        else:
            break
    return fa


def wind_direction_boundary(flow_angle, north_angle=0.0) -> dict:
    """复刻 VBS 16 风向的入口/出口/自由滑移挂接判定。

    ``flow_angle`` 为入口风向角 Theta（风**吹向**），``north_angle`` 为北向角；
    内部 ``FlowAngle = NorthAngle + Theta``（SetAngle 归一）后按 8 个区间
    决定四个边界面 ``Xmin/Xmax/Ymin/Ymax`` 挂入口/出口/自由滑移，以及初始
    速度 ``UNOR/VNOR`` 是否挂接。

    返回 ``{xmin, xmax, ymin, ymax, init_u, init_v}`` 的**条件名**映射，
    未挂接的 init_u/init_v 为 ``None``。
    """
    fa = _set_angle(flow_angle, north_angle)

    if 180 < fa < 270:
        xmin, xmax = COND_OUT, COND_IN
        ymin, ymax = COND_OUT, COND_IN
        init_u, init_v = COND_INIT_U, COND_INIT_V
    elif fa == 270:
        xmin, xmax = COND_OUT, COND_IN
        ymin, ymax = COND_FREE, COND_FREE
        init_u, init_v = COND_INIT_U, None
    elif 270 < fa < 360:
        xmin, xmax = COND_OUT, COND_IN
        ymin, ymax = COND_IN, COND_OUT
        init_u, init_v = COND_INIT_U, COND_INIT_V
    elif fa == 360 or fa == 0:
        xmin, xmax = COND_FREE, COND_FREE
        ymin, ymax = COND_IN, COND_OUT
        init_u, init_v = None, COND_INIT_V
    elif 0 < fa < 90:
        xmin, xmax = COND_IN, COND_OUT
        ymin, ymax = COND_IN, COND_OUT
        init_u, init_v = COND_INIT_U, COND_INIT_V
    elif fa == 90:
        xmin, xmax = COND_IN, COND_OUT
        ymin, ymax = COND_FREE, COND_FREE
        init_u, init_v = COND_INIT_U, None
    elif 90 < fa < 180:
        xmin, xmax = COND_IN, COND_OUT
        ymin, ymax = COND_OUT, COND_IN
        init_u, init_v = COND_INIT_U, COND_INIT_V
    elif fa == 180:
        xmin, xmax = COND_FREE, COND_FREE
        ymin, ymax = COND_OUT, COND_IN
        init_u, init_v = None, COND_INIT_V
    else:  # 理论上到不了（SetAngle 已归一）
        raise ValueError(f"FlowAngle 归一失败：{fa!r}")

    return {
        "xmin": xmin, "xmax": xmax,
        "ymin": ymin, "ymax": ymax,
        "init_u": init_u, "init_v": init_v,
    }
