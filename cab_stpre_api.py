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
            vd = int(mc("select_vertex", "3"))
        except ValueError:
            vd = 3
    vd_key = _DIVISION_TYPE.get(vd, "all")
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


def build_params_from_gridspec(spec, *, edge_contact: Optional[int] = None
                               ) -> list[tuple[str, str, str, str]]:
    """Map a native ``GridSpec`` (Mesh:Set Division dialog) to
    ``SetGridParam`` tuples, so STpre API gridding uses the dialog settings.
    """
    vd_map = {
        "all": "all", "representative": "main", "axis_plane": "plane",
        "minmax": "minmax", "not_considered": "none", "uniform": "uniform",
    }
    vd = vd_map.get(getattr(spec, "vertex_detection", "minmax"), "minmax")
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


def build_relay_cab(model, archive, src_path: str | Path) -> bool:
    """Write the temp CAB relay from an official STpre XML template.

    STpre rejects minimal project XML (OpenCabFile returns 0), so the relay
    uses the full official ex4_e XML structure with the current project's
    domain / parts / body_files merged in; the mesh sections are regenerated
    by STpre itself.
    """
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
            if sec == "mesh_block":
                for ax in ("x", "y", "z"):
                    el = sec_el.find(ax)
                    if el is not None:
                        sec_el.remove(el)
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


def run_stpre_grid_mesh(cab_in: str | Path, cab_out: str | Path, *,
                        method: str = "detail",
                        division_type: str = "all",
                        grid_params: Optional[list[tuple]] = None,
                        run_element: bool = True) -> bool:
    """Launch STpre through COM and execute gridding (+ element division).

    Returns True when the output CAB was saved.  File paths are the relay
    between cab_gui's memory model and the external STpre process.
    """
    global last_error
    import win32com.client
    app = win32com.client.Dispatch(PROGID)
    try:
        app.Visible = False
        doc = _invoke(app, "GetDocument")
        rc = _invoke(doc, "OpenCabFile", str(cab_in))
        if rc != 1:
            last_error = f"OpenCabFile rc={rc}"
            return False
        mesher = _invoke(doc, "GetMesher")
        params = grid_params if grid_params is not None else [
            ("division_method", method, "", ""),
            ("division_type", division_type, "", ""),
        ]
        for key, p1, p2, p3 in params:
            rc = _invoke(mesher, "SetGridParam", key, p1, p2, p3)
            if rc != 1:
                last_error = f"SetGridParam({key}) rc={rc}"
                return False
        rc = _invoke(mesher, "ExecuteGrid", method, "T")
        if rc != 1:
            last_error = f"ExecuteGrid({method}) rc={rc}"
            return False
        if run_element:
            rc = _invoke(mesher, "ExecuteElement")
            if rc != 1:
                last_error = f"ExecuteElement rc={rc}"
                return False
        rc = _invoke(doc, "SaveCabFile", str(cab_out))
        if rc != 1:
            last_error = f"SaveCabFile rc={rc}"
            return False
        last_error = None
        return True
    finally:
        try:
            _invoke(app, "Quit")
        except Exception:
            pass


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
