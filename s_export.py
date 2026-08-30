"""P3: SDAT (.s) solver-input exporter for scSTREAM Pre cab projects.

Generates the same section layout as the official exporter (sample
``tests/ex4_e.s``). Values are derived from the cab XML members:

- CXYZ            <- ``mesh_block`` axis coordinates (mm -> m)
- PARTS           <- ``element`` part box tables + material mapping
- REGION / A_MDR  <- ``analysis_region`` face lists + ``element`` faces
- INIT/FLUX/AMOM/AENT/VENT/VFWL <- ``value`` + ``condition`` bindings
- analysis/control sections <- ``analysis_set`` / ``output`` / ``steady_param``

R8-B 多样本交叉验证（CradleCFD_2023.2 示例库 295 对 (.cab,.s) 样本，
tools/diag_s_constants.py）后，原先写死自 tests/ex4_e.s 的 opaque 常量
已改为从 XML 状态派生，或注明保留原因：

- SDAT 第二行 9 列  <- 扩散物种数(根级 <diffusion> 个数) / 辐射面组数
  (无辐射 0, type=flux 2, 其余 4) / 湍流模型号；col4=2 当
  analysis_etc/fusion 存在（exA11-1）；col6=1 当
  analysis_etc/free_surf 存在；col8=analysis_set/moving_body
  计数（exA09-1=1, exA09-2=2）；其余 hdr2 尾列仍无 XML 源，恒 0。
- VFEX 段           <- radiation 存在且 type != "flux"（flux 法无角系数）
- HEATPATH 段       <- analysis_set/heat_path = 1
- EQUA 8 位掩码     <- 位1-3 各轴向网格数>1（2D/1D 关对应动量方程，
  样本实证 exB11: 1000x1x1 -> 1001xxxx），位4 恒 1（连续性），
  位5 热方程（0/1，mars 自由面且 mars_fluid_energy=1 时为 2），
  位6-7 湍流（k/eps 两方程），位8 扩散物种>0。
- HSOL              <- thermal_solver 的 [0] 与 [1],[3],[4]；仅热分析、
  type=incompressive、无自由面、无运动件时发射（样本中 compressive /
  mars / 运动件项目均无 HSOL 段）。
- CYCS/CYCT/UNDR/STED <- calculation 稳/瞬态 + cycle / time_step（或
  init_time_step+courant 自适应）；UNDR/STED 逐条来自 steady_param 的
  under_relax / conv_check（类型索引 U1 V2 W3 P4 T5 K6 E7）。
- 仍为常量的行：SDAT 版本行、VFDE 的 LEAP/EM1、EQUA 后的
  TBEC/UPWD 附加卡（无 XML 源，不发射）。hdr1 尾列已全部从
  XML 派生（P5-1，295 样本零失配）：第 6 列 =
  ``analysis_etc/particle/max_num``（exA07-1=10000 /
  exA07-6=1000000），第 7/8 列 = 1 当且仅当
  ``particle/kind == "reaction"``（exB12；marker/mass 恒 0）。
  MREF/MRCL 已从 radiation XML 派生
  （max_reflection / smrt_rays）。已证无法派生的例外样本清单见
  tools/diag_s_constants.py 输出。
"""

from __future__ import annotations

import re
from typing import Optional

from cabxml import PropertyModel, StpreModel


def _child_text(el, tag: str, default: str = "") -> str:
    from cabxml import _first
    if el is None:
        return default
    c = _first(el, tag)
    return c.text.strip() if c is not None and c.text else default


def _rad_int(el, tag: str, default: int) -> int:
    """Integer radiation XML field; first comma-separated token, else default."""
    raw = _child_text(el, tag, str(default)) or str(default)
    try:
        return int(float(raw.split(",")[0]))
    except ValueError:
        return int(default)


def _part_is_cutcell(p) -> bool:
    """Part carries ``<cutcell> T`` (Option -> Cut Cell Setting, R9-B)."""
    cc = p.elem.find("cutcell") if getattr(p, "elem", None) is not None else None
    return cc is not None and (cc.text or "").strip().upper() in ("T", "1")


#: part kind → CCEL ``TYPE`` string (official Cube/Cylinder/Sphere kinds)
_CCEL_TYPE_BY_KIND = {"cube": "Cube", "cylinder": "Cylinder",
                      "sphere": "Sphere"}


def ccel_filename(model: StpreModel) -> str:
    """Header ``CCEL`` reference: ``<project>.ccel`` (sample convention).

    All official cut-cell samples name the container after the project
    (exA23-2b_cut_cell_e / exA23-3_e / exA23-4_e); it lives next to the
    ``.s`` file, outside the .cab archive.
    """
    stem = model.project_name
    if not stem:
        aset = model.root.find("analysis_set")
        ro = _child_text(aset.find("file") if aset is not None else None,
                         "ro", "ex4_e")
        stem = ro[:-2] if ro.lower().endswith(".r") else ro
    return stem + ".ccel"


def _ccel_faces_for(p, tess) -> list:
    """CCEL faces of one part: tess mesh → cube corners → empty.

    Tess points are metres + local frame; the part ``<transform>`` is
    applied before serialisation. Untransformed cubes keep the official
    six-quad ``TYPE 'Cube'`` layout.
    """
    import ccel as _ccel

    pts = tris = None
    if tess is not None:
        import numpy as np
        _pts = np.asarray(getattr(tess, "points", ()), dtype=float)
        _tris = np.asarray(getattr(tess, "triangles", ()))
        if _pts.size and _tris.size:
            pts, tris = _pts, _tris
    elif p.base and p.size:
        try:
            b = [float(v) for v in p.base.split(",")[:3]]
            s = [float(v) for v in p.size.split(",")[:3]]
        except ValueError:
            b = s = []
        if len(b) == 3 and len(s) == 3:
            if not (p.transform or "").strip():
                mn = [v / 1000.0 for v in b]
                mx = [(b[i] + s[i]) / 1000.0 for i in range(3)]
                return _ccel.faces_from_box(mn, mx)
            from cab_parts import cube_tess
            t = cube_tess(b, s)
            pts, tris = t.points, t.triangles
    if pts is None:
        return []
    import cab_vtk
    pts = cab_vtk._apply_transform(pts, p.transform or "")
    return _ccel.faces_from_triangles(pts, tris)


def _ccel_attr(p) -> str:
    """CCEL ATTR from part attribute/kind: PANEL, CBODY, FLUID, or BODY.

    Official 22 ``.ccel`` files: BODY (solid cut-cell), PANEL (panel
    attribute), and one CBODY (exA23-1a extruded sketch with
    ``attribute=area`` + ``<cutcell>T``). FLUID is kept for
    ``attribute=fluid`` even though this example set has no FLUID row.
    """
    a = (getattr(p, "attribute", "") or "").strip().lower()
    k = (getattr(p, "kind", "") or "").strip().lower()
    if a in ("panel", "sheet", "open") or k in ("panel", "quad_panel"):
        return "PANEL"
    if _part_is_cutcell(p) and a == "area":
        return "CBODY"
    if a == "fluid" or a.startswith("fluid"):
        return "FLUID"
    return "BODY"


def build_ccel(model: StpreModel, meshes=None) -> Optional[bytes]:
    """R20: serialise cut-cell registered parts to a ``.ccel`` stream.

    Geometry priority per part: GUI tessellation (``meshes`` items with
    ``.name/.points/.triangles`` in metres) → cube ``base/size`` corners.
    Returns None when no part is registered for cut-cell (callers then
    skip the file; the .s header also omits the CCEL line).
    """
    import ccel as _ccel

    infos = [p for p in model.parts() if _part_is_cutcell(p)]
    if not infos:
        return None
    mesh_by_name = {m.name: m for m in (meshes or [])}
    out = []
    for p in infos:
        faces = _ccel_faces_for(p, mesh_by_name.get(p.name))
        out.append(_ccel.CcelPart(
            name=p.name,
            type_str=_CCEL_TYPE_BY_KIND.get((p.kind or "").lower(),
                                            "Any_Body"),
            attr=_ccel_attr(p),
            faces=faces))
    return _ccel.write_ccel(out)


def _f(v: float, w: int = 26) -> str:
    return f"{v:{w}.14e}"


def _i(v: int, w: int = 12) -> str:
    return f"{v:{w}d}"


# Pinned .s header / VFDE constants (R8-B, 295 official samples).
# hdr1 tail default is 1,1,0,0,0; overlays from <particle>:
# col3 = max_num, col4 = col5 = 1 iff kind == "reaction" (P5-1,
# see hdr1_tail). hdr2 col4-9 default 0; overlays: fusion /
# free_surf / moving_body (see hdr2_tail). VFDE LEAP=1, EM1=0.99.
# MREF/MRCL are XML-derived.
HDR1_TAIL = (1, 1, 0, 0, 0)
HDR2_TAIL = (0, 0, 0, 0, 0, 0)
VFDE_LEAP = 1
VFDE_EM1 = 0.99


