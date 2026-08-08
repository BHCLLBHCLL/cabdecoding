"""STpre VB/COM automation bridge for gridding and meshing.

Reference: ``Manuals/ST/HTML/VB_Interface_eng``:

* Application: ``CreateObject("STpre_Bx64net.Application.2025")``,
  ``GetDocument``, ``Visible``, ``Quit``;
* Doc: ``OpenCabFile(path)``, ``SaveCabFile(path)``, ``GetMesher``;
* Mesher: ``SetGridParam(key, p1, p2, p3)``, ``ExecuteGrid(key, flag)``,
  ``ExecuteElement``.

The bridge is file-relay based: cab_gui writes the current project to a
temporary CAB, STpre (automated via COM) opens it, runs gridding/element
division, saves another CAB, and cab_gui merges the mesh sections back into
its in-memory model.  Default off; cab_gui keeps its native implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

PROGID = "STpre_Bx64net.Application.2025"
last_error: Optional[str] = None
_TEMPLATE = Path(__file__).resolve().parent / "data" / "stpre_template.xml"

_DIVISION_METHOD = {
    "coarse": "coarse",
    "rough_only": "coarse",
    "detail": "detail",
    "rough_and_detail": "detail",
    "auto1": "auto1",
    "num_elements": "auto1",
    "auto3": "auto3",
}

_DIVISION_TYPE = {
    0: "all", 1: "main", 2: "plane", 3: "minmax",
    4: "none", 5: "uniform",
}


def api_available() -> bool:
    """True when the STpre COM ProgID is registered on this machine."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROGID):
            return True
    except Exception:
        return False


def _stpre_process_running() -> bool:
    """True when an STpre process is already running.

    STpre is a single-instance COM server: ``Dispatch(PROGID)`` returns the
    object of an already-running instance instead of starting a private one.
    If that instance belongs to the user (an open STpre window), hiding it
    (``Visible=False``) or quitting it (``Quit``) would destroy the user's
    session.  Automation therefore refuses to attach while any STpre
    process is alive; the GUI falls back to the native gridding/meshing.
    """
    import subprocess
    names = ("STpre_Bx64net.exe", "STprePMesh_Bx64net.exe")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for name in names:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=flags).stdout
        except Exception:
            continue
        if name.lower() in (out or "").lower():
            return True
    try:
        import win32com.client
        win32com.client.GetActiveObject(PROGID)
        return True
    except Exception:
        return False


def _invoke(obj, name: str, *args):
    """Call a COM member, flagging it as a method first.

    STpre's automation interface (like scPOST) requires ``_FlagAsMethod``
    before invoking members that take no arguments or only VARIANT
    arguments; otherwise win32com raises DISP_E_MEMBERNOTFOUND
    (-2147352573, "找不到成员。") for some members.
    """
    obj._FlagAsMethod(name)
    return getattr(obj, name)(*args)


def build_grid_params(model, *, method: Optional[str] = None,
                      division_type: Optional[int] = None,
                      target_elements: Optional[int] = None,
                      target_per_axis: Optional[tuple[int, int, int]] = None,
                      outer_ratio: Optional[tuple[float, float, float]] = None,
                      edge_contact: Optional[int] = None,
                      max_elements: Optional[int] = None
                      ) -> list[tuple[str, str, str, str]]:
    """Map cab model mesh_control values to ``SetGridParam`` tuples."""
    def mc(tag, default=""):
        try:
            return model.mesh_control_value(tag) or default
        except Exception:
            return default
    method = method or _DIVISION_METHOD.get(mc("divide_method", "1"),
                                            "detail")
    if method not in _DIVISION_METHOD:
        method = "detail"
    key = _DIVISION_METHOD[method]
    vd = division_type
    if vd is None:
        try:
            vd = int(mc("select_vertex", "1"))
        except ValueError:
            vd = 1
    vd_key = _DIVISION_TYPE.get(vd, "main")
    params: list[tuple[str, str, str, str]] = [
        ("division_method", key, "", ""),
        ("division_type", vd_key, "", ""),
    ]
    if key == "auto1" and target_elements is not None:
        params.append(("division_num", int(target_elements), 0, 0))
    elif key == "auto3" and target_per_axis is not None:
        params.append(("division_num", *(int(v) for v in target_per_axis)))
    if outer_ratio is None:
        try:
            vals = [float(x) for x in mc("divide_ratio2", "1.2,1.2,1.2")
                    .split(",")[:3]]
        except ValueError:
            vals = [1.2, 1.2, 1.2]
        outer_ratio = tuple(vals)
    params.append(("outer_ratio", *(float(v) for v in outer_ratio)))
    if edge_contact is None:
        edge_contact = 1 if mc("edge_contact", "0") == "1" else 0
    params.append(("edge_contact", int(edge_contact), "", ""))
    if max_elements is not None:
        params.append(("max_elements", int(max_elements), "", ""))
    return params


