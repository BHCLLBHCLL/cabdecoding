"""STpre VB/COM automation bridge — full class-hierarchy coverage + headless fallback.

Reference: ``Manuals/ST/HTML/VB_Interface_eng``.  ProgID:
``STpre_Bx64net.Application.2025``.  Class hierarchy (all late-bound, any
member callable via :meth:`ComObject.call`):

    Application                              (CreateObject / GetObject, Visible, Quit)
      `- GetDocument -> Doc                   (OpenCabFile/SaveCabFile/SaveSFile/SaveNfbFile,
          |                                     Intersect/Subtract/Unite/Section,
          |                                     Create*Model / Create*Property / Create*Value,
          |                                     Get*/Set* analysis params, GetMesher/GetSketcher)
          |- GetMesher -> Mesher               (SetGridParam/ExecuteGrid/ExecuteElement, GetBlock)
          |    `- GetBlock/GetRootBlock -> MeshBlock (SetParam/SetRange/GetDivideArray)
          |- GetModel/GetAllModelArray -> Model (Copy/Rotate/Transform/GetBoundingBox/SaveXtFile)
          |- GetValue/GetAllValueArray -> Value (SetParam/GetParam, condition write-back)
          |- GetPropertyEntity -> Property     (Create*Material/Create*Property)
          `- GetTable -> Table, GetSketcher -> Sketch, CreateScript/Expression/UserFunction

This module keeps the original file-relay gridding/meshing bridge (used by
cab_gui and stpre_probe) and adds:

* a generic :class:`ComObject` wrapper whose :meth:`ComObject.call` does the
  ``_FlagAsMethod`` dance (scPOST manual "VB interface usage in Python") so
  the *entire* VB surface is reachable without pre-writing a wrapper;
* typed wrappers :class:`STpreApplication`, :class:`STpreDoc`, :class:`STpreModel`,
  :class:`STpreMesher`, :class:`STpreMeshBlock`, :class:`STpreValue` for the
  high-value members;
* :class:`STpreSession` now *attaches* to an already-running STpre by default
  (``attach=True``) instead of refusing — the old safety policy is unfrozen,
  while the ownership guard (never ``Visible=False`` / ``Quit`` a user-open
  instance) is preserved via ``_owned``.
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
    session.  ``STpreSession`` now *attaches* by default (``attach=True``)
    and simply never hides/quits an attached instance (``_owned=False``);
    the legacy ``attach=False`` path still refuses while any STpre process
    is alive.
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

    def __init__(self, *, attach: bool = True, headless: bool = True):
        self._app = None
        self._doc = None
        self._mesher = None
        self._cab_in: Optional[str] = None
        # attach=True (unfrozen policy): attach to an already-running STpre
        # via GetActiveObject and drive it, without hiding/quoting it.
        # attach=False keeps the legacy "refuse while STpre is running".
        self._attach = attach
        self._headless = headless
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
                if not self._attach:
                    last_error = (
                        "STpre is already running; attach=False refuses "
                        "(set attach=True to drive the running instance)")
                    return False
                return self._attach_start(cab_in)
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
        """Start a private STpre instance (hidden when headless) and open.

        ``DispatchEx`` starts a fresh instance; ``Dispatch`` returns a
        running one for this single-instance server (scPOST manual note).
        """
        global last_error
        import win32com.client
        app = win32com.client.Dispatch(PROGID)
        self._owned = True
        if self._headless:
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

    def _attach_start(self, cab_in: str) -> bool:
        """Attach to an already-running STpre (GetActiveObject) and open.

        The attached instance is *never* hidden or quit (``_owned=False``);
        only ``OpenCabFile`` and the automation calls themselves run.
        """
        global last_error
        import win32com.client
        try:
            app = win32com.client.GetActiveObject(PROGID)
        except Exception:
            app = win32com.client.Dispatch(PROGID)  # single-instance fallback
        self._owned = False
        doc = _invoke(app, "GetDocument")
        rc = _invoke(doc, "OpenCabFile", cab_in)
        if rc != 1:
            last_error = f"attach OpenCabFile rc={rc}"
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

    @property
    def application(self):
        """The wrapped :class:`STpreApplication` (or None before open)."""
        return STpreApplication(self._app) if self._app is not None else None

    @property
    def doc(self):
        """The wrapped :class:`STpreDoc` (or None before open)."""
        return STpreDoc(self._doc) if self._doc is not None else None

    @property
    def mesher(self):
        """The wrapped :class:`STpreMesher` (or None before open)."""
        return STpreMesher(self._mesher) if self._mesher is not None else None

    def model(self, name: str):
        """``Doc.GetModel(name)`` -> :class:`STpreModel`."""
        if self._doc is None:
            return None
        return STpreModel(_invoke(self._doc, "GetModel", name))

    def value(self, name: str):
        """``Doc.GetValue(name)`` -> :class:`STpreValue`."""
        if self._doc is None:
            return None
        return STpreValue(_invoke(self._doc, "GetValue", name))

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

# ============================================================================
# Class-hierarchy wrappers (late-bound, full VB/COM coverage)
# ============================================================================


class ComObject:
    """Generic late-bound COM wrapper.

    win32com dynamic dispatch needs ``_FlagAsMethod(name)`` before calling a
    member with *no* arguments or *only* VARIANT arguments (scPOST manual
    "VB interface usage in Python").  :meth:`call` does this transparently
    so **any** member in the manual's class lists is reachable without a
    pre-written typed wrapper.  Attribute access reads COM properties;
    :meth:`set_prop` writes them.
    """

    def __init__(self, obj):
        self._obj = obj

    @property
    def raw(self):
        """The underlying win32com dispatch object."""
        return self._obj

    def call(self, name: str, *args):
        """Invoke ``name`` as a COM *method* (``_FlagAsMethod`` first)."""
        return _invoke(self._obj, name, *args)

    def prop(self, name: str, default=None):
        """Read a COM *property* (returns ``default`` on failure)."""
        try:
            return getattr(self._obj, name)
        except Exception:
            return default

    def set_prop(self, name: str, value) -> None:
        """Write a COM *property*."""
        setattr(self._obj, name, value)

    def __repr__(self):
        return f"<{type(self).__name__} {self._obj!r}>"


class STpreSketch(ComObject):
    """Sketch class (Doc.GetSketcher). VB_Interface Sketch_Class methods."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetClose(self):
        return self.call("GetClose")

    def SetClose(self, flag):
        return self.call("SetClose", flag)

    def GetSystem(self):
        return self.call("GetSystem")

    def SetSystem(self, origin_uvw):
        return self.call("SetSystem", origin_uvw)

    def GetTarget(self):
        return self.call("GetTarget")

    def SetTarget(self, name):
        return self.call("SetTarget", name)

    def GetVertex(self, index):
        return self.call("GetVertex", index)

    def SetVertex(self, *args):
        return self.call("SetVertex", *args)

    def GetVertexKind(self, index):
        return self.call("GetVertexKind", index)

    def SetCircle(self, *args):
        return self.call("SetCircle", *args)

    def SetRectangle(self, *args):
        return self.call("SetRectangle", *args)

    def SetSide(self, direction):
        return self.call("SetSide", direction)