def hdr1_tail(model: StpreModel) -> tuple:
    """hdr1 last 5 ints: default HDR1_TAIL, cols 3-5 from <particle>.

    Official 2023.2 ST Example (295 pairs, P5-1 black-box sweep over
    all local libraries incl. scFLOW 2023/2025 + tests/box, zero
    mismatches, tools/diag_hdr1_tail.py):

    * col3 = ``analysis_etc/particle/max_num`` when <particle> exists
      (exA07-1=10000 / exA07-6=1000000)
    * col4 = col5 = 1 iff ``particle/kind == "reaction"`` (exB12);
      marker/mass kinds and non-particle projects stay 0
    """
    a, b, _c, d, e = HDR1_TAIL
    particle = model.root.find("analysis_etc/particle")
    max_num = 0
    if particle is not None:
        raw = _child_text(particle, "max_num", "0") or "0"
        try:
            max_num = int(float(raw.split(",")[0]))
        except ValueError:
            max_num = 0
        if (_child_text(particle, "kind") or "").strip() == "reaction":
            d = e = 1
    return (a, b, max_num, d, e)


def hdr2_tail(model: StpreModel) -> tuple:
    """hdr2 last 6 ints, overlaid from analysis_etc / moving_body.

    Official 2023.2 ST Example (do not invent remaining columns):

    * col4 = 2 iff ``<analysis_etc>/<fusion>`` exists (exA11-1)
    * col6 = 1 iff ``<analysis_etc>/<free_surf>`` exists (exA10-*)
    * col8 = ``<analysis_set>/<moving_body>`` integer (exA09-1=1,
      exA09-2=2)
    * col9 ``2``/``42`` still has no unique XML source — stays 0
    """
    col4, col5, col6, col7, col8, col9 = HDR2_TAIL
    if model.root.find("analysis_etc/fusion") is not None:
        col4 = 2
    if model.root.find("analysis_etc/free_surf") is not None:
        col6 = 1
    aset = model.root.find("analysis_set")
    raw = _child_text(aset, "moving_body", "0") or "0"
    try:
        col8 = int(float(raw.split(",")[0]))
    except ValueError:
        col8 = 0
    return (col4, col5, col6, col7, col8, col9)


def _name_key(name: str):
    """Sort key that orders Wall1..Wall4 / HeatSource1..8 numerically."""
    m = re.search(r"(\d+)$", name)
    return (name[:m.start()], int(m.group(1))) if m else (name, 0)