def _as3(v, default: float = 1.0) -> tuple[float, float, float]:
    if isinstance(v, (int, float)):
        return (float(v), float(v), float(v))
    try:
        vals = [float(x) for x in v[:3]]
        while len(vals) < 3:
            vals.append(default)
        return (vals[0], vals[1], vals[2])
    except Exception:
        return (default, default, default)


def _parse_vec3_text(text: str, default: float = 1.0
                     ) -> tuple[float, float, float]:
    try:
        vals = [float(x.strip()) for x in (text or "").split(",")[:3]]
        while len(vals) < 3:
            vals.append(default)
        return (vals[0], vals[1], vals[2])
    except Exception:
        return (default, default, default)


def build_block_params_from_gridspec(spec
                                     ) -> list[tuple[str, float, float, float]]:
    """RootBlock ``SetParam`` tuples (VB MeshBlock): length / ratio / limit.

    STpre Sample_3: ``blk.SetParam "length"|"ratio"|"limit", x, y, z`` —
    these are *not* Mesher.SetGridParam keys.
    """
    length = _as3(getattr(spec, "standard_length", 0.5), 0.5)
    ratio = _as3(spec.ratio_internal() if hasattr(spec, "ratio_internal")
                 else getattr(spec, "geometric_ratio", 1.0), 1.0)
    limit = _as3(getattr(spec, "threshold_length", 0.1), 0.1)
    return [
        ("length", *length),
        ("ratio", *ratio),
        ("limit", *limit),
    ]


def build_block_params_from_model(model
                                  ) -> list[tuple[str, float, float, float]]:
    """Read RootBlock division params from XML for SetParam / relay."""
    from cabxml import _first
    length = (1.0, 1.0, 1.0)
    ratio = (1.0, 1.0, 1.0)
    limit = (0.1, 0.1, 0.1)
    mb = _first(model.root, "mesh_block")
    if mb is not None:
        el = _first(mb, "divide_length")
        if el is not None and el.text:
            length = _parse_vec3_text(el.text, 1.0)
        el = _first(mb, "divide_ratio1")
        if el is not None and el.text:
            ratio = _parse_vec3_text(el.text, 1.0)
        el = _first(mb, "limit")
        if el is not None and el.text:
            limit = _parse_vec3_text(el.text, 0.1)
    mc = _first(model.root, "mesh_control")
    block = _first(mc, "block") if mc is not None else None
    if block is not None:
        el = _first(block, "limit")
        if el is not None and el.text:
            limit = _parse_vec3_text(el.text, 0.1)
    # Prefer mesh_control divide_ratio2 only when mesh_block ratio missing
    if mb is None or _first(mb, "divide_ratio1") is None:
        try:
            text = model.mesh_control_value("divide_ratio2") or ""
            if text.strip():
                ratio = _parse_vec3_text(text, 1.0)
        except Exception:
            pass
    return [
        ("length", *length),
        ("ratio", *ratio),
        ("limit", *limit),
    ]


def build_params_from_gridspec(spec, *, edge_contact: Optional[int] = None
                               ) -> list[tuple[str, str, str, str]]:
    """Map a native ``GridSpec`` (Mesh:Set Division dialog) to
    ``SetGridParam`` tuples, so STpre API gridding uses the dialog settings.

    Standard length / internal ratio / threshold are *not* SetGridParam
    keys — use :func:`build_block_params_from_gridspec` + MeshBlock.SetParam.
    """
    vd_map = {
        "all": "all", "representative": "main", "axis_plane": "plane",
        "minmax": "minmax", "not_considered": "none", "uniform": "uniform",
    }
    vd = vd_map.get(getattr(spec, "vertex_detection", "representative"),
                    "main")
    if getattr(spec, "method", "rough_and_detail") == "num_elements" \
            and getattr(spec, "target_per_axis", None) is not None:
        method = "auto3"
    else:
        method = {
            "rough_only": "coarse",
            "rough_and_detail": "detail",
            "num_elements": "auto1",
        }.get(getattr(spec, "method", "rough_and_detail"), "detail")
    params: list[tuple[str, str, str, str]] = [
        ("division_method", method, "", ""),
        ("division_type", vd, "", ""),
    ]
    if method == "auto1" and getattr(spec, "target_elements", None):
        params.append(("division_num", int(spec.target_elements), 0, 0))
    elif method == "auto3" and getattr(spec, "target_per_axis", None):
        params.append(("division_num",
                       *(int(v) for v in spec.target_per_axis)))
    params.append(("outer_ratio", *spec.ratio_external()))
    params.append(("edge_contact",
                   int(1 if edge_contact else 0), "", ""))
    return params