class STpreProperty(ComObject):
    """Property / PropertyGroup (Doc.GetPropertyEntity)."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetName(self):
        return self.call("GetName")

    def GetTypeString(self):
        return self.call("GetTypeString")

    def GetKind(self, key):
        return self.call("GetKind", key)

    def Get(self, key):
        return self.call("Get", key)

    def Set(self, key, value):
        return self.call("Set", key, value)

    def GetNum(self):
        return self.call("GetNum")

    def SetNum(self, n):
        return self.call("SetNum", n)

    def GetData(self, index):
        return self.call("GetData", index)

    def SetData(self, index, data):
        return self.call("SetData", index, data)

    def GetRadField(self):
        return self.call("GetRadField")

    def SetRadField(self, flag):
        return self.call("SetRadField", flag)

    def GetTable(self, key):
        return STpreTable(self.call("GetTable", key))

    def SetTable(self, key, table):
        return self.call("SetTable", key, table)

    def GetExpression(self, key):
        return self.call("GetExpression", key)

    def SetExpression(self, key, expr):
        return self.call("SetExpression", key, expr)

    def GetScript(self, key):
        return self.call("GetScript", key)

    def SetScript(self, key, script):
        return self.call("SetScript", key, script)

    def GetUserFunction(self, key):
        return self.call("GetUserFunction", key)

    def SetUserFunction(self, key, fn):
        return self.call("SetUserFunction", key, fn)

    def CreateEntity(self, name):
        return STpreProperty(self.call("CreateEntity", name))

    def DeleteEntity(self, name):
        return self.call("DeleteEntity", name)

    def GetEntities(self):
        return [STpreProperty(p) for p in (self.call("GetEntities") or [])]


class STpreTable(ComObject):
    """Table class (Doc.GetTable / Value.GetTable)."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetName(self):
        return self.call("GetName")

    def SetName(self, name):
        return self.call("SetName", name)

    def GetNum(self):
        return self.call("GetNum")

    def GetTypeString(self):
        return self.call("GetTypeString")

    def SetType(self, type_):
        return self.call("SetType", type_)

    def GetData(self, index):
        return self.call("GetData", index)

    def SetData(self, index, value):
        return self.call("SetData", index, value)

    def GetXUnit(self):
        return self.call("GetXUnit")

    def GetYUnit(self):
        return self.call("GetYUnit")

    def SetUnit(self, x_unit, y_unit):
        return self.call("SetUnit", x_unit, y_unit)

    def GetTableCondParam(self, key):
        return self.call("GetTableCondParam", key)

    def SetTableCondParam(self, key, value):
        return self.call("SetTableCondParam", key, value)


def pack_set_param(key, *values, slots: int = 3):
    """Pad Value.SetParam extras with 0 (VB_Interface; unused slots are 0).

    SetParam(key, v1[, v2[, v3]]) — extra components default to 0.
    SetParam3(v1, v2, v3) is the 3-component form (no key).
    """
    vals = list(values) + [0] * max(0, slots - len(values))
    return (key, *vals[:slots])


