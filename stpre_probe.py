"""STpre gridding/meshing algorithm probe (multi-instance black-box).

Purpose
-------
Reverse-guess STpre's gridding/meshing rules by running a controlled
matrix of projects through the VB/COM API (``STpre_Bx64net.Application``)
and recording every input/echo/output pair:

* computational domain (base/size, incl. non-cube and offset domains);
* vertex detection (all/representative/axis_plane/minmax/none/uniform);
* division method (coarse/detail/auto1/auto3) + element targets;
* standard length / threshold / internal ratio / external ratio;
* edge-contact flag and sub-block scale;
* resulting mesh_block axis coordinates, part cell boxes and mesh_control
  echoes.

Each case launches a fresh STpre instance (single-session ownership guard in
``cab_stpre_api`` ensures no user-open STpre is hijacked).  Results are
written to ``data/stpre_probe_<timestamp>.json`` for offline rule mining.

Usage::

    python stpre_probe.py --cases base,vd_all,std_5_0 --out data/probe.json
    python stpre_probe.py --analyze data/probe.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cab_stpre_api
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parent
BASE_CAB = ROOT / "tests" / "box.cab"
DATA_DIR = ROOT / "data"
_BASE_CABS = {
    "box": ROOT / "tests" / "box.cab",
    "tr03": ROOT / "tests" / "tr03.cab",
    "ex4e": ROOT / "tests" / "ex4_e.cab",
}

_VD_KEY = {0: "all", 1: "main", 2: "plane", 3: "minmax",
           4: "none", 5: "uniform"}
_METHOD_KEY = {"coarse": "coarse", "detail": "detail",
               "auto1": "auto1", "auto3": "auto3"}


@dataclass
class ProbeCase:
    """One black-box probe. Coordinates are in mm."""

    name: str
    domain_min: tuple[float, float, float] = (-25.0, -25.0, -25.0)
    domain_max: tuple[float, float, float] = (25.0, 25.0, 25.0)
    vertex_detection: int = 3              # 0..5 (STpre select_vertex)
    method: str = "detail"                 # coarse|detail|auto1|auto3
    target_elements: Optional[int] = None  # auto1
    target_per_axis: Optional[tuple[int, int, int]] = None  # auto3
    standard_length: tuple[float, float, float] = (1.0, 1.0, 1.0)
    threshold: tuple[float, float, float] = (0.1, 0.1, 0.1)
    ratio_in: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ratio_out: tuple[float, float, float] = (1.2, 1.2, 1.2)
    edge_contact: int = 0
    divide_scale: int = 2
    do_element: bool = True
    part_transform: Optional[str] = None   # 16 column-major values
    extra_part: bool = False
    stl_part: bool = False                 # L-shaped non-convex polygon part
    drop_box: bool = False                 # remove base box part
    base: str = "box"                      # box | tr03 | ex4e
    keep_parts: tuple[str, ...] = ()       # delete every other part
    stl_body_files: bool = False           # register STL in <body_files>
    note: str = ""

    def key(self) -> str:
        return _METHOD_KEY.get(self.method, "detail")

    def grid_params(self) -> list[tuple]:
        params: list[tuple] = [
            ("division_method", self.key(), "", ""),
            ("division_type", _VD_KEY.get(self.vertex_detection, "minmax"),
             "", ""),
        ]
        if self.method == "auto1" and self.target_elements is not None:
            params.append(("division_num", int(self.target_elements), 0, 0))
        elif self.method == "auto3" and self.target_per_axis is not None:
            params.append(("division_num", *(int(v) for v in
                                             self.target_per_axis)))
        params.append(("outer_ratio", *(float(v) for v in self.ratio_out)))
        params.append(("edge_contact", int(self.edge_contact), "", ""))
        return params

    def block_params(self) -> list[tuple]:
        return [
            ("length", *(float(v) for v in self.standard_length)),
            ("ratio", *(float(v) for v in self.ratio_in)),
            ("limit", *(float(v) for v in self.threshold)),
        ]

    def input_dict(self) -> dict:
        return {
            "domain_min": list(self.domain_min),
            "domain_max": list(self.domain_max),
            "vertex_detection": self.vertex_detection,
            "method": self.method,
            "target_elements": self.target_elements,
            "target_per_axis": list(self.target_per_axis)
            if self.target_per_axis else None,
            "standard_length": list(self.standard_length),
            "threshold": list(self.threshold),
            "ratio_in": list(self.ratio_in),
            "ratio_out": list(self.ratio_out),
            "edge_contact": self.edge_contact,
            "divide_scale": self.divide_scale,
            "do_element": self.do_element,
            "part_transform": self.part_transform,
            "extra_part": self.extra_part,
            "stl_part": self.stl_part,
            "drop_box": self.drop_box,
            "base": self.base,
            "keep_parts": list(self.keep_parts),
            "stl_body_files": self.stl_body_files,
            "note": self.note,
        }


def default_cases() -> list[ProbeCase]:
    base = dict(domain_min=(-25.0, -25.0, -25.0),
                domain_max=(25.0, 25.0, 25.0))
    cases = [
        ProbeCase(name="base_minmax_detail", **base,
                  vertex_detection=3, method="detail"),
        ProbeCase(name="vd_all", **base, vertex_detection=0),
        ProbeCase(name="vd_representative", **base, vertex_detection=1),
        ProbeCase(name="vd_axis_plane", **base, vertex_detection=2),
        ProbeCase(name="vd_not_considered", **base, vertex_detection=4),
        ProbeCase(name="vd_uniform", **base, vertex_detection=5),
        ProbeCase(name="method_coarse", **base, method="coarse"),
        ProbeCase(name="auto1_8000", **base, method="auto1",
                  target_elements=8000),
        ProbeCase(name="auto1_64000", **base, method="auto1",
                  target_elements=64000),
        ProbeCase(name="ratio_out_1_0", **base, ratio_out=(1.0, 1.0, 1.0)),
        ProbeCase(name="ratio_out_1_5", **base, ratio_out=(1.5, 1.5, 1.5)),
        ProbeCase(name="std_5_0", **base, standard_length=(5.0, 5.0, 5.0)),
        ProbeCase(name="std_0_25", **base, standard_length=(0.25, 0.25,
                                                            0.25)),
        ProbeCase(name="domain_0_100",
                  domain_min=(0.0, 0.0, 0.0),
                  domain_max=(100.0, 100.0, 100.0)),
        ProbeCase(name="domain_noncube_offset",
                  domain_min=(-10.0, 20.0, -30.0),
                  domain_max=(70.0, 80.0, 60.0)),
        ProbeCase(name="part_translate_2_5", **base,
                  part_transform="1,0,0,0,0,1,0,0,0,0,1,0,2.5,2.5,2.5,1"),
        ProbeCase(name="part_translate_x_2_5", **base,
                  part_transform="1,0,0,0,0,1,0,0,0,0,1,0,2.5,0,0,1"),
        ProbeCase(name="part_translate_x_mm_2_5", **base,
                  part_transform="1,0,0,0,0,1,0,0,0,0,1,0,0.0025,0,0,1"),
        ProbeCase(name="part_rot_z45_minmax", **base, vertex_detection=3,
                  part_transform="0.7071067811865476,0.7071067811865476,0,0,"
                                 "-0.7071067811865476,0.7071067811865476,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="part_rot_z45_all", **base, vertex_detection=0,
                  part_transform="0.7071067811865476,0.7071067811865476,0,0,"
                                 "-0.7071067811865476,0.7071067811865476,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="part_rot_z30_minmax", **base,
                  part_transform="0.8660254037844387,0.5,0,0,"
                                 "-0.5,0.8660254037844387,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="part_rot_z30_rep", **base, vertex_detection=1,
                  part_transform="0.8660254037844387,0.5,0,0,"
                                 "-0.5,0.8660254037844387,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="part_rot_z30_plane", **base, vertex_detection=2,
                  part_transform="0.8660254037844387,0.5,0,0,"
                                 "-0.5,0.8660254037844387,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="part_rot_z30_all", **base, vertex_detection=0,
                  part_transform="0.8660254037844387,0.5,0,0,"
                                 "-0.5,0.8660254037844387,0,0,"
                                 "0,0,1,0,0,0,0,1"),
        ProbeCase(name="threshold_0_5", **base, vertex_detection=1,
                  threshold=(0.5, 0.5, 0.5)),
        ProbeCase(name="ratio_in_1_2", **base,
                  ratio_in=(1.2, 1.2, 1.2)),
        ProbeCase(name="edge_contact_1", **base, edge_contact=1),
        ProbeCase(name="auto3_20", **base, method="auto3",
                  target_per_axis=(20, 20, 20)),
        ProbeCase(name="divide_scale_4", **base, divide_scale=4),
        ProbeCase(name="two_parts", **base, extra_part=True),
        ProbeCase(name="stl_L_minmax", **base, stl_part=True,
                  drop_box=True, vertex_detection=3),
        ProbeCase(name="stl_L_all", **base, stl_part=True,
                  drop_box=True, vertex_detection=0),
        ProbeCase(name="stl_L_rep", **base, stl_part=True,
                  drop_box=True, vertex_detection=1),
        ProbeCase(name="stl_L_plane", **base, stl_part=True,
                  drop_box=True, vertex_detection=2),
        ProbeCase(name="stl_L_none", **base, stl_part=True,
                  drop_box=True, vertex_detection=4),
    ]
    return cases


def auto1_sweep_cases() -> list[ProbeCase]:
    """Auto1 target-element sweep + offset/domain variants."""
    base = dict(domain_min=(-25.0, -25.0, -25.0),
                domain_max=(25.0, 25.0, 25.0))
    cases = []
    for target in (1000, 2000, 4000, 8000, 16000, 32000, 64000, 100000):
        cases.append(ProbeCase(name=f"auto1_{target}", **base,
                               method="auto1", target_elements=target))
    cases.append(ProbeCase(
        name="auto1_8000_offset_x2_5", **base, method="auto1",
        target_elements=8000,
        part_transform="1,0,0,0,0,1,0,0,0,0,1,0,0.0025,0,0,1"))
    cases.append(ProbeCase(
        name="auto1_8000_domain_0_100",
        domain_min=(0.0, 0.0, 0.0), domain_max=(100.0, 100.0, 100.0),
        method="auto1", target_elements=8000))
    cases.append(ProbeCase(
        name="auto1_8000_scale_0_5", **base, method="auto1",
        target_elements=8000,
        part_transform="0.5,0,0,0,0,0.5,0,0,0,0,0.5,0,0,0,0,1"))
    cases.append(ProbeCase(
        name="auto1_8000_scale_2_0", **base, method="auto1",
        target_elements=8000,
        part_transform="2,0,0,0,0,2,0,0,0,0,2,0,0,0,0,1"))
    return cases


def tr03_vd_cases() -> list[ProbeCase]:
    """Vertex-detection matrix on the curved tr03 Impeller."""
    base = dict(base="tr03", keep_parts=("Impeller",),
                domain_min=(-20.0, -20.0, -20.0),
                domain_max=(70.0, 120.0, 120.0))
    cases = [ProbeCase(name=f"tr03_imp_vd_{i}", **base,
                       vertex_detection=i) for i in range(6)]
    cases += [
        ProbeCase(name="tr03_imp_thr_0_5", **base, vertex_detection=1,
                  threshold=(0.5, 0.5, 0.5)),
        ProbeCase(name="tr03_imp_thr_2_0", **base, vertex_detection=1,
                  threshold=(2.0, 2.0, 2.0)),
        ProbeCase(name="tr03_imp_thr_2_0_vd2", **base, vertex_detection=2,
                  threshold=(2.0, 2.0, 2.0)),
    ]
    return cases


def ex4e_vd_cases() -> list[ProbeCase]:
    """Vertex-detection matrix on ex4_e battery (solid) and speaker."""
    cases = []
    for part, dmin, dmax in (
            ("battery", (-10.0, -10.0, -10.0), (60.0, 60.0, 15.0)),
            ("speaker", (-10.0, -10.0, -10.0), (30.0, 30.0, 15.0))):
        base = dict(base="ex4e", keep_parts=(part,),
                    domain_min=dmin, domain_max=dmax)
        for vd in (0, 1, 2, 3):
            cases.append(ProbeCase(name=f"ex4e_{part}_vd{vd}", **base,
                                   vertex_detection=vd))
    cases.append(ProbeCase(
        name="ex4e_battery_thr_2_0", base="ex4e", keep_parts=("battery",),
        domain_min=(-10.0, -10.0, -10.0), domain_max=(60.0, 60.0, 15.0),
        vertex_detection=1, threshold=(2.0, 2.0, 2.0)))
    return cases


def stl_registration_cases() -> list[ProbeCase]:
    """STL part registration variants (body_files + file ref)."""
    base = dict(domain_min=(-25.0, -25.0, -25.0),
                domain_max=(25.0, 25.0, 25.0))
    return [
        ProbeCase(name="stl_L_bodyfiles", **base, stl_part=True,
                  drop_box=True, stl_body_files=True, vertex_detection=3),
        ProbeCase(name="stl_L_bodyfiles_vd1", **base, stl_part=True,
                  drop_box=True, stl_body_files=True, vertex_detection=1),
    ]


_MATRICES = {
    "default": default_cases,
    "auto1": auto1_sweep_cases,
    "tr03": tr03_vd_cases,
    "ex4e": ex4e_vd_cases,
    "stlreg": stl_registration_cases,
}


def _fresh_model(base: str = "box") -> tuple[StpreModel, CabArchive]:
    """Parse the base cab into an independent model + shared archive."""
    cab_path = _BASE_CABS.get(base, BASE_CAB)
    archive = CabArchive.parse(cab_path.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    model = StpreModel(parse_stpre(members[xml_name]))
    return model, archive


def _l_shape_stl_bytes() -> bytes:
    """Text STL of an L-shaped prism (two 10 mm boxes, notch at x/y=6)."""
    def box(x0, y0, z0, x1, y1, z1):
        v = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
        quads = [(0, 1, 2, 3), (5, 4, 7, 6), (0, 4, 5, 1),
                 (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        out = []
        for q in quads:
            out.append(f"facet normal 0 0 0\n outer loop\n"
                       f"  vertex {v[q[0]][0]:g} {v[q[0]][1]:g} "
                       f"{v[q[0]][2]:g}\n"
                       f"  vertex {v[q[1]][0]:g} {v[q[1]][1]:g} "
                       f"{v[q[1]][2]:g}\n"
                       f"  vertex {v[q[2]][0]:g} {v[q[2]][1]:g} "
                       f"{v[q[2]][2]:g}\n"
                       f" endloop\nendfacet\n")
            out.append(f"facet normal 0 0 0\n outer loop\n"
                       f"  vertex {v[q[0]][0]:g} {v[q[0]][1]:g} "
                       f"{v[q[0]][2]:g}\n"
                       f"  vertex {v[q[2]][0]:g} {v[q[2]][1]:g} "
                       f"{v[q[2]][2]:g}\n"
                       f"  vertex {v[q[3]][0]:g} {v[q[3]][1]:g} "
                       f"{v[q[3]][2]:g}\n"
                       f" endloop\nendfacet\n")
        return "".join(out)
    # L footprint: 0..10 x 0..6 y + 0..6 x 6..10 y, height 0..10 mm
    stl = ("solid lshape\n"
           + box(0, 0, 0, 10, 6, 10)
           + box(0, 6, 0, 6, 10, 10)
           + "endsolid lshape\n")
    return stl.encode("ascii")


def _apply_case(model: StpreModel, case: ProbeCase,
                archive: Optional[CabArchive] = None) -> None:
    model.ensure_domain(
        name="Domain(cuboid)",
        base=tuple(float(v) for v in case.domain_min),
        size=tuple(float(b) - float(a) for a, b in
                   zip(case.domain_min, case.domain_max)),
        unit="mm",
        material="air(incompressible/20C)",
    )
    overrides = {
        "select_vertex": str(case.vertex_detection),
        "divide_method": {"coarse": "0", "detail": "1",
                          "auto1": "2", "auto3": "3"}[case.method],
        "divide_scale": str(case.divide_scale),
        "edge_contact": str(case.edge_contact),
        "divide_ratio2": ",".join(f"{v:g}" for v in case.ratio_out),
    }
    for tag, text in overrides.items():
        model.set_mesh_control_value(tag, text)
    if case.part_transform:
        model.set_part_transform("box", case.part_transform)
    if case.extra_part:
        model.add_part(name="box2", file_ref="x_t", volume="1e-06",
                       transform=case.part_transform)
    if case.stl_part and archive is not None:
        import cab_import
        from cabxml import _first
        import xml.etree.ElementTree as ET
        raw = _l_shape_stl_bytes()
        cab_import.add_stl_member(archive, raw, name="lshape.stl")
        bodies = cab_import.import_stl_bytes(raw, name="lshape")
        if case.stl_body_files:
            # STpre-style registration: <body_files><file type="stl"> and
            # <parts><file> lshape.stl </file>
            bf = model.doc.root.find("body_files")
            if bf is None:
                bf = ET.Element("body_files")
                bf.attrib["unit"] = "m"
                bf.text = "\n   "
                bf.tail = "\n"
                model.doc.root.append(bf)
            from cabxml import _children
            if not any(c.attrib.get("type") == "stl" and
                       (c.text or "").strip() == "lshape.stl"
                       for c in _children(bf, "file")):
                e = ET.SubElement(bf, "file")
                e.attrib["type"] = "stl"
                e.text = " lshape.stl "
                e.tail = "\n   "
            cab_import.register_parts(
                model, bodies, kind="polygon")
            part_el = model.find_part("lshape")
            if part_el is not None:
                fe = _first(part_el, "file")
                if fe is not None:
                    fe.text = " lshape.stl "
        else:
            cab_import.register_parts(model, bodies, kind="polygon")
    if case.drop_box:
        model.delete_part("box")
    if case.keep_parts:
        for p in list(model.parts()):
            if p.name not in case.keep_parts:
                model.delete_part(p.name)


def _axis_metrics(vals: list[float]) -> dict:
    if len(vals) < 2:
        return {"count": len(vals), "min": None, "max": None,
                "spacing_min": None, "spacing_mean": None,
                "spacing_max": None}
    d = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return {
        "count": len(vals),
        "min": vals[0],
        "max": vals[-1],
        "spacing_min": min(d),
        "spacing_mean": sum(d) / len(d),
        "spacing_max": max(d),
    }


def _wait_stpre_gone(timeout: float = 20.0) -> bool:
    t0 = time.time()
    while cab_stpre_api._stpre_process_running():
        if time.time() - t0 > timeout:
            return False
        time.sleep(0.4)
    return True


def run_case(case: ProbeCase, workdir: Path,
             session_factory=cab_stpre_api.STpreSession) -> dict:
    """Run one probe: relay cab -> STpre COM grid/mesh -> parse output."""
    if not _wait_stpre_gone():
        raise RuntimeError("STpre process still running; refusing to probe")
    model, archive = _fresh_model(case.base)
    _apply_case(model, case, archive)
    src = workdir / f"{case.name}_in.cab"
    dst = workdir / f"{case.name}_out.cab"
    if not cab_stpre_api.build_relay_cab(
            model, archive, src, block_params=case.block_params()):
        return {"name": case.name, "ok": False,
                "error": f"relay build: {cab_stpre_api.last_error}"}

    session = session_factory()
    record = {"name": case.name, "ok": False, "input": case.input_dict()}
    t0 = time.time()
    try:
        if not session.ensure_open(src):
            record["error"] = f"open: {cab_stpre_api.last_error}"
            return record
        record["rc"] = {"open": 1}
        ok = session.grid(case.grid_params(), case.key(),
                          block_params=case.block_params())
        record["rc"]["grid"] = 1 if ok else 0
        if not ok:
            record["error"] = f"grid: {cab_stpre_api.last_error}"
            return record
        if case.do_element:
            ok = session.element()
            record["rc"]["element"] = 1 if ok else 0
            if not ok:
                record["error"] = f"element: {cab_stpre_api.last_error}"
                return record
        if not session.save(dst):
            record["error"] = f"save: {cab_stpre_api.last_error}"
            return record
        record["rc"]["save"] = 1
        record["duration_s"] = round(time.time() - t0, 2)
        record["ok"] = True
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        session.close()
    if not record.get("ok"):
        return record

    try:
        out_arch = CabArchive.parse(dst.read_bytes())
        out_arch.fill_member_data()
        members = {m.name: m.data for m in out_arch.members}
        xml_name = next(n for n in members if n.endswith(".xml")
                        and not n.startswith("_"))
        out_model = StpreModel(parse_stpre(members[xml_name]))
        axes = out_model.mesh_axes()
        record["output"] = {
            "mesh_block_min": out_model.root_block_bounds()[:3]
            if out_model.root_block_bounds() else None,
            "mesh_block_max": out_model.root_block_bounds()[3:]
            if out_model.root_block_bounds() else None,
            "axes": {ax: list(v) for ax, v in axes.items()},
            "axis_metrics": {ax: _axis_metrics(axes.get(ax, []))
                             for ax in "xyz"},
            "part_boxes": {p.name: out_model.part_boxes(p.name)
                           for p in out_model.parts()},
            "elements": out_model.elements() is not None,
            "mesh_control": {
                tag: out_model.mesh_control_value(tag)
                for tag in ("select_vertex", "divide_method",
                            "divide_scale", "edge_contact",
                            "divide_ratio2", "grid", "element_max")
            },
        }
    except Exception as exc:
        record["ok"] = False
        record["error"] = f"parse output: {type(exc).__name__}: {exc}"
    return record


def _uniform_hypothesis(vals: list[float], tol: float = 1e-9) -> dict:
    if len(vals) < 3:
        return {"uniform": False, "reason": "too few points"}
    d = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    d0 = d[0]
    uniform = all(abs(x - d0) <= tol * max(1.0, abs(d0)) for x in d)
    return {"uniform": uniform, "spacing": d0}


def analyze(records: list[dict]) -> dict:
    """First-pass rule mining over the recorded outputs."""
    summary = []
    for r in records:
        if not r.get("ok"):
            summary.append({"name": r["name"], "ok": False,
                            "error": r.get("error")})
            continue
        out = r["output"]
        axes = out["axes"]
        row = {
            "name": r["name"],
            "counts": [out["axis_metrics"][a]["count"] for a in "xyz"],
            "domain_min": r["input"]["domain_min"],
            "domain_max": r["input"]["domain_max"],
            "uniform": {a: _uniform_hypothesis(axes[a]) for a in "xyz"},
            "spacing_min": [out["axis_metrics"][a]["spacing_min"]
                            for a in "xyz"],
            "spacing_max": [out["axis_metrics"][a]["spacing_max"]
                            for a in "xyz"],
            "box_boxes": out["part_boxes"].get("box", []),
        }
        summary.append(row)
    return {"cases": summary}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default="",
                    help="comma list of case names (default: all)")
    ap.add_argument("--matrix", default="default",
                    choices=sorted(_MATRICES),
                    help="case matrix to run (default|auto1|tr03|ex4e|stlreg)")
    ap.add_argument("--out", default="",
                    help="output JSON path (default data/stpre_probe_<ts>)")
    ap.add_argument("--analyze", metavar="JSON",
                    help="analyze an existing probe JSON")
    args = ap.parse_args()

    if args.analyze:
        data = json.loads(Path(args.analyze).read_text(encoding="utf-8"))
        print(json.dumps(analyze(data["records"]), ensure_ascii=False,
                         indent=2))
        return

    if not BASE_CAB.is_file():
        raise SystemExit(f"missing base project: {BASE_CAB}")
    if not cab_stpre_api.api_available():
        raise SystemExit("STpre COM ProgID not registered")
    if cab_stpre_api._stpre_process_running():
        raise SystemExit(
            "STpre is already running; close it before probing "
            "(ownership guard refuses to attach).")

    cases = _MATRICES[args.matrix]()
    if args.cases:
        wanted = {s.strip() for s in args.cases.split(",") if s.strip()}
        cases = [c for c in cases if c.name in wanted]
    if not cases:
        raise SystemExit("no cases selected")

    DATA_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else (
        DATA_DIR / f"stpre_probe_{time.strftime('%Y%m%d_%H%M%S')}.json")
    workdir = Path(tempfile.mkdtemp(prefix="stpre_probe_"))
    records = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.name} ...", flush=True)
        try:
            rec = run_case(case, workdir)
        except Exception as exc:
            import traceback
            rec = {
                "name": case.name,
                "ok": False,
                "input": case.input_dict(),
                "error": f"harness: {type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        status = "OK" if rec.get("ok") else f"FAIL: {rec.get('error')}"
        if rec.get("ok"):
            m = rec["output"]["axis_metrics"]
            status += (f"  grid {m['x']['count']}x{m['y']['count']}"
                       f"x{m['z']['count']} "
                       f"({rec['duration_s']} s)")
        print("   " + status)
        records.append(rec)
        payload = {
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_project": str(BASE_CAB),
            "stpre_progid": cab_stpre_api.PROGID,
            "records": records,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8")
    ok_n = sum(1 for r in records if r.get("ok"))
    print(f"\n{ok_n}/{len(records)} cases OK -> {out_path}")
    if ok_n:
        print(json.dumps(analyze(records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