class SExport:
    """Builds the SDAT text from a project model."""

    def __init__(self, model: StpreModel, props: PropertyModel,
                 meshes=None, ccel_name: str = ""):
        self.m = model
        self.p = props
        self.lines: list[str] = []
        self.meshes = list(meshes or [])
        self.ccel_name = ccel_name
        self.materials = self._material_order()
        self.parts = self._part_list()

    # -- material / part bookkeeping --------------------------------------

    def _material_order(self) -> dict[str, int]:
        from xemt_export import _ordered_materials, _used_material_names
        return _ordered_materials(self.m, self.p)

    def _part_list(self) -> list[dict]:
        """Ordered part descriptors: id, name, material, fraction, boxes."""
        out: list[dict] = []
        ar = self.m.analysis_region()
        from cabxml import _first
        fluid_name = ""
        if ar is not None:
            prop = _first(ar, "property")
            fluid_name = prop.text.strip() if prop is not None else ""
        mat = self.materials.get(fluid_name, 1)
        out.append({
            "id": 1, "name": _child_text(ar, "name", "Domain"),
            "material": mat, "fraction": 1.0,
            "boxes": self.m.part_boxes(_child_text(ar, "name", "Domain")),
        })
        pid = 1
        for p in self.m.parts():
            pid += 1
            cut = _part_is_cutcell(p)
            out.append({
                # R20: cut-cell parts carry a negative id and an empty box
                # list — their geometry lives in the .ccel container
                # (exA23-2b / exA23-4 PARTS evidence)
                "id": -pid if cut else pid, "name": p.name,
                "material": self.materials.get(p.property, 1),
                "fraction": 0.0 if p.attribute == "solid" else 1.0,
                "boxes": [] if cut else self.m.part_boxes(p.name),
            })
        return out

    # -- main render ------------------------------------------------------

    def render(self) -> str:
        self._header()
        self._vfex_unit()
        self._heatpath()
        self._equations()
        self._property()
        self._cxyz()
        self._parts()
        self._regions()
        self._movb_parts()
        self._init_region()
        self._flux_region()
        self._amom_region()
        self._aent_region()
        self._vent_region()
        self._vfwl_region()
        self._movb_control()
        self._vfem_vfde()
        self._peltier()
        self._autofixp()
        self._lsol_sections()
        self._pcle_handling()
        self._humw_region()
        self._es_field_bc()
        self._fout()
        self._sufs_region()
        self._surf_porous()
        self._topopt_region()
        self._meix_var()
        self._balances()
        self._flux_sum()
        self._cutcell()
        self._tprt()
        self.lines.append("GOGO")
        return "\r\n".join(self.lines) + "\r\n"

    # -- sections ---------------------------------------------------------

    def _header(self):
        aset = self.m.root.find("analysis_set")
        files = aset.find("file") if aset is not None else None
        def fname(tag: str) -> str:
            return _child_text(files, tag, "ex4_e")
        self.lines += [
            "SDAT",
            "STREAM  ",
            "        2023           0           0    UTF-8",
            "           3",
            "! STpre  Version.2023.2  1623.20302.20231027",
            "POST",
            self.m.project_name,
            "RO",
            fname("ro"),
            "VF",
            fname("vf"),
            "OT",
            fname("ot"),
            "HPT",
            fname("hpt"),
        ]
        # R20: cut-cell parts reference their geometry container after
        # the RO/VF/OT/HPT family (exA23-3_e / exA23-4_e header evidence;
        # exA23-2b carries CCEL right after RO because it has no
        # VF/OT/HPT lines at all)
        if any(_part_is_cutcell(p) for p in self.m.parts()):
            self.lines += [
                "CCEL",
                self.ccel_name or ccel_filename(self.m),
            ]
        self.lines += [
            "/",
            _child_text(self.m.project, "comment", ""),
            "           1",
        ]
        axes = self.m.mesh_axes()
        ni = len(axes.get("x", [])) - 1
        nj = len(axes.get("y", [])) - 1
        nk = len(axes.get("z", [])) - 1
        # hdr1 后 5 列默认 HDR1_TAIL；第 6 列（粒子 max_num）见 hdr1_tail
        self.lines.append(
            f"{_i(ni)}{_i(nj)}{_i(nk)}"
            + "".join(_i(v) for v in hdr1_tail(self.m)))
        # hdr2：col1=扩散物种数；col2=辐射面组数（无 0 / flux 2 / 其余 4，
        # 例外 exA09-3c=12 无 XML 源）；col3=湍流模型号；
        # col4..9 = hdr2_tail（fusion / free_surf / moving_body）
        rad = aset.find("radiation") if aset is not None else None
        if rad is None:
            rad_groups = 0
        elif rad.attrib.get("type", "") == "flux":
            rad_groups = 2
        else:
            rad_groups = 4
        turb_model = int(_child_text(aset, "turbulence_model", "0") or 0)
        diff_n = len(self.m.root.findall("diffusion"))
        self.lines.append(
            "".join(_i(v) for v in (diff_n, rad_groups, turb_model)
                    + hdr2_tail(self.m)))

    def _vfex_unit(self):
        aset = self.m.root.find("analysis_set")
        rad = aset.find("radiation") if aset is not None else None
        # VFEX 仅角系数法辐射发射；flux 法及无辐射项目均无该段
        # （exA01-1 flux / exB16a 无辐射实证；例外 exA08-* 见诊断记录）
        if rad is not None and rad.attrib.get("type", "") != "flux":
            method = _child_text(rad, "method", "1")
            self.lines += ["VFEX", f"{_i(int(method))}{_i(1)}"]
        self.lines += [
            "UNIT",
            f"   temperature{_i(1, 15)}{_i(1)}",
            "/",
        ]

    def _heatpath(self):
        aset = self.m.root.find("analysis_set")
        # HEATPATH 段仅 heat_path=1 时发射（exA01-1 heat_path=0 无此段）
        if _child_text(aset, "heat_path", "0") != "1":
            return
        proj = self.m.project
        ambient = _child_text(proj, "ambient_temperature", "20")
        self.lines += [
            "HEATPATH",
            "atmosphere",
            _f(float(ambient), 29),
            "timing",
            f"{_i(0, 5)}:L",
            "/",
        ]

    # -- R8-B 派生辅助 ---------------------------------------------------

    def _equa_mask(self) -> str:
        """EQUA 8 位掩码（295 样本交叉验证，见模块头注释）。"""
        aset = self.m.root.find("analysis_set")
        heat = _child_text(aset, "heat", "0") == "1"
        turb = _child_text(aset, "turbulence", "0") not in ("", "0")
        fs = self.m.root.find("analysis_etc/free_surf")
        mfe = _child_text(fs, "mars_fluid_energy", "") if fs is not None else ""
        diff_n = len(self.m.root.findall("diffusion"))
        axes = self.m.mesh_axes()
        # 位1-3：各轴向区间数>1 才解该方向动量方程（2D/1D 实证）
        bits = "".join("1" if len(axes.get(a, [])) - 1 > 1 else "0"
                       for a in ("x", "y", "z"))
        bits += "1"                                   # 位4 连续性恒开
        if not heat:
            bits += "0"
        elif fs is not None and mfe == "1":
            bits += "2"                               # mars 两流体能量方程
        else:
            bits += "1"
        bits += "1" if turb else "0"                  # 位6 k
        bits += "1" if turb else "0"                  # 位7 eps
        bits += "1" if diff_n > 0 else "0"            # 位8 扩散
        return bits

    def _has_moving_parts(self) -> bool:
        return bool(self._moving_parts())

    def _equations(self):
        aset = self.m.root.find("analysis_set")
        self.lines += ["EQUA", self._equa_mask()]
        grav_abs = float(_child_text(aset, "grav_abs", "9.8"))
        grav_vec = [float(x) for x in _child_text(aset, "grav_vec",
                                                   "0,0,-1").split(",")[:3]]
        ambient = float(_child_text(self.m.project, "ambient_temperature", "20"))
        self.lines += [
            "GRAV",
            f"{_f(grav_vec[0] * grav_abs, 29)}"
            f"{_f(grav_vec[1] * grav_abs)}{_f(grav_vec[2] * grav_abs)}"
            f"{_f(ambient)}{_i(0)}",
        ]
        # HSOL：固体热传导求解卡。样本中 compressive / mars 自由面 /
        # 运动件项目的官方 .s 均无此段；值取 thermal_solver 的
        # [0] 与 [1],[3],[4]（ex4_e "1,3,2,1,1,0" -> 1 / 3 1 1）
        fs = self.m.root.find("analysis_etc/free_surf")
        if (_child_text(aset, "heat", "0") == "1"
                and _child_text(aset, "type", "incompressive")
                != "compressive"
                and fs is None and not self._has_moving_parts()):
            ts = [x.strip() for x in _child_text(aset, "thermal_solver",
                                                 "1,3,2,1,1,0").split(",")]
            self.lines += [
                "HSOL",
                _i(int(ts[0])),
                _i(int(ts[1])) + _i(int(ts[3])) + _i(int(ts[4])),
            ]
        # CYC：稳态 CYCS(起止迭代)，瞬态 CYCT(起止步 + 步进模式) + 参数行
        cycle = [x.strip() for x in
                 _child_text(aset, "cycle", "1,100").split(",")]
        c0 = int(cycle[0]) if cycle and cycle[0] else 1
        c1 = int(cycle[1]) if len(cycle) > 1 and cycle[1] else 100
        if _child_text(aset, "calculation", "steady") == "transient":
            ts_el = aset.find("time_step") if aset is not None else None
            # 第三值：固定 time_step 时 -1，courant 自适应时 1（样本实证）
            self.lines += [
                "CYCT",
                f"{_i(c0)}{_i(c1, 10)}{_i(-1 if ts_el is not None else 1, 10)}",
            ]
            if ts_el is not None:
                tsp = [x.strip() for x in
                       (ts_el.text or "99999,0").split(",")]
                v0 = float(tsp[0])
                v1 = float(tsp[1]) if len(tsp) > 1 and tsp[1] else 0.0
                first = _i(int(v0)) if v0 == int(v0) else _f(v0)
                self.lines.append(first + _f(v1))
            else:
                dt = float(_child_text(aset, "init_time_step", "0"))
                cou = float(_child_text(aset, "courant", "0"))
                self.lines.append(_f(dt) + _f(cou))
        else:
            self.lines += ["CYCS", f"{_i(c0)}{_i(c1, 10)}"]
        # UNDR / STED：稳态控制卡，逐条来自 steady_param
        # （类型索引 U1 V2 W3 P4 T5 K6 E7；ex4_e under_relax T 0.99
        #   -> "5 0.99"；exB16a conv_check U/V/W/T -> STED 1/2/3/5 行）
        sp = self.m.root.find("steady_param")
        if sp is not None:
            type_idx = {"U": 1, "V": 2, "W": 3, "P": 4,
                        "T": 5, "K": 6, "E": 7}
            for e in sp.findall("under_relax"):
                no = type_idx.get(e.attrib.get("type", "T"), 5)
                val = (e.text or "0").split(",")[0].strip() or "0"
                self.lines += ["UNDR", f"{_i(no)}{_f(float(val))}"]
            for e in sp.findall("conv_check"):
                parts = [x.strip() for x in (e.text or "0,0").split(",")]
                if not parts or parts[0] in ("", "0"):
                    continue
                no = type_idx.get(e.attrib.get("type", "T"), 5)
                eps = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
                self.lines += [
                    "STED",
                    f"{_i(no)}{_i(int(parts[0]))}{_f(eps)}",
                ]
        self.lines.append("/")

    def _property(self):
        self.lines += ["PROPERTY", f"{_i(1)}"]
        # fluid entry: viscosity / capacity / conductivity then density / expansion
        from cabxml import _first
        def prop(name: str, key: str) -> str:
            ent = self.p.find_entry(name)
            if ent is None:
                return "0"
            c = _first(ent, key)
            return c.text.strip() if c is not None and c.text else "0"
        fname = self.m.analysis_region()
        from cabxml import _first as _f1
        fluid_prop = _child_text(fname, "property", "air(incompressible/20C)")
        visc = float(prop(fluid_prop, "viscosity"))
        cap = float(prop(fluid_prop, "capacity"))
        cond = float(prop(fluid_prop, "conductivity"))
        dens = float(prop(fluid_prop, "density"))
        exp = float(prop(fluid_prop, "expansion"))
        self.lines.append(
            f"{'boussinesq':>18}{_f(visc, 37)}{_f(cap)}{_f(cond)}"
            f"   {fluid_prop} ! (1)")
        self.lines.append(f"{_f(dens, 29)}{_f(exp)}")
        # collect unique solid materials in EMT numbering order
        solid_mats = [name for name in self.materials
                      if name != fluid_prop]
        self.lines.append(f"{_i(len(solid_mats))}")
        for no, name in enumerate(solid_mats, start=2):
            d = float(prop(name, "density"))
            c = float(prop(name, "capacity"))
            k = float(prop(name, "conductivity"))
            self.lines.append(
                f"{_f(d, 29)}{_f(c)}{_f(k)}   {name} ! ({no})")

    def _cxyz(self):
        self.lines.append("CXYZ")
        axes = self.m.mesh_axes()
        for axis in ("x", "y", "z"):
            vals = [v / 1000.0 for v in axes.get(axis, [])]
            self.lines.append("   0")
            for i in range(0, len(vals), 5):
                row = vals[i:i + 5]
                self.lines.append(
                    " " * 8 + "     ".join(f"{v:21.14e}" for v in row))

    def _parts(self):
        self.lines.append("PARTS")
        for idx, p in enumerate(self.parts):
            self.lines.append(
                f"{_i(p['id'])}{_i(p['material'])}{p['fraction']:8.1f}"
                f"    {p['name']}")
            if idx == 0:
                continue            # fluid part: no boxes / no slash
            for box in p["boxes"]:
                self.lines.append(
                    f"{int(box[0]):14d}"
                    + "".join(f"{int(v):10d}" for v in box[1:6]))
            self.lines.append("   /")
        self.lines.append("/")

    def _regions(self):
        self.lines.append("REGION")
        for p in self.parts:
            self.lines += [
                f"   {p['name']}   ! {p['name']}",
                "   V_PRT",
                # cut-cell parts register under the absolute id
                # (exA23-2b: PARTS id -2 -> REGION V_PRT 2)
                f"{_i(abs(p['id']), 15)}",
                "   /",
            ]
        ar = self.m.analysis_region()
        from cabxml import _children, _first
        if ar is not None:
            face_index = {}
            for region in _children(ar, "region"):
                face = _first(region, "face")
                if face is None or face.text is None:
                    continue
                idx = face.text.split(",")[-1].strip()
                try:
                    face_index[_child_text(region, "name")] = int(idx)
                except ValueError:
                    continue
            elem = self.m.elements()
            face_lists: dict[int, list[int]] = {}
            if elem is not None:
                analysis = _first(elem, "analysis")
                if analysis is not None:
                    for f in _children(analysis, "face"):
                        lst = _first(f, "list")
                        if lst is None or not lst.text:
                            continue
                        try:
                            no = int(f.attrib.get("no", "0"))
                            face_lists[no] = [int(x) for x in lst.text.split(",")]
                        except ValueError:
                            continue
            for region in _children(ar, "region"):
                name = _child_text(region, "name")
                no = face_index.get(name)
                box = face_lists.get(no or 0)
                if box is None:
                    continue
                v = box[0]
                code = - (1 if v > 0 else -1) * ((abs(v) + 1) // 2)
                self.lines += [
                    f"   {name}   ! {name}",
                    "   A_MDR",
                    f"{code:11d}"
                    + "".join(f"{int(x):10d}" for x in box[1:7]),
                    "   /",
                ]
        self.lines.append("/")

    # -- moving object (c7) -------------------------------------------------
    #
    # STpre 2025.2 does not write MOVB blocks itself (probe probe_movebody_s);
    # the layout below mirrors the official 2023.2 exercise exports
    # (exA09-1/-2/-4, exA15-2): MOVB_PARTS after the REGION family,
    # MOVB_CONTROL after the value/condition regions, before MEIX_VAR.

    def _moving_parts(self) -> list[tuple]:
        """``[(part_info, motion_dict)]`` for parts with a body_move or a
        6DOF rigid-body condition (C7)."""
        out = []
        for p in self.parts[1:]:
            motion = self.m.part_motion(p["name"])
            if motion is not None:
                out.append((p, motion))
                continue
            dyn = self._six_dof_for_part(p["name"])
            if dyn is not None:
                out.append((p, {"kind": "dynamical", **dyn}))
        return out

    def _six_dof_entries(self) -> list[dict]:
        """``<value type="body_move_6dof">`` conditions (exA09-4):
        name / label / move_kind / rotate_kind / force_x|y|z, bound via
        ``<parts>`` conditions."""
        from cabxml import _first

        def txt(val, tag, default=""):
            el = _first(val, tag)
            return el.text.strip() if el is not None and el.text                 else default

        out = []
        for val in self.m.values_of_type("body_move_6dof"):
            name = txt(val, "name")
            if not name:
                continue
            parts_names = []
            for c in self.m.conditions():
                v = _first(c, "value")
                if v is None or not v.text or v.text.strip() != name:
                    continue
                for ch in c:
                    if ch.tag == "parts" and (ch.text or "").strip():
                        parts_names.append((ch.text or "").strip())
            if not parts_names:
                continue
            out.append({
                "name": name,
                "label": txt(val, "label", name),
                "move_kind": txt(val, "move_kind", "free"),
                "rotate_kind": txt(val, "rotate_kind", "free"),
                "forces": [
                    float(txt(val, f"force_{ax}", "0") or 0.0)
                    for ax in "xyz"
                ],
                "parts": parts_names,
            })
        return out

    def _six_dof_for_part(self, part_name: str) -> Optional[dict]:
        for entry in self._six_dof_entries():
            if part_name in entry["parts"]:
                return entry
        return None

    def _part_bounds_m(self, p: dict) -> Optional[tuple]:
        """Part bounding box in metres: cube base/size, else element boxes."""
        info = next((q for q in self.m.parts() if q.name == p["name"]), None)
        if info is not None and info.base and info.size:
            try:
                base = [float(v) for v in info.base.split(",")[:3]]
                size = [float(v) for v in info.size.split(",")[:3]]
                if len(base) == 3 and len(size) == 3:
                    return (base[0] / 1000.0, base[1] / 1000.0,
                            base[2] / 1000.0,
                            (base[0] + size[0]) / 1000.0,
                            (base[1] + size[1]) / 1000.0,
                            (base[2] + size[2]) / 1000.0)
            except ValueError:
                pass
        axes = self.m.mesh_axes()
        xs, ys, zs = axes.get("x", []), axes.get("y", []), axes.get("z", [])
        if not (xs and ys and zs):
            return None
        lo = [min(xs), min(ys), min(zs)]
        hi = [max(xs), max(ys), max(zs)]
        for box in p["boxes"]:
            if len(box) < 7:
                continue
            i0, i1, j0, j1, k0, k1 = box[1:7]
            for ax, (a, b, axis) in enumerate(
                    ((i0, i1, xs), (j0, j1, ys), (k0, k1, zs))):
                if 0 <= min(a, b) < len(axis):
                    lo[ax] = min(lo[ax], axis[min(a, b)])
                if 0 <= max(a, b) < len(axis):
                    hi[ax] = max(hi[ax], axis[max(a, b)])
        return (lo[0] / 1000.0, lo[1] / 1000.0, lo[2] / 1000.0,
                hi[0] / 1000.0, hi[1] / 1000.0, hi[2] / 1000.0)

    def _movb_parts(self):
        moving = self._moving_parts()
        if not moving:
            return
        self.lines.append("MOVB_PARTS")
        self.lines.append(f"{len(moving):15d}{0:12d}")
        for p, _motion in moving:
            b = self._part_bounds_m(p)
            if b is None:
                b = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            x0, y0, z0, x1, y1, z1 = b
            # exA09-4 corner order: bottom ring then top ring, the
            # trailing list is the official outline order 1 2 4 3 5 6 8 7
            corners = [
                (x0, y0, z0), (x1, y0, z0), (x0, y1, z0), (x1, y1, z0),
                (x0, y0, z1), (x1, y0, z1), (x0, y1, z1), (x1, y1, z1),
            ]
            self.lines.append(f" {p['name']}")
            self.lines.append(f"{3:15d}{0:12d}")
            self.lines.append(f"{1:8d}{len(corners):7d}")
            for cx, cy, cz in corners:
                self.lines.append(" " * 9 + "      ".join(
                    f"{v:.14e}" for v in (cx, cy, cz)))
            self.lines.append(f"{1:15d}"
                              + "".join(f"{v:12d}" for v in (2, 4, 3, 5, 6, 8, 7)))
        self.lines.append("/")

    def _movb_control(self):
        moving = self._moving_parts()
        six_dof = [e for e in self._six_dof_entries()
                   if not any(p["name"] in e["parts"]
                              for p, _m in moving)]
        if not moving and not six_dof:
            return
        self.lines.append("MOVB_CONTROL")
        for p, motion in moving:
            name = p["name"]
            vname = motion.get("value_name") or name
            kind = motion.get("kind") or ""

            def _params(vals) -> str:
                return " " * 9 + "      ".join(f"{v:.14e}" for v in vals)

            def _entry(kind_s: str, vals, part: str):
                self.lines.append(f"{kind_s}    0   ! {vname}")
                self.lines.append(_params(vals))
                self.lines.append(f"   {part}")
                self.lines.append("   /")

            if kind in ("translate", "translate+rotate"):
                vel = motion.get("velocity") or (0.0, 0.0, 0.0)
                _entry("translation", tuple(float(v) for v in vel[:3]), name)
            if kind in ("rotate", "translate+rotate"):
                omega = float(motion.get("omega") or 0.0)
                center = motion.get("center") or (0.0, 0.0, 0.0)
                normal = motion.get("normal") or (0.0, 0.0, 1.0)
                # XML stores the centre in mm (like all geometry);
                # the solver takes metres.
                _entry("rotation",
                       (omega,
                        float(center[0]) / 1000.0, float(center[1]) / 1000.0,
                        float(center[2]) / 1000.0,
                        float(normal[0]), float(normal[1]), float(normal[2])),
                       name)
            if kind == "coordinate":
                coord = motion.get("coordinate") or (0.0, 0.0, 0.0)
                _entry("coordinate",
                       tuple(float(v) / 1000.0 for v in coord[:3]), name)
        # C7: 6DOF rigid-body conditions -> dynamical entry + DYNA_MOTION
        # (exA09-4 evidence).  Parts already driven by a body_move keep
        # their classic entry above.
        for entry in self._six_dof_entries():
            if any(p["name"] in entry["parts"] and
                   (self.m.part_motion(p["name"]) is not None)
                   for p in self.parts[1:]):
                continue
            for part in entry["parts"]:
                self.lines.append(f"dynamical    0   ! {entry['name']}")
                self.lines.append(f" {entry['label']}")
                self.lines.append(f"   {part}")
                self.lines.append("   /")
                break
        self.lines.append("/")
        for entry in self._six_dof_entries():
            if any(p["name"] in entry["parts"] and
                   (self.m.part_motion(p["name"]) is not None)
                   for p in self.parts[1:]):
                continue
            self.lines.append("DYNA_MOTION")
            self.lines.append(entry["label"])
            self.lines.append("translation")
            self.lines.append("   unrestricted"
                              if entry["move_kind"] == "free"
                              else "   fixed")
            self.lines.append("rotation")
            self.lines.append("   unrestricted"
                              if entry["rotate_kind"] == "free"
                              else "   fixed")
            self.lines.append("external_force")
            self.lines.append(" " * 9 + "      ".join(
                f"{v:.14e}" for v in entry["forces"]))
            self.lines.append("   /")
            self.lines.append("   /")
            self.lines.append("/")

    def _init_region(self):
        self.lines += ["INIT_REGION", "TEMP"]
        init_temp = "20"
        for c in self.m.conditions():
            has_analysis = any(ch.tag == "analysis" for ch in c)
            if not has_analysis:
                continue
            from cabxml import _first
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None:
                continue
            vtype = val.attrib.get("type", "")
            if vtype == "initial":
                param = _first(val, "param")
                init_temp = param.text.strip() if param is not None else "20"
                break
        self.lines.append(_f(float(init_temp), 29))
        ar = self.m.analysis_region()
        self.lines.append("   " + _child_text(ar, "name", "Domain"))
        self.lines.append("   /")
        solid_temp = _child_text(self.m.project, "solid_init_temperature", "20")
        self.lines.append("TEMP")
        self.lines.append(_f(float(solid_temp), 29))
        for p in self.parts[1:]:
            self.lines.append("      " + p["name"])
        self.lines += ["   /", "/"]

    def _flux_region(self):
        self.lines.append("FLUX_REGION")
        kinds = {"total_pres": "total-pres", "out": "natural-out"}
        for name, val, region in sorted(self._bound_values("flux"),
                                        key=lambda x: _name_key(x[0])):
            kind = kinds.get(_child_text(val, "kind"), "total-pres")
            prefix = {"total-pres": "total-pres    0",
                      "natural-out": "natural-out    0"}.get(kind,
                                                             "total-pres    0")
            self.lines.append(f"{prefix}   ! {name}")
            if kind == "total-pres":
                pres = float(_child_text(val, "pressure", "0"))
                temp = float(_child_text(val, "temperature", "20"))
                self.lines.append(f"{_f(pres, 29)}{_f(temp)}")
            self.lines.append("      0  0  0  0")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _amom_region(self):
        self.lines.append("AMOM_REGION")
        # Kinds rough/power_law/smooth-moving wall (C5) are stored in XML
        # but map to noslip here: the AMOM_REGION card layout for those
        # variants needs solver-reference evidence (no local sample) —
        # deferred to a probe window (DEV_PLAN §23 C5).
        kinds = {"free_slip": "freeslip", "no_slip": "noslip"}
        groups: dict[str, tuple[str, list[str]]] = {}
        for name, val, region in sorted(self._bound_values("wall"),
                                        key=lambda x: _name_key(x[0])):
            kind = kinds.get(_child_text(val, "kind"), "noslip")
            if kind not in groups:
                groups[kind] = (name, [])
            groups[kind][1].append(region)
        for kind, (first_name, regions) in groups.items():
            prefix = {"freeslip": "freeslip  static    0",
                      "noslip": "noslip  static    0"}.get(
                          kind, "noslip  static    0")
            self.lines.append(f"{prefix}   ! {first_name}")
            for r in regions:
                self.lines.append("   " + r)
            self.lines.append("   /")
        # undefined-faces wall condition
        undef_name = self._undefined_value("wall")
        if undef_name:
            undef = self.m.find_value(undef_name)
            kind = kinds.get(_child_text(undef, "kind"), "noslip") \
                if undef is not None else "noslip"
            prefix = {"freeslip": "freeslip  static    0",
                      "noslip": "noslip  static    0"}.get(
                          kind, "noslip  static    0")
            self.lines.append(f"{prefix}   ! "
                              f"{undef_name}")
            self.lines.append("   @UNDEFINEDMOM")
            self.lines.append("   /")
        self.lines.append("/")

    def _aent_region(self):
        self.lines.append("AENT_REGION")
        # sample-driven default conduction block (mapping TBD, P5)
        self.lines += [
            "conduction    0",
            _f(0.0, 29),
            "   @UNDEFINEDENTX",
            "   /",
        ]
        # undefined heat conditions (value-only, bound implicitly)
        markers = {
            "domain_boundary": "@UNDEFINEDENTB",
            "between_fluids_solids": "@UNDEFINEDENTF",
            "nbetween_solids": "@UNDEFINEDENTS",
        }
        for undef, vname in self._undefined_conditions():
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != "heat_transfer":
                continue
            key = next((m for k, m in markers.items() if k in vname),
                       "@UNDEFINEDENTS")
            kind = _child_text(val, "kind", "adiabatic")
            kw = "adiabatic" if kind == "adiabatic" else "conduction"
            prefix = {"adiabatic": "adiabatic    0",
                      "conduction": "conduction    0"}.get(
                          kw, "conduction    0")
            self.lines.append(f"{prefix}   ! {vname}")
            if kw == "conduction":
                temp = float(_child_text(val, "temperature", "0"))
                self.lines.append(_f(temp, 29))
            self.lines.append("   " + key)
            self.lines.append("   /")
        for name, val, region in sorted(self._bound_values("heat_transfer"),
                                        key=lambda x: _name_key(x[0])):
            kind = _child_text(val, "kind", "adiabatic")
            kw = "adiabatic" if kind == "adiabatic" else "conduction"
            prefix = {"adiabatic": "adiabatic    0",
                      "conduction": "conduction    0"}.get(
                          kw, "conduction    0")
            self.lines.append(f"{prefix}   ! {name}")
            if kw == "conduction":
                temp = float(_child_text(val, "temperature", "0"))
                self.lines.append(_f(temp, 29))
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _vent_region(self):
        self.lines.append("VENT_REGION")
        entries = list(self._bound_parts_values("heat_source"))
        entries += list(self._bound_analysis_values("heat_source"))
        for name, val, region in sorted(
                entries, key=lambda x: _name_key(x[0])):
            src = float(_child_text(val, "source", "0"))
            self.lines.append(f"source    0   ! {name}")
            self.lines.append(f"{_f(src, 29)}   2")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _vfwl_region(self):
        self.lines.append("VFWL_REGION")
        rad = self.m.find_value("_rad_condition(undefined_faces)")
        if rad is not None:
            temp = float(_child_text(rad, "temperature", "20"))
            factor = float(_child_text(rad, "factor", "0.9"))
            self.lines += [
                "detailFAC    0   1   0   ! _rad_condition(undefined_faces)",
                _f(temp, 29),
                "              6           0   1.00    0.00",
                f"{_f(factor)}{_f(1.0 - factor)}{_f(0.0)}",
                "   @UNDEFINEDVFWL",
                "   /",
            ]
        for p in self.parts[1:]:
            self.lines += [
                f"detailBDY   0   1   0   ! {p['name']}",
                "         0   0    1.00    0.00",
                f"{_f(0.9)}{_f(0.1)}{_f(0.0)}{_f(0.0)}",
                f"   {p['name']}",
                "   /",
            ]
        self.lines.append("/")

    def _vfem_vfde(self):
        self.lines += [
            "VFEM",
            f"{_i(1, 15)}{_f(-1.0, 26)}",
            "/",
            "VFDE",
        ]
        aset = self.m.root.find("analysis_set")
        rad = aset.find("radiation") if aset is not None else None
        mpcl = _rad_int(rad, "max_particle", 20000)
        self.lines.append(f"   MPCL{_i(mpcl, 12)}")
        self.lines.append(f"   LEAP{_i(VFDE_LEAP, 9)}")
        self.lines.append(f"   IXYZ{_i(_rad_int(rad, 'space_cycle', 0), 9)}")

        # MREF is always written (default 100).  MRCL is written ONLY when
        # smrt_rays is set in the radiation XML: the golden ex4_e.s emits
        # MREF but not MRCL (smrt_rays absent -> defaults to MPCL), so
        # emitting the default breaks .s parity.
        self.lines.append(
            f"   MREF{_i(_rad_int(rad, 'max_reflection', 100), 9)}")
        if rad is not None and rad.find("smrt_rays") is not None:
            mrcl = _rad_int(rad, "smrt_rays", mpcl)
            self.lines.append(f"   MRCL{_i(mrcl, 9)}")
        self.lines.append(f"   EM1{VFDE_EM1:>9}")
        self.lines.append(
            f"   MAXM{_i(_rad_int(rad, 'max_group_num', 4000), 9)}")
        pgn = _child_text(rad, "parts_group_num", "6,-1").split(",")[0]
        try:
            mgmi = int(float(pgn))
        except ValueError:
            mgmi = 6
        self.lines.append(f"   MGMI{_i(mgmi, 9)}")
        self.lines.append("/")

    def _peltier(self):
        """R7: PELTIER_OUT / PELTIER_SET — 唯一有官方 .s 实证的专用件段。

        依据 CradleCFD_2023.2 exA22-2（配套 exA22-2_e.cab 可交叉验证）::

            PELTIER_OUT
                   0:L
             basic
            /
            PELTIER_SET
                Peltier
                     1.00000000000000e+01   @S:_peltier1_cr   @S:_peltier1_qc   @S:_peltier1_qh   @S:_peltier1_dt
            /

        官方 cab 中该件 ``paramV unit="V" = 15.5,17.5,10``，卡片数值
        ``1.0e+01`` 即 **paramV 的最后一个元素**（驱动电压）；``@S:``
        求解器变量按 Peltier 件出现顺序从 1 编号（cr/qc/qh/dt 为电流/
        冷端/热端/温差输出）。其余四种专用件（AC Unit / Diffuser /
        Card Guide / Heat Pipe）在 2023.2 样本 *.s 与 2025.2 探针
        SaveSFile 中均无对应卡片 —— 无实证不发射。
        """
        entries = []
        for p in self.m.parts():
            if p.kind != "peltier":
                continue
            params = self.m.part_params(p.name) or {}
            param_v = params.get("paramV")
            if not param_v:
                continue
            entries.append((p.name, float(param_v[-1])))
        if not entries:
            return
        self.lines += ["PELTIER_OUT", "       0:L", " basic", "/"]
        self.lines.append("PELTIER_SET")
        for i, (name, volt) in enumerate(entries, 1):
            refs = "".join(f"   @S:_peltier{i}_{s}"
                           for s in ("cr", "qc", "qh", "dt"))
            self.lines.append(f"    {name}")
            # 官方数值列宽 29（9 空格 + .14e），与 VENT source 行一致
            self.lines.append(f"{_f(volt, 29)}{refs}")
        self.lines.append("/")

    def _autofixp(self):
        aset = self.m.root.find("analysis_set")
        vals = [int(x) for x in
                _child_text(aset, "auto_fixp", "1,1").split(",")[:2]]
        self.lines += ["AUTOFIXP", f"{_i(vals[0])}{_i(vals[1])}"]

    def _es_field_bc(self):
        """ES_FIELD_BC — electrostatic electric-potential boundaries (C3).

        Evidence: official exA07-3 (cradle corpus) — ``<value
        type="e_field">`` with ``<e_potential unit="V">`` bound to
        face_list regions emits one ``epotential    0   ! <name>`` card
        per region (value line + region + ``/``)::

            ES_FIELD_BC
            epotential    0   ! 0V
                         0.00000000000000e+00
               Xmin面
               /

        Placed before FOUT (after ES_FIELD/ES_FIELD_PROP/ES_FIELD_SORC in
        the official file; the non-card members of that block are
        material-dependent and not emitted here).
        """
        groups: list[tuple[str, str, str]] = []
        for val in self.m.values_of_type("e_field"):
            name = _child_text(val, "name")
            pot = _child_text(val, "e_potential", "0")
            if not name:
                continue
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "region":
                        region = (ch.text or "").strip()
                        if region:
                            groups.append((name, pot, region))
        if not groups:
            return
        self.lines.append("ES_FIELD_BC")
        for name, pot, region in groups:
            self.lines.append(f"epotential    0   ! {name}")
            try:
                self.lines.append(_f(float(pot)))
            except ValueError:
                self.lines.append(_f(0.0))
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _sufs_region(self):
        """SUFS_REGION contactangle cards — free-surface Contact Angle (C3).

        Evidence: official exA09-4 — the card layout is::

            SUFS_REGION
            contactangle   0
                  9.00000000000000e+01
               @UNDEFINEDCAG
               /

        Only user-defined ``<value type="contact_angle">`` conditions are
        emitted here (same card body with the bound region); the
        ``@UNDEFINEDCAG`` default card in the sample has no user value
        behind it, so the trigger for emitting it is unknown — deferred.
        """
        groups: list[tuple[str, str, str]] = []
        for val in self.m.values_of_type("contact_angle"):
            name = _child_text(val, "name")
            angle = _child_text(val, "angle", "90")
            if not name:
                continue
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "region":
                        region = (ch.text or "").strip()
                        if region:
                            groups.append((name, angle, region))
        if not groups:
            return
        self.lines.append("SUFS_REGION")
        for name, angle, region in groups:
            self.lines.append("contactangle   0 ")
            try:
                self.lines.append(f"{float(angle):26.14e}")
            except ValueError:
                self.lines.append(f"{90.0:26.14e}")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _surf_porous(self):
        """SURF_POROUS — MARS free-surface attenuation zones (C6).

        Evidence: official exA15-6 — ``<value type="surface_porous">``
        with ``kind=energy_decay`` (Wave Energy Attenuation Zone) bound
        via ``<parts>`` conditions emits::

            SURF_POROUS
            energyattenuation
                         -1           2        <- dir(15) + fluid_no(12)
              <decay 4 floats + depth>          <- 5 x _f(26)
               attenuation_zone_xm              <- parts name
               /

        direction maps -X -> -1, +X -> 1 (other axes have no sample).
        Permeable-object cards would live in the same section with a
        different kind — no sample, not emitted.
        """
        _DIR_CODE = {"-X": -1, "+X": 1}
        groups: list[tuple[str, int, int, list[float], str]] = []
        for val in self.m.values_of_type("surface_porous"):
            if _child_text(val, "kind").strip() != "energy_decay":
                continue
            name = _child_text(val, "name")
            direction = _child_text(val, "direction")
            if direction not in _DIR_CODE:
                continue
            try:
                fluid_no = int(_child_text(val, "fluid_no", "1"))
            except ValueError:
                continue
            decay = _child_text(val, "decay")
            try:
                nums = [float(x) for x in decay.split(",")]
            except ValueError:
                continue
            try:
                depth = float(_child_text(val, "depth", "0"))
            except ValueError:
                continue
            nums += [0.0] * (4 - len(nums))
            nums = nums[:4] + [depth]
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "parts":
                        parts = (ch.text or "").strip()
                        if parts:
                            groups.append((name, _DIR_CODE[direction],
                                           fluid_no, nums, parts))
        if not groups:
            return
        self.lines.append("SURF_POROUS")
        for _name, d, n, nums, parts in groups:
            self.lines.append("energyattenuation")
            self.lines.append(f"{d:15d}{n:12d}")
            self.lines.append("".join(_f(v) for v in nums))
            self.lines.append("   " + parts)
            self.lines.append("   /")
        self.lines.append("/")

    def _lsol_sections(self):
        """LSOL_FORCE_MODEL / LSOL_OPTION / LSOL_TIME_STEP — DEM particle
        interaction configuration (C1, Force between Particles family).

        Evidence: official exA07-4 — ``<analysis_etc><dem>`` children map
        1:1 (dem_contact_model=1 -> linear_spring_dashpot,
        dem_rolling_resistance_model=1 -> simplified_linear,
        dem_it_scheme -> time_integration, dem_detect_algorithm/timing/
        n_factor, dem_min_reynolds, dem_stab_scale, dem_time_divide/
        dem_max_loop/dem_recoverty_*).  Only the evidenced model names
        (1) are emitted; LSOL_FORCE_IP (per-pair material properties)
        is probe-deferred.  Sections are omitted when no <dem> block
        exists (ex4_e golden parity).
        """
        dem = self.m.analysis_etc_section("dem")
        if dem is None:
            return
        if _child_text(dem, "dem_motion", "0").strip() != "1":
            return

        def num(tag, default):
            try:
                return float(_child_text(dem, tag, str(default)))
            except ValueError:
                return float(default)

        self.lines.append("LSOL_FORCE_MODEL")
        self.lines.append("contact_model")
        contact = _child_text(dem, "dem_contact_model", "1").strip()
        if contact != "1":
            return  # other contact models have no name evidence
        self.lines.append("   linear_spring_dashpot")
        rolling = _child_text(dem, "dem_rolling_resistance_model",
                              "1").strip()
        if rolling != "1":
            return  # other rolling models have no name evidence
        self.lines.append("rolling_resistance_model")
        self.lines.append("   simplified_linear")
        self.lines.append("cohesion_model")
        self.lines.append(
            "   none" if _child_text(dem, "dem_adhesion", "0").strip()
            == "0" else "   none")
        self.lines.append("/")
        self.lines.append("LSOL_OPTION")
        self.lines.append("lagrangian_solver")
        self.lines.append(_i(1, 12))
        self.lines.append("time_integration")
        self.lines.append(_i(int(num("dem_it_scheme", 2)), 12))
        self.lines.append("contact_detection_algorithm")
        self.lines.append(_i(int(num("dem_detect_algorithm", 3)), 12))
        self.lines.append("contact_detection_timing")
        self.lines.append(_i(int(num("dem_detect_cycle", 1)), 12))
        self.lines.append("neighboring_factor")
        self.lines.append(f"{num('dem_detect_n_factor', 1.2):29.14e}")
        self.lines.append("min_Reynolds")
        self.lines.append(f"{num('dem_min_reynolds', 1e-10):29.14e}")
        self.lines.append("void_fraction")
        self.lines.append(_i(1, 12))
        self.lines.append("stab_factor")
        self.lines.append(f"{num('dem_stab_scale', 0.0):29.14e}")
        self.lines.append("/")
        self.lines.append("LSOL_TIME_STEP")
        self.lines.append("time_step")
        self.lines.append(" division")
        self.lines.append(_i(int(num("dem_time_divide", 5)), 12))
        self.lines.append("loop")
        self.lines.append(_i(int(num("dem_max_loop", 100)), 12))
        self.lines.append("recovery")
        self.lines.append(" repeat")
        self.lines.append(
            f"{num('dem_recoverty_step_scale', 0.1):26.14e}"
            f"{int(num('dem_recoverty_max', 100)):15d}")

    def _pcle_handling(self):
        """PCLE_HANDLING — particle destruction / sedimentation regions
        (C1: Particle Vanishment / Sedimentation).

        Evidence: official exA07-3 — ``<value type="particle_condition">``
        with kind destruction/sedimentation and ``applied_face`` bound to
        face_list regions emits::

               1:L
            destruction
               0
               Xmax面
               /

        per condition, under a ``PCLE_HANDLING`` header.  Omitted when no
        such values exist (ex4_e golden parity).
        """
        groups: list[tuple[str, str, str]] = []
        for val in self.m.values_of_type("particle_condition"):
            kind = _child_text(val, "kind").strip()
            if kind not in ("destruction", "sedimentation"):
                continue
            name = _child_text(val, "name")
            face = _child_text(val, "applied_face", "0").strip() or "0"
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "region":
                        region = (ch.text or "").strip()
                        if region:
                            groups.append((kind, face, region))
        if not groups:
            return
        self.lines.append("PCLE_HANDLING")
        self.lines.append(f"{1:8d}:L")
        for kind, face, region in groups:
            self.lines.append(kind)
            self.lines.append(f"{int(float(face)):4d}")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _topopt_region(self):
        """TOPOPT_REGION — topology-optimization design space / volume
        constraint (C8).

        Evidence: official exA28-1_step2 — ``<value type="topo_obj_func">``
        + ``<value type="topo_design_space">`` (vol_constraint_type /
        vol_constraint), both bound via ``<parts>`` (Design_space), emit::

            TOPOPT_REGION
            objective_and_constraint    0   ! 体積目的関数1
                          1           1
                 0.00000000000000e+00  1.20000000000000e-01   <- lower/upper
                 0.00000000000000e+00
               Design_space               (one line per bound parts)
               /

        The leading pair (1, 1) has a single sample — pinned constants.
        Omitted when no topo_design_space values exist (ex4_e golden
        parity).
        """
        ds_vals = self.m.values_of_type("topo_design_space")
        if not ds_vals:
            return
        obj_vals = self.m.values_of_type("topo_obj_func")

        def txt(val, tag, default=""):
            from cabxml import _first
            el = _first(val, tag)
            return el.text.strip() if el is not None and el.text                 else default

        obj_name = txt(obj_vals[0], "name") if obj_vals else             txt(ds_vals[0], "name")
        parts_list: list[str] = []
        for val in ds_vals + obj_vals:
            name = txt(val, "name")
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "parts":
                        parts = (ch.text or "").strip()
                        if parts:
                            # the official card repeats the region line
                            # once per bound condition (no dedup)
                            parts_list.append(parts)
        lower = 0.0
        upper = 0.0
        try:
            vc = float(txt(ds_vals[0], "vol_constraint", "0"))
            upper = vc
        except ValueError:
            pass
        self.lines.append("TOPOPT_REGION")
        self.lines.append(
            f"objective_and_constraint    0   ! {obj_name}")
        self.lines.append(f"{1:15d}{1:12d}")
        self.lines.append(_f(lower, 29) + _f(upper))
        self.lines.append(_f(0.0, 29))
        for parts in parts_list:
            self.lines.append("   " + parts)
            self.lines.append("   /")
        self.lines.append("/")

    def _humw_region(self):
        """HUMW_REGION — humidity boundary conditions (C2).

        Evidence: official exA05-2 (cradle corpus) — ``<value
        type="humidity">`` with ``kind=boundary`` / ``type=2`` and
        ``param1``/``param2`` emits one ``transfer  wallhumidity    0``
        card PER bound region, each closed with ``/``::

            HUMW_REGION
            transfer  wallhumidity    0   ! 湿度1
                         2.44000000000000e-02
                         6.60000000000000e-01
               Xmin面
               /

        ``type=1`` values (region-pair family) alternate between
        ``lewislaw  saturation`` and ``diffusion  saturation`` prefixes
        with no discriminating XML field in the sample — emission for
        that family is probe-deferred.  Section omitted when no type=2
        humidity boundary exists (empty sections are dropped).
        """
        groups: list[tuple[str, str, str, str]] = []
        for val in self.m.values_of_type("humidity"):
            if _child_text(val, "kind").strip() != "boundary":
                continue
            if _child_text(val, "type").strip() != "2":
                continue
            name = _child_text(val, "name")
            p1 = _child_text(val, "param1", "0")
            p2 = _child_text(val, "param2", "0")
            for c in self.m.conditions():
                if _child_text(c, "value") != name:
                    continue
                for ch in c:
                    if ch.tag == "region":
                        region = (ch.text or "").strip()
                        if region:
                            groups.append((name, p1, p2, region))
        if not groups:
            return
        self.lines.append("HUMW_REGION")
        for name, p1, p2, region in groups:
            self.lines.append(f"transfer  wallhumidity    0   ! {name}")
            try:
                self.lines.append(_f(float(p1)))
            except ValueError:
                self.lines.append(_f(0.0))
            try:
                self.lines.append(_f(float(p2)))
            except ValueError:
                self.lines.append(_f(0.0))
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _fout(self):
        out = self.m.root.find("output")
        from cabxml import _children
        self.lines.append("FOUT")
        if out is not None:
            for f in _children(out, "fout"):
                self.lines.append(f"    {f.attrib.get('type', '')}")
        self.lines.append("/")

    def _meix_var(self):
        out = self.m.root.find("output")
        cycle = _child_text(out, "minmax_cycle", "1")
        kind = _child_text(out, "minmax_kind", "1,1,2").split(",")
        kind += ["0"] * (3 - len(kind))
        self.lines.append("MEIX_VAR")
        self.lines.append(f"{_i(int(cycle))}{_i(int(kind[0]))}"
                          f"{_i(int(kind[1]))}{_i(int(kind[2]))}")
        from cabxml import _children
        if out is not None:
            for v in _children(out, "minmax_var"):
                if (v.text or "").strip() == "T":
                    vtype = v.attrib.get("type", "")
                    aset = self.m.root.find("analysis_set")
                    turb = _child_text(aset, "turbulence", "0")
                    if vtype in ("TURK", "TEPS") and turb == "0":
                        continue
                    self.lines.append(f"    {vtype}")
        self.lines.append("/")

    def _balances(self):
        out = self.m.root.find("output")
        c1 = _child_text(out, "hbal_output_cycle1", "0").split(":")[0]
        c2 = _child_text(out, "hbal_output_cycle2", "0").split(":")[0]
        self.lines += [
            "HBAL_PARTS",
            f"{_i(int(c1), 5)}:L{_i(0, 12)}",
            "HBAL_BTW_PARTS",
            f"{_i(int(c2), 5)}:L{_i(0, 12)}",
            "FBAL",
            f"{_i(1, 5)}:L",
        ]

    # Evidence-locked C4 quantity tags for Output Passage cards; further
    # quantities need corpus evidence (only heat_flux observed).
    _FLUX_SUM_QUANTITIES = ("heat_flux",)

    def _flux_sum(self):
        """FLUX_SUM — Output Passage (``list_summary``) regions (C4).

        Evidence: official exA18-2 (cradle corpus) — two ``list_summary``
        values (通過流量1/2 with ``heat_flux=1``) bound to regions
        ``in`` / ``out`` emit exactly::

            FLUX_SUM
                          1            <- option count, width 15
            heat_flux
                in
               /
            heat_flux
                out
               /
            /

        The leading count has a single sample; pinned as a width-15 field.
        The other C4 output commands (PFOC_REGION / SURFLIST / STOP_VAR /
        NCOZ_OUTPUT / OCSV_PARTS / PCL_RESTRICTION) have no corpus
        evidence — their UI/storage exists but nothing is emitted here
        (probe-deferred, see DEV_PLAN §23 C4).
        """
        groups: list[tuple[str, str]] = []
        for val in self.m.values():
            if val.attrib.get("type") != "list_summary":
                continue
            name = _child_text(val, "name")
            for tag in self._FLUX_SUM_QUANTITIES:
                if _child_text(val, tag, "0").strip() == "1":
                    for c in self.m.conditions():
                        if _child_text(c, "value") != name:
                            continue
                        region = ""
                        for ch in c:
                            if ch.tag == "region":
                                region = (ch.text or "").strip()
                        groups.append((tag, region))
        if not groups:
            return
        self.lines.append("FLUX_SUM")
        self.lines.append(_i(1, 15))
        for tag, region in groups:
            self.lines.append(tag)
            self.lines.append(f"    {region}")
            self.lines.append("   /")
        self.lines.append("/")

    def _cutcell(self):
        """R9-B: CUTCELL_OPTION / CUTCELL_GAP 段。

        样本实证（CradleCFD_2023.2 Exercise_e/Function/exA23-2/
        exA23-2b_cut_cell_e.s L217-225）::

            CUTCELL_OPTION
            volume_min_ratio
                     5.00000000000000e-03
            thin_shape_model
                       1
            /
            CUTCELL_GAP
                         -1          -1
            /

        - volume_min_ratio <- analysis_set/cutcell_criteria（手册默认
          0.05；样本值 0.005）；
        - thin_shape_model <- analysis_set/cutcell_thin_model（缺省 1）；
        - CUTCELL_GAP 两整数为样本唯一观测值（cutcell_all_gap=T 时
          -1 -1），无其余变体样本可考证，按常量发射。

        发射判据 = 存在零件级 cut-cell 注册（<parts> 下 <cutcell> T，
        exA23-2b_cut_cell.cab XML 实证）——staircase 对照版虽带相同
        analysis_set 值但不注册零件，其 .s 无本段。

        R20 完整接线：注册零件同时在头部发 CCEL 行（引用 <project>
        .ccel）、PARTS 段用负 id 空盒列表（几何移入 .ccel 二进制容
        器，:func:`build_ccel`），导出路径负责把 .ccel 写到 .s 旁。
        """
        registered = any(_part_is_cutcell(p) for p in self.m.parts())
        if not registered:
            return
        aset = self.m.root.find("analysis_set")
        try:
            criteria = float(_child_text(aset, "cutcell_criteria", "0.05"))
        except ValueError:
            criteria = 0.05
        try:
            thin = int(_child_text(aset, "cutcell_thin_model", "1"))
        except ValueError:
            thin = 1
        self.lines += [
            "CUTCELL_OPTION",
            "volume_min_ratio",
            _f(criteria, 29),
            "thin_shape_model",
            _i(thin),
            "/",
            "CUTCELL_GAP",
            f"{-1:15d}{-1:12d}",
            "/",
        ]

    def _tprt(self):
        self.lines += ["TPRT_OUTPUT", f"{_i(len(self.parts), 15)}"]
        ids = [p["id"] for p in self.parts]
        for i in range(0, len(ids), 5):
            row = ids[i:i + 5]
            self.lines.append(f"{row[0]:15d}"
                              + "".join(f"{x:11d}" for x in row[1:]))

    # -- helpers ----------------------------------------------------------

    def _bound_values(self, vtype: str):
        """Yield (value_name, value_elem, region_or_parts_target) for
        conditions whose value element has the requested type."""
        from cabxml import _first
        for c in self.m.conditions():
            target = None
            for child in c:
                if child.tag in ("region", "parts"):
                    target = (child.tag, child.text.strip() if child.text else "")
            if target is None:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            region = target[1]
            if target[0] == "parts":
                continue
            if re.fullmatch(r"undefine\d+", region):
                continue
            yield vname, val, region

    def _bound_parts_values(self, vtype: str):
        """Conditions bound to parts (used by VENT_REGION)."""
        from cabxml import _first
        for c in self.m.conditions():
            parts_name = None
            for child in c:
                if child.tag == "parts":
                    parts_name = child.text.strip() if child.text else ""
            if parts_name is None:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            yield vname, val, parts_name

    def _bound_analysis_values(self, vtype: str):
        """Conditions bound to the analysis/domain region (volumetric
        sources etc.)."""
        dom = self.m.domain_name() or "Domain(cuboid)"
        for c in self.m.conditions():
            region = None
            for child in c:
                if child.tag in ("analysis", "region"):
                    region = child.text.strip() if child.text else ""
            if region is None or region != dom:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            yield vname, val, region

    def _undefined_conditions(self):
        """(undefine_region_name, value_name) for `undefineN` bindings."""
        for c in self.m.conditions():
            region = None
            vname = None
            for child in c:
                if child.tag == "region":
                    region = child.text.strip() if child.text else ""
                if child.tag == "value":
                    vname = child.text.strip() if child.text else ""
            if region and vname and re.fullmatch(r"undefine\d+", region):
                yield region, vname

    def _undefined_value(self, vtype: str) -> str:
        """Value name of the undefined condition with the given type."""
        for _, vname in self._undefined_conditions():
            val = self.m.find_value(vname)
            if val is not None and val.attrib.get("type", "") == vtype:
                return vname
        return ""


def build_sdat(model: StpreModel, props: PropertyModel, meshes=None,
               ccel_name: str = "") -> str:
    """Render the .s text.

    ``meshes``/``ccel_name`` only affect the R20 cut-cell wiring: the
    header ``CCEL`` line uses ``ccel_name`` when given (the basename the
    caller will actually write) instead of the ``<project>.ccel``
    convention. Pair with :func:`build_ccel` at the write site.
    """
    return SExport(model, props, meshes=meshes, ccel_name=ccel_name).render()


def validate_sfile(text: str) -> list[tuple[str, str]]:
    """P3: structural validation of an S file.

    Returns (level, message) diagnostics (INFO/WARN/ERROR):
    * required sections present (CXYZ/PARTS/REGIONS) and GOGO termination;
    * SDAT header grid counts vs CXYZ axis point counts;
    * PARTS occupancy boxes within the CXYZ axis ranges.
    """
    diags: list[tuple[str, str]] = []
    raw_lines = text.splitlines()
    lines = [l.strip() for l in raw_lines]
    for sec in ('CXYZ', 'PARTS', 'REGIONS'):
        if sec in lines:
            diags.append(('INFO', 'section %s present' % sec))
        else:
            diags.append(('WARN', 'section %s missing' % sec))
    if lines and lines[-1].strip() == 'GOGO':
        diags.append(('INFO', 'GOGO termination present'))
    else:
        diags.append(('WARN', 'missing GOGO termination'))
    # -- CXYZ axis point counts ----------------------------------------
    axes: list[list[float]] = []
    current: list[float] = []
    if 'CXYZ' in lines:
        for raw in lines[lines.index('CXYZ') + 1:]:
            s = raw.strip()
            if s == 'PARTS':
                if current:
                    axes.append(current)
                break
            if s in ('0', '0.0'):
                if current:
                    axes.append(current)
                    current = []
                continue
            try:
                current.extend(float(x) for x in s.split())
            except ValueError:
                continue
        counts = [len(a) - 1 for a in axes if len(a) >= 2]
        diags.append(('INFO', 'CXYZ axis points: %s' % [len(a) for a in axes]))
        # -- per-axis sanity: finite, strictly increasing, positive widths
        for ax, arr in enumerate(axes):
            if len(arr) < 2:
                continue
            n_bad = sum(1 for v in arr
                        if not (v == v) or abs(v) == float('inf'))
            if n_bad:
                diags.append(('ERROR', 'axis %d: %d non-finite value(s)'
                              % (ax, n_bad)))
                continue
            widths = [arr[i + 1] - arr[i] for i in range(len(arr) - 1)]
            n_neg = sum(1 for w in widths if w <= 0.0)
            if n_neg:
                diags.append(('ERROR', 'axis %d: %d non-positive width(s) '
                             '(non-monotonic/duplicate coords)' % (ax, n_neg)))
            else:
                diags.append(('INFO', 'axis %d monotonic, min width %g'
                              % (ax, min(widths))))
        # -- SDAT header counts (12-wide fields) -----------------------
        try:
            sd = lines.index('SDAT')
            hdr = None
            for cand in raw_lines[sd + 1:sd + 40]:
                fields = [cand[i:i + 12].strip() for i in
                          range(0, len(cand), 12)]
                if len(fields) == 8 and all(f.lstrip('-').isdigit()
                                            for f in fields):
                    hdr = [int(f) for f in fields]
                    break
            if hdr is not None and len(counts) == 3:
                for ax in range(3):
                    expect, got = hdr[ax], counts[ax]
                    if expect != got:
                        diags.append(('WARN', 'axis %d: SDAT=%d CXYZ=%d'
                                      % (ax, expect, got)))
                    else:
                        diags.append(('INFO', 'axis %d count %d consistent'
                                      % (ax, got)))
        except Exception:
            diags.append(('WARN', 'SDAT header counts not parsable'))
        # -- PARTS boxes within range ------------------------------------
        if 'PARTS' in lines:
            n_bad = 0
            n_box = 0
            for raw in lines[lines.index('PARTS') + 1:]:
                s = raw.strip()
                if s == '/' or s == '   /':
                    break
                nums = [int(x) for x in s.split() if x.lstrip('-').isdigit()]
                if len(nums) == 6:
                    n_box += 1
                    if len(counts) == 3 and (
                            nums[1] > counts[0] or nums[3] > counts[1]
                            or nums[5] > counts[2]):
                        n_bad += 1
                    if nums[0] > nums[1] or nums[2] > nums[3] \
                            or nums[4] > nums[5]:
                        diags.append(('ERROR',
                                      'inverted occupancy box %s' % nums))
            diags.append(('INFO', 'PARTS boxes: %d' % n_box))
            if n_bad:
                diags.append(('ERROR', '%d box(es) out of axis range' % n_bad))
            else:
                diags.append(('INFO', 'all PARTS boxes within axis range'))
    return diags


def parse_s_parts(text: str) -> list[str]:
    """Names of the part/region entries in the PARTS section of an S file.

    PARTS header lines look like ``<id><material><fraction>    <name>``
    (the fluid part first, then one entry per part).  Numeric box-list
    lines are skipped.  Used by [Mesh] - [Checking S-File].
    """
    names: list[str] = []
    in_parts = False
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s == "PARTS":
            in_parts = True
            continue
        if not in_parts:
            continue
        if s in ("/", "   /"):
            break
        parts = s.split()
        if len(parts) >= 4:
            try:
                int(parts[0])
                int(parts[1])
                float(parts[2])
            except ValueError:
                continue
            names.append(" ".join(parts[3:]).strip())
    return names