class STpreApplication(ComObject):
    """Application class (``CreateObject`` / ``GetObject``)."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    @property
    def Visible(self):
        return self.prop("Visible")

    @Visible.setter
    def Visible(self, value):
        self.set_prop("Visible", value)

    @property
    def UserControl(self):
        return self.prop("UserControl")

    @UserControl.setter
    def UserControl(self, value):
        self.set_prop("UserControl", value)

    def GetDocument(self):
        return STpreDoc(self.call("GetDocument"))

    def GetVersionNo(self):
        return self.call("GetVersionNo")

    def GetProcessID(self):
        return self.call("GetProcessID")

    def GetHomeFolder(self):
        return self.call("GetHomeFolder")

    def GetEnvFilePath(self):
        return self.call("GetEnvFilePath")

    def GetFileVersion(self):
        return self.call("GetFileVersion")

    def ClearDocument(self):
        return self.call("ClearDocument")

    def BeginViewerMode(self):
        return self.call("BeginViewerMode")

    def IsViewerMode(self):
        return self.call("IsViewerMode")

    def UpdateAll(self):
        return self.call("UpdateAll")

    def Quit(self):
        return self.call("Quit")


class STpreDoc(ComObject):
    """Doc class — owns all Create*Model / Save* / Open* / Boolean / conditions.

    Full method list (459 members) in ``Manuals/ST/HTML/VB_Interface_eng``
    ``St_vb_Preprocessor_Doc_Class.html``; any member is reachable via
    :meth:`ComObject.call`.
    """

    # -- open / save / export -------------------------------------------
    def OpenCabFile(self, path):
        return self.call("OpenCabFile", str(path))

    def SaveCabFile(self, path):
        return self.call("SaveCabFile", str(path))

    def SaveSFile(self, path):
        return self.call("SaveSFile", str(path))

    def SaveNfbFile(self, path):
        return self.call("SaveNfbFile", str(path))

    def SaveXmlFile(self, path):
        return self.call("SaveXmlFile", str(path))

    def SaveParamFile(self, path):
        return self.call("SaveParamFile", str(path))

    def SaveConditionFile(self, path):
        return self.call("SaveConditionFile", str(path))

    def SaveLibraryCabFile(self, path):
        return self.call("SaveLibraryCabFile", str(path))

    def OpenCadFile(self, path):
        return self.call("OpenCadFile", str(path))

    def OpenDxfFile(self, path):
        return self.call("OpenDxfFile", str(path))

    def OpenNasFile(self, path):
        return self.call("OpenNasFile", str(path))

    def OpenXmlFile(self, path):
        return self.call("OpenXmlFile", str(path))

    def OpenTextFile(self, path):
        return self.call("OpenTextFile", str(path))

    def OpenCsvFile(self, path):
        return self.call("OpenCsvFile", str(path))

    def OpenLibraryCabFile(self, path):
        return self.call("OpenLibraryCabFile", str(path))

    # -- boolean / solid editing ----------------------------------------
    def Intersect(self, a, b, name):
        return self.call("Intersect", a, b, name)

    def Subtract(self, a, b, name):
        return self.call("Subtract", a, b, name)

    def Unite(self, a, b, name):
        return self.call("Unite", a, b, name)

    def Section(self, *args):
        return self.call("Section", *args)

    def EditSolidModel(self, *args):
        return self.call("EditSolidModel", *args)

    def SelectSolidModel(self, *args):
        return self.call("SelectSolidModel", *args)

    # -- accessors ------------------------------------------------------
    def GetMesher(self):
        return STpreMesher(self.call("GetMesher"))

    def GetSketcher(self):
        return STpreSketch(self.call("GetSketcher"))

    def GetModel(self, name):
        return STpreModel(self.call("GetModel", name))

    def GetAllModelArray(self, kind="parts"):
        return [STpreModel(m) for m in self.call("GetAllModelArray", kind)]

    def GetRootModelArray(self):
        return [STpreModel(m) for m in self.call("GetRootModelArray")]

    def GetValue(self, name):
        return STpreValue(self.call("GetValue", name))

    def GetAllValueArray(self):
        return [STpreValue(v) for v in self.call("GetAllValueArray")]

    def GetDomain(self):
        return STpreModel(self.call("GetDomain"))

    def GetFluidArea(self, idx=0):
        return STpreModel(self.call("GetFluidArea", idx))

    def GetTable(self, name):
        return STpreTable(self.call("GetTable", name))

    def GetPropertyEntity(self, name):
        return STpreProperty(self.call("GetPropertyEntity", name))

    def GetNumAllModelArray(self):
        return self.call("GetNumAllModelArray")

    def GetAllPartsBoundingBox(self):
        return self.call("GetAllPartsBoundingBox")

    # -- project / analysis ---------------------------------------------
    def GetProjectName(self):
        return self.call("GetProjectName")

    def SetProjectName(self, name):
        return self.call("SetProjectName", name)

    def GetComment(self):
        return self.call("GetComment")

    def SetComment(self, text):
        return self.call("SetComment", text)

    def GetFileName(self):
        return self.call("GetFileName")

    def SetFileName(self, name):
        return self.call("SetFileName", name)

    def GetAmbientTemperature(self):
        return self.call("GetAmbientTemperature")

    def SetAmbientTemperature(self, value):
        return self.call("SetAmbientTemperature", value)

    def GetGravity(self):
        return self.call("GetGravity")

    def SetGravity(self, gx, gy, gz):
        return self.call("SetGravity", gx, gy, gz)

    def GetAnalysisType(self, kind):
        return self.call("GetAnalysisType", kind)

    def SetAnalysisType(self, kind, flag):
        return self.call("SetAnalysisType", kind, flag)

    def SetMoveBodyOption(self, key: str, param) -> int:
        """Set a moving-object analysis parameter (MOVB_OPTION).

        Keywords (VB manual): 'panel', 'interference', 'initial-state',
        'listout-position', 'courant', 'gap_filling', 'body_file',
        'matrix_solver', 'pdro_threshold', 'dynamical_gravity',
        'dynamical_fluid'.  Returns 1 on success.
        """
        return self.call("SetMoveBodyOption", key, param)

    def GetMoveBodyOption(self, key: str):
        """Read back a SetMoveBodyOption parameter."""
        return self.call("GetMoveBodyOption", key)

    def SetCartesianDomain(self, x1, y1, z1, x2, y2, z2):
        return self.call("SetCartesianDomain", x1, y1, z1, x2, y2, z2)

    def SetCylindricalDomain(self, *args):
        return self.call("SetCylindricalDomain", *args)

    def SetUnit(self, *args):
        return self.call("SetUnit", *args)

    def GetUnit(self, key):
        """``Doc.GetUnit("length")`` -> "km"/"m"/"cm"/"mm"/"um"。

        WindTool 入口用它做功率律高度（梯度高/参考高）的单位换算：
        km=0.001 / m=1 / cm=100 / mm=1000 / um=1000000 倍。
        """
        return self.call("GetUnit", key)

    # -- part creation (Create*Model; the full surface is call()-able) ---
    def CreateCubeModel(self, name, base, size):
        return STpreModel(self.call("CreateCubeModel", name, base, size))

    def CreateCylinderModel(self, name, *args):
        return STpreModel(self.call("CreateCylinderModel", name, *args))

    def CreateSphereModel(self, name, *args):
        return STpreModel(self.call("CreateSphereModel", name, *args))

    def CreateConeModel(self, name, *args):
        return STpreModel(self.call("CreateConeModel", name, *args))

    def CreatePanelModel(self, name, *args):
        return STpreModel(self.call("CreatePanelModel", name, *args))

    def CreateHexaModel(self, name, *args):
        return STpreModel(self.call("CreateHexaModel", name, *args))

    def CreatePipeModel(self, name, *args):
        return STpreModel(self.call("CreatePipeModel", name, *args))

    def CreateFinModel(self, name, *args):
        return STpreModel(self.call("CreateFinModel", name, *args))

    def CreateFanModel(self, name, *args):
        return STpreModel(self.call("CreateFanModel", name, *args))

    def CreateAxialFanModel(self, name, *args):
        return STpreModel(self.call("CreateAxialFanModel", name, *args))

    def CreateBlowerFanModel(self, name, *args):
        return STpreModel(self.call("CreateBlowerFanModel", name, *args))

    def CreateAirconModel(self, name, *args):
        return STpreModel(self.call("CreateAirconModel", name, *args))

    def CreateAnemoModel(self, name, *args):
        return STpreModel(self.call("CreateAnemoModel", name, *args))

    def CreateCardGuideModel(self, name, *args):
        return STpreModel(self.call("CreateCardGuideModel", name, *args))

    def CreateCaseModel(self, name, *args):
        return STpreModel(self.call("CreateCaseModel", name, *args))

    def CreateDelphiModel(self, name, *args):
        return STpreModel(self.call("CreateDelphiModel", name, *args))

    def CreateExtrudeModel(self, name, *args):
        return STpreModel(self.call("CreateExtrudeModel", name, *args))

    def CreateHoleModel(self, name, *args):
        return STpreModel(self.call("CreateHoleModel", name, *args))

    def CreateLinerDiffuserModel(self, name, *args):
        return STpreModel(self.call("CreateLinerDiffuserModel", name, *args))

    def CreatePeltierModel(self, name, *args):
        return STpreModel(self.call("CreatePeltierModel", name, *args))

    def CreatePinFinModel(self, name, *args):
        return STpreModel(self.call("CreatePinFinModel", name, *args))

    def CreatePointModel(self, name, *args):
        return STpreModel(self.call("CreatePointModel", name, *args))

    def CreateQuadPanelModel(self, name, *args):
        return STpreModel(self.call("CreateQuadPanelModel", name, *args))

    def CreateRevolveModel(self, name, *args):
        return STpreModel(self.call("CreateRevolveModel", name, *args))

    def CreateSlitPunchingModel(self, name, *args):
        return STpreModel(self.call("CreateSlitPunchingModel", name, *args))

    def CreateSpinRectangleSimpleModel(self, name, *args):
        return STpreModel(self.call("CreateSpinRectangleSimpleModel", name, *args))

    def CreateSweepModel(self, name, *args):
        return STpreModel(self.call("CreateSweepModel", name, *args))

    def CreateTwoResistanceModel(self, name, *args):
        return STpreModel(self.call("CreateTwoResistanceModel", name, *args))

    def CreateGroup(self, name):
        return ComObject(self.call("CreateGroup", name))

    def CreateFaceListSet(self, name, *args):
        return ComObject(self.call("CreateFaceListSet", name, *args))

    def CreateRegionPair(self, *args):
        return ComObject(self.call("CreateRegionPair", *args))

    def CreateConnectedRegion(self, *args):
        return ComObject(self.call("CreateConnectedRegion", *args))

    # -- materials / properties / conditions ----------------------------
    def CreateFluidMaterial(self, name):
        return ComObject(self.call("CreateFluidMaterial", name))

    def CreateSolidMaterial(self, name):
        return ComObject(self.call("CreateSolidMaterial", name))

    def CreateAbsorptionProperty(self, name):
        return ComObject(self.call("CreateAbsorptionProperty", name))

    def CreateRadiationProperty(self, name):
        return ComObject(self.call("CreateRadiationProperty", name))

    def CreatePropertyGroup(self, name):
        return ComObject(self.call("CreatePropertyGroup", name))

    def CreateReactiveFormula(self, name):
        return ComObject(self.call("CreateReactiveFormula", name))

    def CreateScript(self, name):
        return ComObject(self.call("CreateScript", name))

    def CreateExpression(self, name):
        return ComObject(self.call("CreateExpression", name))

    def CreateUserFunction(self, name):
        return ComObject(self.call("CreateUserFunction", name))

    def CreateUserData(self, name):
        return ComObject(self.call("CreateUserData", name))

    # -- conditions (common subset; full Set*/Get* via call()) ----------
    def SetNorthAngle(self, angle):
        """``Doc.SetNorthAngle(angle)`` — 设置北向角（度）。

        WindTool 每个风向循环前调用，把入口风向角（相对北向）转到全局
        坐标：``FlowAngle = NorthAngle + Theta``。
        """
        return self.call("SetNorthAngle", angle)

    def SetWall(self, region, *args):
        return self.call("SetWall", region, *args)

    def SetFluxFix(self, region, *args):
        return self.call("SetFluxFix", region, *args)

    def SetFluxPres(self, region, *args):
        return self.call("SetFluxPres", region, *args)

    def SetFluxOut(self, region, *args):
        return self.call("SetFluxOut", region, *args)

    def SetFluxPower(self, region, *args):
        return self.call("SetFluxPower", region, *args)

    def SetFluxPower2(self, *args):
        """幂律风速廓线入口边界条件（WindTool 16 风向入口）。

        与 ``STpre_STsolver_eng.vbs`` 一致，11 参数透传：
        ``(name, RefVel, "N", Theta, Exponent, GrdHei, RefHei, 0.0,
        TurbType, KEParam1, KEParam2)``

        * ``name``     — 入口条件名（VBS 用 ``CondIn = "Tool_Flux1_"``）；
        * ``RefVel``   — 参考高度处的参考风速 (m/s)；
        * ``"N"``      — 角度基准（"N" 表示以北向为 0°，固定）；
        * ``Theta``    — 入口风向角（度，风**吹向**，``180 + i*360/16``）；
        * ``Exponent`` — 幂律指数（默认 3.7037）；
        * ``GrdHei``   — 梯度高度（默认 0.0，按长度单位换算）；
        * ``RefHei``   — 参考高度（默认 74.5，按长度单位换算）；
        * ``0.0``      — 粗糙度（固定 0.0）；
        * ``TurbType`` — 湍流类型（"zg" 标准）；
        * ``KEParam1`` — k-ε 参数 1（默认 550，"zg" 时按单位换算）；
        * ``KEParam2`` — k-ε 参数 2（默认 0）。
        """
        return self.call("SetFluxPower2", *args)

    def SetTemperatureFix(self, region, *args):
        return self.call("SetTemperatureFix", region, *args)

    def SetHeatTransfer(self, region, *args):
        return self.call("SetHeatTransfer", region, *args)

    def SetHeatSource(self, region, *args):
        return self.call("SetHeatSource", region, *args)

    def SetSymmetry(self, region, *args):
        return self.call("SetSymmetry", region, *args)

    def SetInitialValue(self, *args):
        return self.call("SetInitialValue", *args)

    def SetFanPQcurve(self, *args):
        return self.call("SetFanPQcurve", *args)

    def SetFanConstFlow(self, *args):
        return self.call("SetFanConstFlow", *args)

    # -- housekeeping ----------------------------------------------------
    def DeleteModel(self, name):
        return self.call("DeleteModel", name)

    def DeleteValue(self, name):
        return self.call("DeleteValue", name)

    def DeleteTable(self, name):
        return self.call("DeleteTable", name)

    def DeleteScript(self, name):
        return self.call("DeleteScript", name)

    def ClearSelect(self):
        return self.call("ClearSelect")

    def SortModel(self, *args):
        return self.call("SortModel", *args)

    # -- extended surface (2026-08-16 signature sweep, tools/probe_com_sig.py;
    #    evidence tools/probe_work/com_sig_probe.json) ----------------------
    #    Storage note (probe_com_storage.py -> data/com_storage_probe.json):
    #    enabling evap/solid_melt creates the canonical sections
    #    analysis_etc/evaporation{gas_temp,liquid_temp,latent_heat} and
    #    analysis_etc/fusion{liquid_rotate_omega,...} with zero defaults -
    #    the CW pages write the real values there natively.  The Set*Param
    #    wrappers exist for parity, but their value persistence needs the
    #    exact GUI key/value format (probed keys returned rc=0); SetUserEntity
    #    returns rc=1 yet stores nothing visible in the cab (session-local).
    def SetSolverParam(self, key: str, value):
        return self.call("SetSolverParam", key, value)

    def GetSolverParam(self, key: str):
        return self.call("GetSolverParam", key)

    def SetEvaporationParam(self, key: str, value):
        return self.call("SetEvaporationParam", key, value)

    def GetEvaporationParam(self, key: str):
        return self.call("GetEvaporationParam", key)

    def SetSolidMeltParam(self, key: str, value):
        return self.call("SetSolidMeltParam", key, value)

    def GetSolidMeltParam(self, key: str):
        return self.call("GetSolidMeltParam", key)

    def SetPhaseParam(self, key: str, value):
        return self.call("SetPhaseParam", key, value)

    def GetPhaseParam(self, key: str):
        return self.call("GetPhaseParam", key)

    def SetPorousHeatTransfer(self, region: str, model: str, coeff):
        return self.call("SetPorousHeatTransfer", region, model, coeff)

    def SetCycle(self, kind: str, ncyc):
        return self.call("SetCycle", kind, ncyc)

    def GetCycle(self):
        return self.call("GetCycle")

    def SetUserEntity(self, key: str, value):
        return self.call("SetUserEntity", key, value)

    def GetUserEntity(self, key: str):
        return self.call("GetUserEntity", key)

    def GetScript(self, name: str):
        return self.call("GetScript", name)

    def GetExpression(self, name: str):
        return self.call("GetExpression", name)

    def GetReferencedExpression(self, name: str):
        return self.call("GetReferencedExpression", name)

    def SetUserFunction(self, name: str, expr: str):
        return self.call("SetUserFunction", name, expr)

    def GetUserFunction(self, name: str):
        return self.call("GetUserFunction", name)

    def SetUserData(self, name: str, value):
        return self.call("SetUserData", name, value)

    def GetUserData(self, name: str):
        return self.call("GetUserData", name)
class STpreModel(ComObject):
    """Model class (part / region / group).  458 members; call()-able."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    @property
    def Visible(self):
        return self.prop("Visible")

    @Visible.setter
    def Visible(self, value):
        self.set_prop("Visible", value)

    def GetName(self):
        return self.call("GetName")

    def GetModelType(self):
        return self.call("GetModelType")

    def SetMoveBodyControl(self, key: str, params) -> "STpreValue":
        """Set the moving-object motion (MOVB_CONTROL).

        ``key``: 'T' translation velocity xyz (m/s) | 'R' omega (rad/s),
        rotation-center xyz, axis-vector xyz | 'B' both (10 values) |
        'X' translation coordinates xyz (mm).  Returns the created
        Value (saved as ``<value type="body_move">`` + ``<condition>``;
        COM-probed 2026-08-16).
        """
        return STpreValue(self.call("SetMoveBodyControl", key,
                                    list(params)))

    def GetBoundingBox(self):
        return self.call("GetBoundingBox")

    def GetVolume(self):
        return self.call("GetVolume")

    def GetColor(self):
        return self.call("GetColor")

    def SetColor(self, r, g, b):
        return self.call("SetColor", r, g, b)

    def GetMaterial(self):
        return self.call("GetMaterial")

    def SetMaterial(self, name):
        return self.call("SetMaterial", name)

    def GetTransform(self):
        return self.call("GetTransform")

    def GetParam(self, key):
        return self.call("GetParam", key)

    def SetParam(self, key, *args):
        return self.call("SetParam", key, *args)

    def Copy(self, *args):
        return self.call("Copy", *args)

    def Rotate(self, *args):
        return self.call("Rotate", *args)

    def Move(self, *args):
        return self.call("Move", *args)

    def ConvertModel(self, *args):
        return self.call("ConvertModel", *args)

    def CreateConvexHull(self, *args):
        return self.call("CreateConvexHull", *args)

    def CreateFEM(self, *args):
        """FEM Conversion（Edit 菜单）：把实体件转成 FEM 单元模型。

        手册签名 ``model.CreateFEM(length, scale, edge)``（VB manual
        Model class，COM 探针实证 2026-08-16，结果见
        ``tools/probe_work/fem_probe.json``）：

        * ``length`` — 单元尺寸 (double)。``scale="T"`` 时为部件长度
          （各轴最大长度）的比例，``"F"`` 时为绝对 mm 尺寸；
        * ``scale`` — ``"T"/"F"``（同上）；
        * ``edge``  — ``"T"`` 保留部件棱边 / ``"F"`` 不保留；

        返回新 Model（原实体件保留，主 XML 新增 ``fem_<原名>`` 的
        ``type="mesh_body"`` 部件，单元数据存 cab 的 ``.xfem`` 成员，
        4 组合 (2.0,'F','T')/(0.05,'T','T')/(4.0,'F','F')/(0.05,'T','F')
        全部成功，输出 kind=4 四面体）。
        """
        return self.call("CreateFEM", *args)

    def Deform(self, *args):
        return self.call("Deform", *args)

    def SaveStlFile(self, path):
        return self.call("SaveStlFile", str(path))

    def SaveXtFile(self, path):
        return self.call("SaveXtFile", str(path))

    def GetFaceArray(self):
        return self.call("GetFaceArray")

    def GetSubModelArray(self):
        return [STpreModel(m) for m in self.call("GetSubModelArray")]

    def GetValueArray(self):
        return [STpreValue(v) for v in self.call("GetValueArray")]

    def AppendValue(self, name):
        return self.call("AppendValue", name)

    def RemoveValue(self, name):
        return self.call("RemoveValue", name)

    def SetMeshDivide(self, *args):
        return self.call("SetMeshDivide", *args)

    def SetMeshDivideType(self, kind):
        return self.call("SetMeshDivideType", kind)

    def GetMeshParam(self, key):
        return self.call("GetMeshParam", key)

    def SetFacetParam(self, *args):
        return self.call("SetFacetParam", *args)

    def GetFacetParam(self):
        return self.call("GetFacetParam")