def _set_xml_vec(parent, tag: str, vals, *, unit: Optional[str] = None
                 ) -> None:
    import xml.etree.ElementTree as ET
    from cabxml import _first
    el = _first(parent, tag)
    if el is None:
        el = ET.SubElement(parent, tag)
        el.tail = "\n      "
    el.text = " " + ",".join(f"{float(v):.17g}" for v in vals) + " "
    if unit is not None:
        el.attrib["unit"] = unit


def apply_block_params_to_xml(root, block_params,
                              *, outer_ratio=None,
                              select_vertex: Optional[int] = None,
                              divide_method: Optional[int] = None) -> None:
    """Write length/ratio/limit into relay ``mesh_control`` / ``mesh_block``."""
    import xml.etree.ElementTree as ET
    from cabxml import _first
    d = {p[0]: p[1:4] for p in (block_params or [])}
    length = d.get("length")
    ratio = d.get("ratio")
    limit = d.get("limit")
    mc = root.find("mesh_control")
    mb = root.find("mesh_block")
    if mb is not None:
        if length is not None:
            _set_xml_vec(mb, "divide_length", length, unit="mm")
        if ratio is not None:
            _set_xml_vec(mb, "divide_ratio1", ratio)
        if limit is not None:
            _set_xml_vec(mb, "limit", limit, unit="mm")
    if mc is not None:
        block = _first(mc, "block")
        if block is not None and limit is not None:
            _set_xml_vec(block, "limit", limit, unit="mm")
        if outer_ratio is not None:
            _set_xml_vec(mc, "divide_ratio2", outer_ratio)
        if select_vertex is not None:
            el = _first(mc, "select_vertex")
            if el is None:
                el = ET.SubElement(mc, "select_vertex")
                el.tail = "\n   "
            el.text = f" {int(select_vertex)} "
        if divide_method is not None:
            el = _first(mc, "divide_method")
            if el is None:
                el = ET.SubElement(mc, "divide_method")
                el.tail = "\n   "
            el.text = f" {int(divide_method)} "


