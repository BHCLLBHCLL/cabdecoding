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
        params.append(("division_num", str(int(target_elements)), "0", "0"))
    elif key == "auto3" and target_per_axis is not None:
        params.append(("division_num", *(str(int(v)) for v in target_per_axis)))
    if outer_ratio is None:
        try:
            vals = [float(x) for x in mc("divide_ratio2", "1.2,1.2,1.2")
                    .split(",")[:3]]
        except ValueError:
            vals = [1.2, 1.2, 1.2]
        outer_ratio = tuple(vals)
    params.append(("outer_ratio", *(f"{v:.12g}" for v in outer_ratio)))
    if edge_contact is None:
        edge_contact = 1 if mc("edge_contact", "0") == "1" else 0
    params.append(("edge_contact", str(edge_contact), "", ""))
    if max_elements is not None:
        params.append(("max_elements", str(int(max_elements)), "", ""))
    return params


def run_stpre_grid_mesh(cab_in: str | Path, cab_out: str | Path, *,
                        method: str = "detail",
                        division_type: str = "all",
                        grid_params: Optional[list[tuple]] = None,
                        run_element: bool = True) -> bool:
    """Launch STpre through COM and execute gridding (+ element division).

    Returns True when the output CAB was saved.  File paths are the relay
    between cab_gui's memory model and the external STpre process.
    """
    import win32com.client
    app = win32com.client.Dispatch(PROGID)
    try:
        app.Visible = False
        doc = app.GetDocument()
        if not doc.OpenCabFile(str(cab_in)):
            return False
        mesher = doc.GetMesher()
        params = grid_params if grid_params is not None else [
            ("division_method", method, "", ""),
            ("division_type", division_type, "", ""),
        ]
        for key, p1, p2, p3 in params:
            if mesher.SetGridParam(key, p1, p2, p3) != 1:
                return False
        if mesher.ExecuteGrid(method, "T") != 1:
            return False
        if run_element and mesher.ExecuteElement() != 1:
            return False
        if doc.SaveCabFile(str(cab_out)) != 1:
            return False
        return True
    finally:
        try:
            app.Quit()
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