class STpreMesher(ComObject):
    """Mesher class — gridding/element division. 69 members."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetBlock(self, name):
        return STpreMeshBlock(self.call("GetBlock", name))

    def GetRootBlock(self):
        return STpreMeshBlock(self.call("GetRootBlock"))

    def GetActiveBlock(self):
        return self.call("GetActiveBlock")

    def SetActiveBlock(self, name):
        return self.call("SetActiveBlock", name)

    def CreateBlock(self, name, parent, type_):
        return STpreMeshBlock(self.call("CreateBlock", name, parent, type_))

    def DeleteBlock(self, name):
        return self.call("DeleteBlock", name)

    def SetGridParam(self, key, p1=0, p2=0, p3=0):
        return self.call("SetGridParam", key, p1, p2, p3)

    def GetGridParam(self, key):
        return self.call("GetGridParam", key)

    def ExecuteGrid(self, method, flag):
        return self.call("ExecuteGrid", method, flag)

    def ExecuteElement(self):
        return self.call("ExecuteElement")

    def ExecutePartsElement(self, part):
        return self.call("ExecutePartsElement", part)

    def GetNumElements(self):
        return self.call("GetNumElements")

    def GetNumEdgeContact(self, part):
        return self.call("GetNumEdgeContact", part)

    def RemoveEdgeContact(self, part):
        return self.call("RemoveEdgeContact", part)

    def SetSelectGrid(self, block, axis, num, value):
        return self.call("SetSelectGrid", block, axis, num, value)

    def GetSelectGrid(self):
        return self.call("GetSelectGrid")

    def Update(self):
        return self.call("Update")


class STpreMeshBlock(ComObject):
    """MeshBlock class — block params / range / grid arrays. 88 members."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetName(self):
        return self.call("GetName")

    def SetName(self, name):
        return self.call("SetName", name)

    def GetRange(self):
        return self.call("GetRange")

    def SetRange(self, x1, y1, z1, x2, y2, z2):
        return self.call("SetRange", x1, y1, z1, x2, y2, z2)

    def GetParam(self, key):
        return self.call("GetParam", key)

    def SetParam(self, key, p1=0, p2=0, p3=0):
        return self.call("SetParam", key, p1, p2, p3)

    def GetDivideArray(self, axis):
        return self.call("GetDivideArray", axis)

    def SetDivideArray(self, axis, values):
        return self.call("SetDivideArray", axis, values)

    def GetNumDivision(self, axis):
        return self.call("GetNumDivision", axis)

    def GetNumElements(self):
        return self.call("GetNumElements")

    def GetAspectRatio(self):
        return self.call("GetAspectRatio")

    def GetAttribute(self):
        return self.call("GetAttribute")

    def SetAttribute(self, type_):
        return self.call("SetAttribute", type_)

    def CreateBlock(self, name, type_):
        return STpreMeshBlock(self.call("CreateBlock", name, type_))

    def CreateConnectedBlock(self, name):
        return STpreMeshBlock(self.call("CreateConnectedBlock", name))

    def AppendBlock(self, name):
        return self.call("AppendBlock", name)

    def RemoveBlock(self, name):
        return self.call("RemoveBlock", name)

    def DeleteGrid(self, type_):
        return self.call("DeleteGrid", type_)

    def SetDetailGrid(self, axis, *args):
        return self.call("SetDetailGrid", axis, *args)

    def GetChildBlockArray(self):
        return [STpreMeshBlock(b) for b in self.call("GetChildBlockArray")]

    def GetParentBlock(self):
        return STpreMeshBlock(self.call("GetParentBlock"))