def build_relay_cab(model, archive, src_path: str | Path, *,
                    keep_mesh: bool = False,
                    block_params: Optional[list] = None,
                    grid_spec=None) -> bool:
    """Write the temp CAB relay from an official STpre XML template.

    STpre rejects minimal project XML (OpenCabFile returns 0), so the relay
    uses the full official ex4_e XML structure with the current project's
    domain / parts / body_files merged in; the mesh sections are regenerated
    by STpre itself.

    ``block_params`` / ``grid_spec`` write dialog Standard length, threshold
    and internal ratio into the relay so ExecuteGrid does not keep the
    template's ``divide_length=1``.
    """
    global last_error
    import xml.etree.ElementTree as ET
    from cabxml import StpreModel, _first, parse_stpre
    if not _TEMPLATE.is_file():
        last_error = "missing data/stpre_template.xml"
        return False
    template = StpreModel(parse_stpre(_TEMPLATE.read_bytes()))
    root = template.doc.root
    for tag in ("group", "parts", "analysis_region", "body_files"):
        el = root.find(tag)
        if el is not None:
            root.remove(el)
    if not keep_mesh:
        old_element = root.find("element")
        if old_element is not None:
            root.remove(old_element)
    src_root = model.doc.root
    for tag in ("analysis_region", "body_files"):
        el = src_root.find(tag)
        if el is not None:
            root.append(ET.fromstring(ET.tostring(el)))
    for el in list(src_root):
        if el.tag in ("group", "parts"):
            root.append(ET.fromstring(ET.tostring(el)))
    # sync RootBlock / mesh_block range to the current computational domain
    base = model.domain_base()
    size = model.domain_size()
    if base is not None and size is not None:
        dmin = ",".join(f"{v:.17g}" for v in base)
        dmax = ",".join(f"{v:.17g}" for v in
                        (base[0] + size[0], base[1] + size[1],
                         base[2] + size[2]))
        for sec in ("mesh_control", "mesh_block"):
            sec_el = root.find(sec)
            if sec_el is None:
                continue
            # RootBlock <min>/<max> AND <subblock><area><min>/<max> must
            # all match the domain; STpre grids over the area range.
            for el in sec_el.iter("min"):
                el.text = f" {dmin} "
                el.attrib["unit"] = "mm"
            for el in sec_el.iter("max"):
                el.text = f" {dmax} "
                el.attrib["unit"] = "mm"
            grid = sec_el.find(".//grid")
            if grid is not None:
                grid.text = " 2,2,2 "
            # force STpre to regenerate the coordinate tables: remove the
            # template's x/y/z points from mesh_block (ExecuteGrid otherwise
            # keeps the old coordinates even when min/max are updated).
            if sec == "mesh_block" and not keep_mesh:
                for ax in ("x", "y", "z"):
                    el = sec_el.find(ax)
                    if el is not None:
                        sec_el.remove(el)
    # Dialog / model division params (Standard length etc.)
    if block_params is None and grid_spec is not None:
        block_params = build_block_params_from_gridspec(grid_spec)
    if block_params is None:
        block_params = build_block_params_from_model(model)
    outer = None
    det_idx = None
    method_idx = None
    if grid_spec is not None:
        outer = grid_spec.ratio_external()
        try:
            from cab_grid import detection_index, method_index
            det_idx = detection_index(grid_spec)
            method_idx = method_index(grid_spec)
        except Exception:
            pass
    apply_block_params_to_xml(
        root, block_params, outer_ratio=outer,
        select_vertex=det_idx, divide_method=method_idx)
    if keep_mesh:
        # carry the current generated mesh into the relay (element-only run)
        for sec in ("mesh_block", "element"):
            old = root.find(sec)
            src_el = src_root.find(sec)
            if old is not None:
                root.remove(old)
            if src_el is not None:
                root.append(ET.fromstring(ET.tostring(src_el)))
    prop_member = next((m for m in archive.members
                        if m.name.endswith("_property.xml")), None)
    if prop_member is not None:
        pdb = _first(root, "property_db")
        if pdb is not None:
            f = _first(pdb, "file")
            if f is not None:
                f.text = f" {prop_member.name} "
    xml_bytes = template.doc.serialize()
    for m in archive.members:
        if m.name.endswith(".xml") and not m.name.startswith("_"):
            m.data = xml_bytes
            break
    Path(src_path).write_bytes(archive.to_bytes(preserve_source_blocks=False))
    last_error = None
    return True