class STpreValue(ComObject):
    """Value class — one condition's name/params. 272 members."""

    @property
    def ErrorCode(self):
        return self.prop("ErrorCode")

    @property
    def ErrorString(self):
        return self.prop("ErrorString")

    def GetName(self):
        return self.call("GetName")

    def SetName(self, name):
        return self.call("SetName", name)

    def GetTypeKey(self):
        return self.call("GetTypeKey")

    def GetSubTypeKey(self):
        return self.call("GetSubTypeKey")

    def GetParam(self, key):
        return self.call("GetParam", key)

    def SetParam(self, key, *args):
        return self.call("SetParam", *pack_set_param(key, *args))

    def SetParam3(self, *args):
        vals = list(args) + [0] * max(0, 3 - len(args))
        return self.call("SetParam3", *vals[:3])

    def GetParamString(self, key):
        return self.call("GetParamString", key)

    def GetTable(self, key):
        return STpreTable(self.call("GetTable", key))

    def SetTable(self, key, table):
        return self.call("SetTable", key, table)

    def GetScript(self, key):
        return ComObject(self.call("GetScript", key))

    def SetScript(self, key, script):
        return self.call("SetScript", key, script)

    def GetExpression(self, key):
        return ComObject(self.call("GetExpression", key))

    def SetExpression(self, key, expr):
        return self.call("SetExpression", key, expr)

    def GetUserFunction(self, key):
        return ComObject(self.call("GetUserFunction", key))

    def SetUserFunction(self, key, fn):
        return self.call("SetUserFunction", key, fn)

    def GetMapping(self, key):
        return self.call("GetMapping", key)

    def SetMapping(self, key, *args):
        return self.call("SetMapping", key, *args)

# ============================================================================
# Convenience: headless create / attach + full API catalog
# ============================================================================


def create_application(*, headless: bool = True) -> STpreApplication:
    """Start a private STpre instance (hidden when headless).

    ``Dispatch`` on this single-instance server returns the *running*
    instance if one exists; use :func:`attach_application` for that case.
    """
    import win32com.client
    app = win32com.client.Dispatch(PROGID)
    if headless:
        app.Visible = False
    return STpreApplication(app)


def attach_application() -> STpreApplication:
    """Attach to an already-running STpre (``GetActiveObject``)."""
    import win32com.client
    return STpreApplication(win32com.client.GetActiveObject(PROGID))


def headless_roundtrip(cab_in: str | Path, cab_out: str | Path, *,
                       method: str = "detail", division_type: str = "all",
                       attach: bool = True, run_element: bool = True,
                       grid_params: Optional[list] = None,
                       block_params: Optional[list] = None) -> bool:
    """Headless full round-trip via the typed class hierarchy.

    Demonstrates the Application -> Doc -> Mesher -> MeshBlock chain and is
    functionally identical to :func:`run_stpre_grid_mesh` (kept for the
    file-relay callers).  Returns True when the output CAB was saved.
    """
    global last_error
    session = STpreSession(attach=attach, headless=True)
    try:
        if not session.ensure_open(cab_in):
            return False
        doc = session.doc
        mesher = session.mesher
        if block_params:
            root = mesher.GetBlock("root")
            for key, p1, p2, p3 in block_params:
                if root.SetParam(key, p1, p2, p3) != 1:
                    last_error = f"SetParam({key}) failed"
                    return False
        params = grid_params if grid_params is not None else [
            ("division_method", method, "", ""),
            ("division_type", division_type, "", ""),
        ]
        for key, p1, p2, p3 in params:
            if mesher.SetGridParam(key, p1, p2, p3) != 1:
                last_error = f"SetGridParam({key}) failed"
                return False
        if mesher.ExecuteGrid(method, "T") != 1:
            last_error = f"ExecuteGrid({method}) failed"
            return False
        if run_element and mesher.ExecuteElement() != 1:
            last_error = "ExecuteElement failed"
            return False
        if doc.SaveCabFile(str(cab_out)) != 1:
            last_error = "SaveCabFile failed"
            return False
        last_error = None
        return True
    finally:
        session.close()


# Full method catalog (names only) for discovery.  Every member below (and
# every member in the manual) is reachable via ``ComObject.call(name, ...)``.
API_CATALOG: dict[str, list[str]] = {
    "Application": [
        "ErrorCode", "ErrorString", "Visible", "UserControl",
        "WriteBackToEnvFile", "BeginViewerMode", "ClearDocument",
        "CreateDrawWnd", "GetDocument", "GetEnvFilePath", "GetFileVersion",
        "GetHomeFolder", "GetProcessID", "GetVersionNo", "IsViewerMode",
        "Quit", "UpdateAll",
    ],
    "Mesher": [
        "CreateBlock", "DeleteBlock", "ExecuteGrid", "ExecuteElement",
        "ExecutePartsElement", "GetActiveBlock", "GetBlock", "GetGridParam",
        "GetNumEdgeContact", "GetNumElements", "GetRootBlock", "GetSelectGrid",
        "RemoveEdgeContact", "SetActiveBlock", "SetGridParam", "SetSelectGrid",
        "Update",
    ],
    "MeshBlock": [
        "AppendBlock", "CreateBlock", "CreateConnectedBlock", "DeleteGrid",
        "GetAspectRatio", "GetAttribute", "GetChildBlockArray",
        "GetDependentBlockArray", "GetDivideArray", "GetName",
        "GetNumBlockArray", "GetNumDivision", "GetNumElements", "GetParam",
        "GetParentBlock", "GetRange", "RemoveBlock", "SetAttribute",
        "SetDetailGrid", "SetDivideArray", "SetName", "SetParam", "SetRange",
    ],
    "Sketch": [
        "GetClose", "SetClose", "GetSystem", "SetSystem", "GetTarget",
        "SetTarget", "GetVertex", "SetVertex", "GetVertexKind",
        "SetCircle", "SetRectangle", "SetSide",
    ],
    "Property": [
        "CreateEntity", "DeleteEntity", "Get", "Set", "GetData", "SetData",
        "GetEntities", "GetExpression", "SetExpression", "GetKind", "GetName",
        "GetNum", "SetNum", "GetRadField", "SetRadField", "GetScript",
        "SetScript", "GetTable", "SetTable", "GetTypeString",
        "GetUserFunction", "SetUserFunction",
    ],
    "Table": [
        "GetData", "SetData", "GetName", "SetName", "GetNum",
        "GetTableCondParam", "SetTableCondParam", "GetTypeString",
        "SetType", "GetXUnit", "GetYUnit", "SetUnit",
    ],
    "Doc_high_value": [
        "OpenCabFile", "SaveCabFile", "SaveSFile", "SaveNfbFile",
        "SaveXmlFile", "SaveParamFile", "SaveConditionFile", "SaveLibraryCabFile",
        "OpenCadFile", "OpenDxfFile", "OpenNasFile", "OpenXmlFile",
        "OpenTextFile", "OpenCsvFile", "OpenLibraryCabFile",
        "Intersect", "Subtract", "Unite", "Section", "EditSolidModel",
        "GetMesher", "GetSketcher", "GetModel", "GetAllModelArray",
        "GetValue", "GetAllValueArray", "GetDomain", "GetFluidArea",
        "GetTable", "GetPropertyEntity", "GetAllPartsBoundingBox",
        "CreateCubeModel", "CreateCylinderModel", "CreateSphereModel",
        "CreateConeModel", "CreatePanelModel", "CreateHexaModel",
        "CreatePipeModel", "CreateFinModel", "CreateFanModel",
        "CreateAxialFanModel", "CreateBlowerFanModel", "CreateAirconModel",
        "CreateAnemoModel", "CreateCardGuideModel", "CreateCaseModel",
        "CreateDelphiModel", "CreateExtrudeModel", "CreateHoleModel",
        "CreateLinerDiffuserModel", "CreatePeltierModel", "CreatePinFinModel",
        "CreatePointModel", "CreateQuadPanelModel", "CreateRevolveModel",
        "CreateSlitPunchingModel", "CreateSpinRectangleSimpleModel",
        "CreateSweepModel", "CreateTwoResistanceModel", "CreateGroup",
        "CreateFaceListSet", "CreateRegionPair", "CreateConnectedRegion",
        "CreateFluidMaterial", "CreateSolidMaterial", "CreateAbsorptionProperty",
        "CreateRadiationProperty", "CreatePropertyGroup", "CreateReactiveFormula",
        "CreateScript", "CreateExpression", "CreateUserFunction", "CreateUserData",
        "SetProjectName", "SetComment", "SetFileName", "SetAmbientTemperature",
        "SetGravity", "SetAnalysisType", "SetCartesianDomain",
        "SetCylindricalDomain", "SetUnit", "GetUnit", "SetNorthAngle",
        "SetWall", "SetFluxFix",
        "SetFluxPres", "SetFluxOut", "SetFluxPower", "SetFluxPower2",
        "SetTemperatureFix", "SetHeatTransfer",
        "SetHeatSource", "SetSymmetry", "SetInitialValue", "SetFanPQcurve", "SetFanConstFlow", "DeleteModel", "DeleteValue", "DeleteTable",
        "DeleteScript", "ClearSelect", "SortModel",
        "SetMoveBodyOption", "GetMoveBodyOption",
    ],
    "Model_high_value": [
        "Copy", "Rotate", "Move", "ConvertModel", "CreateConvexHull",
        "CreateFEM", "Deform", "GetBoundingBox", "GetVolume", "GetColor",
        "SetColor", "GetMaterial", "SetMaterial", "GetTransform",
        "GetParam", "SetParam", "SaveStlFile", "SaveXtFile", "GetFaceArray",
        "GetSubModelArray", "GetValueArray", "AppendValue", "RemoveValue",
        "SetMeshDivide", "SetMeshDivideType", "GetMeshParam", "SetFacetParam",
        "GetFacetParam", "SetAircon", "SetHeatSource", "SetEmissivity",
        "SetLayerNo", "SetDrawType", "SetCutcell", "GetName", "GetModelType",
        "SetMoveBodyControl",
    ],
    "Value_high_value": [
        "GetName", "SetName", "GetTypeKey", "GetSubTypeKey", "GetParam",
        "SetParam", "SetParam3", "GetParamString", "GetTable", "SetTable",
        "GetScript", "SetScript", "GetExpression", "SetExpression",
        "GetUserFunction", "SetUserFunction", "GetMapping", "SetMapping",
    ],
}