class STpreSession:
    """Reusable STpre COM session (start once, grid/mesh repeatedly)."""

    def __init__(self):
        self._app = None
        self._doc = None
        self._mesher = None
        self._cab_in: Optional[str] = None
        # False when the COM object is a pre-existing STpre instance the
        # user may be watching.  Only self-started instances are hidden
        # (Visible=False) and terminated (Quit); attached ones are never
        # touched beyond the automation calls themselves.
        self._owned = False

    def ensure_open(self, cab_in: str | Path) -> bool:
        global last_error
        cab_in = str(cab_in)
        if self._app is None:
            if _stpre_process_running():
                last_error = (
                    "STpre is already running; refusing to attach "
                    "(automation would hide/quit the user's instance)")
                return False
            return self._start(cab_in)
        if self._cab_in == cab_in:
            return True
        # A later [Gridding]/[Meshing] click writes a *new* relay CAB, so
        # re-open it in the same STpre process.  If the running build does
        # not accept a second OpenCabFile, restart once instead of leaving
        # the stale project open.
        rc = _invoke(self._doc, "OpenCabFile", cab_in)
        if rc == 1:
            self._mesher = _invoke(self._doc, "GetMesher")
            self._cab_in = cab_in
            last_error = None
            return True
        self.close()
        last_error = f"reopen OpenCabFile rc={rc}; restarted session"
        return self._start(cab_in)

    def _start(self, cab_in: str) -> bool:
        """Start a private, hidden STpre instance and open the relay."""
        global last_error
        import win32com.client
        app = win32com.client.Dispatch(PROGID)
        self._owned = True
        app.Visible = False
        doc = _invoke(app, "GetDocument")
        rc = _invoke(doc, "OpenCabFile", cab_in)
        if rc != 1:
            last_error = f"OpenCabFile rc={rc}"
            if self._owned:
                try:
                    _invoke(app, "Quit")
                except Exception:
                    pass
            return False
        self._app = app
        self._doc = doc
        self._mesher = _invoke(doc, "GetMesher")
        self._cab_in = cab_in
        last_error = None
        return True

    @property
    def is_open(self) -> bool:
        return self._app is not None

    def grid(self, params, method: str = "detail",
             block_params: Optional[list] = None) -> bool:
        """SetGridParam + RootBlock SetParam(length/ratio/limit) + ExecuteGrid.

        VB Sample_3: ``mesh.GetBlock("root").SetParam "length", ...`` before
        ``ExecuteGrid``.  Without SetParam, STpre keeps template
        ``divide_length=1`` and ignores the Mesh:Set division Standard length.
        """
        global last_error
        if block_params:
            try:
                blk = _invoke(self._mesher, "GetBlock", "root")
            except Exception as exc:
                last_error = f"GetBlock(root): {exc}"
                return False
            for key, p1, p2, p3 in block_params:
                rc = _invoke(blk, "SetParam", key, p1, p2, p3)
                if rc != 1:
                    last_error = f"SetParam({key}) rc={rc}"
                    return False
        for key, p1, p2, p3 in params:
            rc = _invoke(self._mesher, "SetGridParam", key, p1, p2, p3)
            if rc != 1:
                last_error = f"SetGridParam({key}) rc={rc}"
                return False
        rc = _invoke(self._mesher, "ExecuteGrid", method, "T")
        if rc != 1:
            last_error = f"ExecuteGrid({method}) rc={rc}"
            return False
        return True

    def element(self) -> bool:
        global last_error
        rc = _invoke(self._mesher, "ExecuteElement")
        if rc != 1:
            last_error = f"ExecuteElement rc={rc}"
            return False
        return True

    def save(self, cab_out: str | Path) -> bool:
        global last_error
        rc = _invoke(self._doc, "SaveCabFile", str(cab_out))
        if rc != 1:
            last_error = f"SaveCabFile rc={rc}"
            return False
        return True

    def close(self) -> None:
        if self._app is not None:
            if self._owned:
                try:
                    _invoke(self._app, "Quit")
                except Exception:
                    pass
            self._app = None
            self._doc = None
            self._mesher = None
            self._cab_in = None
            self._owned = False


def run_stpre_grid_mesh(cab_in: str | Path, cab_out: str | Path, *,
                        method: str = "detail",
                        division_type: str = "all",
                        grid_params: Optional[list[tuple]] = None,
                        block_params: Optional[list[tuple]] = None,
                        run_element: bool = True) -> bool:
    """Launch STpre through COM and execute gridding (+ element division).

    Returns True when the output CAB was saved.  File paths are the relay
    between cab_gui's memory model and the external STpre process.
    """
    global last_error
    session = STpreSession()
    try:
        if not session.ensure_open(cab_in):
            return False
        params = grid_params if grid_params is not None else [
            ("division_method", method, "", ""),
            ("division_type", division_type, "", ""),
        ]
        if not session.grid(params, method, block_params=block_params):
            return False
        if run_element and not session.element():
            return False
        if not session.save(cab_out):
            return False
        last_error = None
        return True
    finally:
        session.close()


def merge_mesh_result(model, out_model) -> list[str]:
    """Merge mesh sections from the STpre output into the in-memory model.

    Copies ``mesh_control`` / ``mesh_block`` / ``element`` (and the domain,
    if STpre adjusted it).  Returns the merged section names.
    """
    import xml.etree.ElementTree as ET
    merged = []
    for tag in ("mesh_control", "mesh_block", "element", "analysis_region"):
        new = out_model.doc.root.find(tag)
        if new is None:
            continue
        old = model.doc.root.find(tag)
        if old is not None:
            model.doc.root.remove(old)
        model.doc.root.append(ET.fromstring(ET.tostring(new)))
        merged.append(tag)
    return merged