# Method counts observed in the VB_Interface_eng manual (for the record):
API_MEMBER_COUNTS = {
    "Application": 12,   # methods (17 members incl. properties)
    "Doc": 459,
    "Model": 458,
    "Value": 272,
    "Mesher": 69,
    "MeshBlock": 88,
    "Sketch": 12,   # Get/Set Close/System/Target/Vertex + Circle/Rectangle/Side
    "Property": 22,  # Get/Set + table/script/expression/entity (VB Property_Class)
    "Table": 12,     # Get/Set name/type/data/units/cond (VB Table_Class)
}


# ── W5: typelib authoritative enumeration + per-class coverage metric ────
#
# Layered closure plan (function_gap_analysis.md §四.6): layer A (wrapper
# coverage) can reach 100% once every typelib member has a typed wrapper;
# layer B (live semantic proof per member) has a hard headless ceiling.
# These helpers turn "~220/1409" into a measurable per-class metric and
# replace manual-count cross-checks with the registered type library as
# the authoritative member source (flowviewer com_typelib methodology).

_TYPELIB_CACHE = Path(__file__).resolve().parent / "data" / "com_typelib_members.json"

_TYPED_BY_VB: dict = {}  # populated below from the typed wrapper classes


def typelib_member_table(progid: str = PROGID) -> dict:
    """Authoritative member table from STpre's registered type library.

    Walks HKCR\\<progid>\\CLSID -> TypeLib (+Version), loads the typelib via
    ``pythoncom.LoadRegTypeLib`` and enumerates every type info's function
    and variable member names. Returns ``{type_name: sorted members}``.

    Requires STpre installed (pywin32 + registry); raises RuntimeError with
    the offending step otherwise. Cache the result with
    :func:`save_typelib_cache` so :func:`coverage_report` works offline.
    """
    import winreg

    import pythoncom

    def _reg(path: str) -> str:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path) as k:
                return winreg.QueryValueEx(k, "")[0]
        except OSError as exc:
            raise RuntimeError(f"registry {path}: {exc}") from exc

    clsid = _reg(progid + r"\CLSID")
    tlid = _reg(rf"CLSID\{clsid}\TypeLib")
    try:
        ver = _reg(rf"CLSID\{clsid}\Version")  # e.g. "1.0"
        major, minor = (int(x) for x in ver.split("."))
    except RuntimeError:
        major, minor = 1, 0
    try:
        lib = pythoncom.LoadRegTypeLib(pythoncom.MakeIID(tlid), major, minor, 0)
    except Exception as exc:  # pythoncom raises raw com_error
        raise RuntimeError(f"LoadRegTypeLib {tlid} {major}.{minor}: {exc}") from exc

    table: dict[str, list[str]] = {}
    for i in range(lib.GetTypeInfoCount()):
        tinfo = lib.GetTypeInfo(i)
        attr = tinfo.GetTypeInfoAttr()
        name = tinfo.GetDocumentation(-1)[0]
        members: set = set()
        for f in range(attr.cFuncs):
            fd = tinfo.GetFuncDesc(f)
            try:
                members.add(tinfo.GetNames(fd.memid)[0])
            except Exception:
                continue
        for v in range(attr.cVars):
            vd = tinfo.GetVarDesc(v)
            try:
                members.add(tinfo.GetNames(vd.memid)[0])
            except Exception:
                continue
        if name and members:
            table[name] = sorted(members)
    if not table:
        raise RuntimeError("typelib enumerated zero members")
    return table


_MANUAL_DIR = Path(
    r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\VB_Interface_eng")

# "Appliation" is Cradle's own typo in the shipped filename — do not fix.
_MANUAL_PAGES = {
    "Application": "St_vb_Preprocessor_Appliation_Class.html",
    "Doc": "St_vb_Preprocessor_Doc_Class.html",
    "Model": "St_vb_Preprocessor_Model_Class.html",
    "Value": "St_vb_Preprocessor_Value_Class.html",
    "Mesher": "St_vb_Preprocessor_Mesher_Class.html",
    "Sketch": "St_vb_Preprocessor_Sketch_Class.html",
    "Property": "St_vb_Preprocessor_Property_Class.html",
    "Table": "St_vb_Preprocessor_Table_Class.html",
    "AirconModel": "St_vb_Preprocessor_AirconModel_Class.html",
    "Femodel": "St_vb_Preprocessor_Femodel_Class.html",
    "GerberModel": "St_vb_Preprocessor_GerberModel_Class.html",
}

_MANUAL_STRUCTURAL_IDS = {
    "container", "contents", "toc", "toctitle", "Property", "Method",
    "Note", "Example", "See_also", "SeeAlso", "top",
}


def manual_member_table(manual_dir: Path | None = None) -> dict:
    """Member table parsed from the VB_Interface_eng manual class pages.

    Empirical chain (2026-08-18): this STpre registers no TypeLib and its
    IDispatch raises on GetTypeInfo, so the *manual* is the only
    authoritative member source on this machine. Every documented member
    has an ``id="Name"`` heading anchor (verified: heading ids == TOC
    level-2 anchors on every page); structural anchors (toc/Property/
    Method group headers) are excluded. Raises RuntimeError when the
    manual directory is absent.
    """
    import re

    root = Path(manual_dir) if manual_dir else _MANUAL_DIR
    if not root.is_dir():
        raise RuntimeError(f"manual dir not found: {root}")
    table: dict[str, list[str]] = {}
    for label, filename in _MANUAL_PAGES.items():
        page = root / filename
        if not page.exists():
            continue
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ids = set(re.findall(r'id="([A-Za-z_]\w*)"', text))
        members = sorted(ids - _MANUAL_STRUCTURAL_IDS)
        if members:
            table[label] = members
    if not table:
        raise RuntimeError(f"no member anchors parsed under {root}")
    return table


def save_typelib_cache(path: Path | None = None) -> Path:
    """Enumerate members and persist as JSON for offline reuse.

    Provenance chain, first success wins (recorded in ``_source``):
    registry typelib → VB manual heading anchors. (``dispatch_member_table``
    is deliberately off the automatic chain: it launches STpre only to find
    IDispatch::GetTypeInfo unsupported on this build.)
    """
    import json

    target = Path(path) if path else _TYPELIB_CACHE
    target.parent.mkdir(parents=True, exist_ok=True)
    table = None
    source = ""
    for fn, src in ((typelib_member_table, "typelib"),
                    (manual_member_table, "manual")):
        try:
            table = fn()
            source = src
            break
        except RuntimeError:
            continue
    if table is None:
        raise RuntimeError("no member source available")
    table["_source"] = source
    table["_generated"] = "2026-08-18"
    target.write_text(json.dumps(table, indent=1, sort_keys=True), encoding="utf-8")
    return target


def load_typelib_cache(path: Path | None = None) -> dict:
    """Load a previously saved member table; {} when the cache is absent."""
    import json

    target = Path(path) if path else _TYPELIB_CACHE
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # member lists become lists; provenance stamps (str) stay verbatim
        return {k: (v if isinstance(v, str) else list(v))
                for k, v in data.items()}
    except (OSError, ValueError):
        return {}


def coverage_report(table: dict | None = None) -> dict:
    """Per-class typed-wrapper coverage against the typelib member table.

    Typed wrappers expose VB member names verbatim (``OpenCabFile`` etc.), so
    coverage is an exact-name intersection. With no typelib table available
    the report still lists typed counts against the manual
    :data:`API_MEMBER_COUNTS` baseline (``pct`` then None).
    """
    if table is None:
        table = load_typelib_cache()
    rows: dict[str, dict] = {}
    tot_lib = tot_typed = 0
    for vb, cls in _TYPED_BY_VB.items():
        wrapped = {n for n in dir(cls) if not n.startswith("_")}
        members = sorted(set(table.get(vb, [])))
        hit = [m for m in members if m in wrapped]
        missing = [m for m in members if m not in wrapped]
        manual = API_MEMBER_COUNTS.get(vb, 0)
        rows[vb] = {
            "typelib": len(members),
            "manual": manual,
            "typed": len(hit),
            "pct": round(100.0 * len(hit) / len(members), 1) if members else None,
            "missing_head": missing[:8],
        }
        tot_lib += len(members)
        tot_typed += len(hit)
    rows["TOTAL"] = {
        "typelib": tot_lib,
        "manual": sum(API_MEMBER_COUNTS.values()),
        "typed": tot_typed,
        "pct": round(100.0 * tot_typed / tot_lib, 1) if tot_lib else None,
        "missing_head": [],
    }
    return rows


_TYPED_BY_VB = {
    "Application": STpreApplication,
    "Doc": STpreDoc,
    "Model": STpreModel,
    "Value": STpreValue,
    "Mesher": STpreMesher,
    "MeshBlock": STpreMeshBlock,
    "Sketch": STpreSketch,
    "Property": STpreProperty,
    "Table": STpreTable,
}


def _members_of_dispatch(obj) -> list[str]:
    """Function + variable member names of a live IDispatch object."""
    if obj is None:
        return []
    try:
        tinfo = obj._oleobj_.GetTypeInfo()
        attr = tinfo.GetTypeInfoAttr()
    except Exception:
        return []
    names: set = set()
    for f in range(attr.cFuncs):
        try:
            names.add(tinfo.GetNames(tinfo.GetFuncDesc(f).memid)[0])
        except Exception:
            continue
    for v in range(attr.cVars):
        try:
            names.add(tinfo.GetNames(tinfo.GetVarDesc(v).memid)[0])
        except Exception:
            continue
    return sorted(names)


def dispatch_member_table(cab_path: Path | None = None) -> dict:
    """Member table from a live STpre via IDispatch::GetTypeInfo.

    This machine's STpre registers no TypeLib (HKCR CLSID has only
    LocalServer32/ProgID/InprocHandler32), so ``typelib_member_table``
    cannot resolve a library — but every automation object still carries
    its own type info. This starts a private hidden STpre, opens a cab
    project (default ``tests/box.cab``) so the model/value/mesher routes
    return live objects, walks the documented getter routes and collects
    per-class members. Raises RuntimeError when STpre cannot be started;
    per-route failures degrade to skipped classes (recorded as []).
    """
    import win32com.client

    cab = str(Path(cab_path) if cab_path
              else Path(__file__).resolve().parent / "tests" / "box.cab")
    try:
        app = win32com.client.Dispatch(PROGID)
    except Exception as exc:
        raise RuntimeError(f"Dispatch {PROGID}: {exc}") from exc
    table: dict[str, list[str]] = {}
    try:
        table["Application"] = _members_of_dispatch(app)
        doc = _invoke(app, "GetDocument")
        table["Doc"] = _members_of_dispatch(doc)
        routes = [
            ("Mesher", lambda: _invoke(doc, "GetMesher")),
            ("Sketch", lambda: _invoke(doc, "GetSketcher")),
            ("Table", lambda: _invoke(doc, "GetTable")),
            ("Model", lambda: (_invoke(doc, "GetAllModelArray") or [None])[0]),
            ("Value", lambda: (_invoke(doc, "GetAllValueArray") or [None])[0]),
            ("Property", lambda: _invoke(doc, "GetPropertyEntity", 0)),
        ]
        for label, route in routes:
            try:
                table[label] = _members_of_dispatch(route())
            except Exception:
                table[label] = []
        try:
            mesher = _invoke(doc, "GetMesher")
            for getter, args in (("GetRootBlock", ()), ("GetBlock", (0,))):
                try:
                    blk = _invoke(mesher, getter, *args)
                    members = _members_of_dispatch(blk)
                    if members:
                        table["MeshBlock"] = members
                        break
                except Exception:
                    continue
            table.setdefault("MeshBlock", [])
        except Exception:
            table["MeshBlock"] = []
    finally:
        try:
            _invoke(app, "Quit")
        except Exception:
            pass
    live = {k: v for k, v in table.items() if v}
    if not live:
        raise RuntimeError("dispatch routes returned zero members")
    return table
