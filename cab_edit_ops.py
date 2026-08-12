"""Model-side helpers for STpre [Edit] menu operations.

Geometry-heavy Parasolid ops (Boolean / Cutting / Sweep / …) are exposed as
best-effort transforms or XML registration so the GUI dialogs stay usable
without the native kernel.  Bounding-box and transform ops are exact.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import Optional

import numpy as np

import cab_domain
import cab_vtk
from cabxml import StpreModel, _first, set_text


IDENTITY = "1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"


def parse_transform(text: str | None) -> np.ndarray:
    """Column-major 4×4 from XML ``<transform>``; identity when empty."""
    m = np.eye(4, dtype=np.float64)
    if not text:
        return m
    vals = [float(v) for v in text.replace(" ", "").split(",") if v != ""]
    if len(vals) >= 16:
        m = np.array(vals[:16], dtype=np.float64).reshape(4, 4, order="F")
    return m


def format_transform(m: np.ndarray) -> str:
    flat = np.asarray(m, dtype=np.float64).reshape(4, 4, order="F").ravel(order="F")
    return ",".join(f"{v:.17g}" for v in flat)


def part_world_bounds(model: StpreModel, name: str, cad_meshes
                      ) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """World AABB (mm) of one part after its transform; ``None`` if empty."""
    meshes = {getattr(t, "name", None): t for t in (cad_meshes or [])}
    tess = meshes.get(name)
    if tess is None:
        return None
    pts = np.asarray(tess.points, dtype=np.float64)
    if pts.size == 0:
        return None
    info = next((p for p in model.parts() if p.name == name), None)
    pts = cab_vtk._apply_transform(pts, info.transform if info else "")
    return pts.min(0), pts.max(0)


def unique_part_name(model: StpreModel, base: str) -> str:
    names = {p.name for p in model.parts()}
    if base not in names:
        return base
    i = 2
    while f"{base}_{i}" in names:
        i += 1
    return f"{base}_{i}"


def clone_part_element(model: StpreModel, src_name: str,
                       new_name: str,
                       transform: Optional[str] = None) -> Optional[ET.Element]:
    """Deep-copy a ``<parts>`` node under the same parent with a new name."""
    src = model.find_part(src_name)
    if src is None or model.find_part(new_name) is not None:
        return None
    parent = model.root
    for grp in model.groups():
        if src in list(grp):
            parent = grp
            break
    clone = copy.deepcopy(src)
    for tag in ("name", "name2"):
        el = _first(clone, tag)
        if el is not None:
            set_text(el, new_name)
    if transform is not None:
        tel = _first(clone, "transform")
        if tel is None:
            tel = ET.SubElement(clone, "transform")
            tel.tail = "\n         "
        set_text(tel, transform)
    clone.tail = src.tail
    parent.append(clone)
    return clone


def translate_part(model: StpreModel, name: str, delta_mm: np.ndarray) -> bool:
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    m = parse_transform(info.transform)
    m[0:3, 3] += np.asarray(delta_mm, dtype=np.float64)
    return model.set_part_transform(name, format_transform(m))


def translate_copy_parts(model: StpreModel, names: list[str],
                         delta_mm, n_copies: int = 0) -> list[tuple[str, str]]:
    """STpre Translation/Copy Part.

    ``n_copies <= 0``: translate selected parts by ``delta_mm``.
    ``n_copies >= 1``: leave originals; create N copies offset by i*delta.

    Returns list of ``(source_name, new_name)`` for created copies.
    """
    delta = np.asarray(delta_mm, dtype=np.float64).reshape(3)
    created: list[tuple[str, str]] = []
    if n_copies <= 0:
        for name in names:
            translate_part(model, name, delta)
        return created
    for name in names:
        info = next((p for p in model.parts() if p.name == name), None)
        if info is None:
            continue
        base = parse_transform(info.transform)
        for i in range(1, int(n_copies) + 1):
            new_name = unique_part_name(model, name)
            m = base.copy()
            m[0:3, 3] = base[0:3, 3] + delta * float(i)
            if clone_part_element(
                    model, name, new_name,
                    transform=format_transform(m)) is not None:
                created.append((name, new_name))
    return created


def mirror_transform(transform: str, axis: str, plane: float) -> str:
    """Mirror a part transform across ``axis`` = plane (mm), axis in XYZ."""
    m = parse_transform(transform)
    # Reflect world points: P' = S (P - o) + o with S = diag(±1)
    s = np.eye(4)
    idx = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    s[idx, idx] = -1.0
    # T_mirror @ M : first apply M, then reflect about plane
    # Reflect about x=plane: x' = 2*plane - x
    t_to = np.eye(4)
    t_to[idx, 3] = -plane
    t_back = np.eye(4)
    t_back[idx, 3] = plane
    mirrored = t_back @ s @ t_to @ m
    return format_transform(mirrored)


def mirror_copy_parts(model: StpreModel, names: list[str], axis: str,
                      plane: float) -> list[str]:
    created: list[str] = []
    for name in names:
        info = next((p for p in model.parts() if p.name == name), None)
        if info is None:
            continue
        new_name = unique_part_name(model, f"{name}_m")
        tf = mirror_transform(info.transform, axis, plane)
        if clone_part_element(model, name, new_name, transform=tf) is not None:
            created.append(new_name)
    return created


def align_parts(model: StpreModel, part_a: str, part_b: str, axis: str,
                location: str, cad_meshes) -> bool:
    """Align Part B bounding box to Part A on one axis (STpre Align Parts)."""
    ba = part_world_bounds(model, part_a, cad_meshes)
    bb = part_world_bounds(model, part_b, cad_meshes)
    if ba is None or bb is None:
        return False
    a_lo, a_hi = ba
    b_lo, b_hi = bb
    idx = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    loc = location.lower()
    if loc in ("min", "minimum"):
        delta = a_lo[idx] - b_lo[idx]
    elif loc in ("max", "maximum"):
        delta = a_hi[idx] - b_hi[idx]
    else:  # center
        delta = 0.5 * ((a_lo[idx] + a_hi[idx]) - (b_lo[idx] + b_hi[idx]))
    d = np.zeros(3)
    d[idx] = delta
    return translate_part(model, part_b, d)


def convert_part_to_type(model: StpreModel, name: str, kind: str,
                         cad_meshes, *, keep: str = "minmax") -> bool:
    """Convert part metadata to cuboid/cylinder using world AABB."""
    bounds = part_world_bounds(model, name, cad_meshes)
    el = model.find_part(name)
    if el is None or bounds is None:
        return False
    lo, hi = bounds
    size = hi - lo
    if keep == "volume" and kind in ("cube", "cuboid"):
        vol = float(np.prod(np.maximum(size, 1e-9)))
        side = vol ** (1.0 / 3.0)
        center = 0.5 * (lo + hi)
        lo = center - 0.5 * side
        hi = center + 0.5 * side
        size = hi - lo
    el.attrib["type"] = "cube" if kind in ("cube", "cuboid", "hexahedron") \
        else ("cylinder" if kind == "cylinder" else kind)
    for tag, val in (("base", ",".join(f"{v:.17g}" for v in lo)),
                     ("size", ",".join(f"{v:.17g}" for v in size))):
        c = _first(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n         "
        set_text(c, val)
    # Reset transform — geometry baked into base/size
    model.set_part_transform(name, IDENTITY)
    if kind == "cylinder":
        center = 0.5 * (lo + hi)
        radius = 0.5 * max(size[0], size[1])
        height = size[2]
        for tag, val in (
                ("center", ",".join(f"{v:.17g}" for v in center)),
                ("radius", f"{radius:.17g}"),
                ("height", f"{height:.17g}"),
                ("direction", "0,0,1"),
        ):
            c = _first(el, tag)
            if c is None:
                c = ET.SubElement(el, tag)
                c.tail = "\n         "
            set_text(c, val)
    return True


def part_metric(model: StpreModel, name: str, cad_meshes,
                measure: str) -> Optional[float]:
    bounds = part_world_bounds(model, name, cad_meshes)
    if bounds is None:
        return None
    lo, hi = bounds
    size = hi - lo
    if measure == "length":
        return float(size.max())
    if measure == "size":
        return float(np.linalg.norm(size))
    # volume/area
    info = next((p for p in model.parts() if p.name == name), None)
    if info and info.kind == "panel":
        return float(size[0] * size[1] if size[2] < 1e-9
                     else max(size[0] * size[1], size[1] * size[2],
                              size[0] * size[2]))
    return float(np.prod(np.maximum(size, 0.0)))


def parts_matching_deletion(model: StpreModel, cad_meshes, *,
                            group: str = "",
                            target_solid: bool = True,
                            target_panel: bool = True,
                            measure: str = "volume",
                            criteria: float = 0.0,
                            keep_heat: bool = True) -> list[str]:
    """Names smaller than ``criteria`` under the given filters."""
    out: list[str] = []
    for p in model.parts():
        if group and p.group != group:
            continue
        is_panel = p.kind == "panel" or p.attribute.lower() == "panel"
        if is_panel and not target_panel:
            continue
        if (not is_panel) and not target_solid:
            continue
        if keep_heat and _has_heat_source(model, p.name):
            continue
        metric = part_metric(model, p.name, cad_meshes, measure)
        if metric is None:
            continue
        if metric < criteria:
            out.append(p.name)
    return out


def _has_heat_source(model: StpreModel, name: str) -> bool:
    for c in model.conditions():
        t = _first(c, "parts")
        if t is None or (t.text or "").strip() != name:
            continue
        v = _first(c, "value")
        if v is not None and "heat" in (v.text or "").lower():
            return True
        if "heat" in (c.attrib.get("type", "") or "").lower():
            return True
    return False


def ungroup(model: StpreModel, group_name: str) -> list[str]:
    """Move all parts in ``group_name`` to root and remove the empty group."""
    target = None
    for grp in model.groups():
        n = _first(grp, "name")
        if n is not None and (n.text or "").strip() == group_name:
            target = grp
            break
    if target is None:
        return []
    names = []
    for el in list(target):
        if el.tag != "parts":
            continue
        n = _first(el, "name")
        if n is not None and n.text:
            names.append(n.text.strip())
    moved = model.move_parts_to_group(names, "")
    parent = model.root
    for grp in model.groups():
        if target in list(grp):
            parent = grp
            break
    if target in list(parent):
        # only remove when empty of parts
        if not any(c.tag == "parts" for c in target):
            parent.remove(target)
    return moved


def group_names(model: StpreModel) -> list[str]:
    out = []
    for grp in model.groups():
        n = _first(grp, "name")
        if n is not None and (n.text or "").strip():
            out.append(n.text.strip())
    return out


def apply_reset_domain(model: StpreModel, *,
                       update_domain: bool,
                       coordinate: str,
                       periodic_y: bool,
                       update_gravity: bool,
                       gravity_acc: float,
                       gravity_vec: tuple[float, float, float],
                       update_temp: bool,
                       default_temp: float,
                       update_all_temps: bool,
                       update_emissivity: bool,
                       default_emissivity: float) -> None:
    """Apply [Reset Computational Domain] fields to the model."""
    if update_domain:
        spec = cab_domain.domain_from_xml(model) or cab_domain.DomainSpec()
        coord_map = {
            "cartesian": "cartesian",
            "cylindrical": "cylindrical",
            "axial": "axial",
            "Cartesian System": "cartesian",
            "Cylindrical System": "cylindrical",
            "Axis Symmetry": "axial",
        }
        spec.coordinate = coord_map.get(coordinate, "cartesian")
        cab_domain.apply_domain(model, spec)
        model.set_project_value(
            "periodic_y", "T" if periodic_y else "F")
    if update_gravity:
        model.set_gravity(gravity_acc, gravity_vec)
    if update_temp:
        model.set_ambient_temperature(default_temp)
        model.set_project_value("solid_init_temperature",
                                f"{default_temp:g}")
        if update_all_temps:
            _update_all_part_temperatures(model, default_temp)
    if update_emissivity:
        model.set_project_value("default_emissivity",
                                f"{default_emissivity:g}")


def _update_all_part_temperatures(model: StpreModel, temp: float) -> None:
    for p in model.parts():
        el = p.elem
        t = _first(el, "temperature")
        if t is None:
            t = ET.SubElement(el, "temperature")
            t.tail = "\n         "
        set_text(t, f"{temp:g}")


def flip_part_faces(cad_meshes, name: str) -> bool:
    """Reverse triangle winding of a tessellation (flip normals)."""
    for tess in cad_meshes or []:
        if getattr(tess, "name", None) != name:
            continue
        tris = getattr(tess, "triangles", None)
        if tris is None:
            tris = getattr(tess, "faces", None)
        if tris is None:
            return False
        arr = np.asarray(tris)
        if arr.ndim != 2 or arr.shape[1] < 3:
            return False
        arr = arr.copy()
        arr[:, [1, 2]] = arr[:, [2, 1]]
        if hasattr(tess, "triangles"):
            tess.triangles = arr
        else:
            tess.faces = arr
        return True
    return False


def place_part_by_centers(model: StpreModel, move_name: str, ref_name: str,
                          cad_meshes,
                          offset: tuple[float, float, float] = (0, 0, 0)
                          ) -> bool:
    """Translate ``move_name`` so its center matches ``ref_name`` + offset."""
    ba = part_world_bounds(model, ref_name, cad_meshes)
    bb = part_world_bounds(model, move_name, cad_meshes)
    if ba is None or bb is None:
        return False
    a_c = 0.5 * (ba[0] + ba[1])
    b_c = 0.5 * (bb[0] + bb[1])
    delta = a_c - b_c + np.asarray(offset, dtype=np.float64)
    return translate_part(model, move_name, delta)


def reconstruct_part_facets(model: StpreModel, archive, cad_meshes,
                            names: list[str], *,
                            facet_tol: float = 1e-4,
                            facet_angle: float = 12.0) -> list:
    """M24: re-run ``PK_TOPOL_facet_2`` for selected part names from XT members.

    Returns updated TessPart list (may be empty when pskernel/XT missing).
    """
    import cab_ps_ops
    if archive is None or not cab_ps_ops.available():
        return []
    want = set(names)
    updated = []
    for m in archive.members:
        if not m.name.endswith(".x_t") or not m.data:
            continue
        try:
            parts = cab_ps_ops.reconstruct_facet(
                m.data, names=want, facet_tol=facet_tol,
                facet_angle_deg=facet_angle, adaptive=True)
        except Exception:
            continue
        updated.extend(parts)
    if not updated or cad_meshes is None:
        return updated
    by_name = {getattr(t, "name", None): t for t in cad_meshes}
    for t in updated:
        by_name[t.name] = t
    cad_meshes[:] = list(by_name.values())
    return updated


def _find_body_tags(model: StpreModel, archive,
                    part_a: str, part_b: str
                    ) -> tuple[Optional[int], Optional[int]]:
    """Locate live body tags for two parts across archive x_t members.

    Bodies are matched by Parasolid SDL name; unmatched single-body members
    are assigned to remaining parts in order (multi-body members keep their
    name-matched bodies).
    """
    if archive is None:
        return None, None
    import ps_facet2_nodes as _ps
    if _ps is None:
        return None, None
    members = {m.name: m.data for m in (archive.members or [])}
    bf = model.doc.root.find("body_files")
    refs = []
    if bf is not None:
        for f in bf.findall("file"):
            txt = (f.text or "").strip()
            if txt and txt in members:
                refs.append(members[txt])
    sess = _ps._get_session()
    matched: dict[str, int] = {}
    leftovers: list[int] = []
    for xt in refs:
        try:
            tags = sess.expand_to_bodies(sess.receive_xt(xt))
        except Exception:
            continue
        for tag in tags:
            nm = ""
            try:
                nm = sess.body_name(tag)
            except Exception:
                pass
            if nm in (part_a, part_b) and nm not in matched:
                matched[nm] = int(tag)
            else:
                leftovers.append(int(tag))
    for name in (part_a, part_b):
        if name not in matched and leftovers:
            matched[name] = leftovers.pop(0)
    return matched.get(part_a), matched.get(part_b)


def _register_boolean_result(model, cad_meshes, archive, name, tess,
                             xt: Optional[bytes], kind: str,
                             keep_a: bool, keep_b: bool,
                             part_a: str, part_b: str) -> None:
    """Register a boolean result part (+ optional XT member)."""
    from cab_parts import PrimitivePart
    from xml.etree.ElementTree import SubElement
    file_ref = "x_t"
    if archive is not None and not xt:
        # PK_PART_transmit can fail on some boolean products; persist the
        # faceted result as a polygon/STL member instead of an x_t body.
        import cab_import
        stl = cab_import._tris_to_stl_bytes(
            np.asarray(tess.points, dtype=np.float64),
            np.asarray(tess.triangles, dtype=np.int64), name)
        member = cab_import.add_stl_member(
            archive, stl, name=f"{name}.stl")
        file_ref = member.name
        kind = "polygon"
    el = model.add_part(name=name, kind=kind, attribute="solid",
                        file_ref=file_ref)
    if el is None:
        return
    tess.name = name
    pts = np.asarray(tess.points, dtype=np.float64)
    lo, hi = pts.min(0) * 1000.0, pts.max(0) * 1000.0
    for tag, val in (
            ("base", ",".join(f"{v:.17g}" for v in lo)),
            ("size", ",".join(f"{v:.17g}" for v in (hi - lo))),
    ):
        c = _first(el, tag)
        if c is None:
            c = SubElement(el, tag)
            c.tail = "\n         "
        set_text(c, val)
    if archive is not None and xt:
        try:
            import cab_import
            cab_import.add_xt_member(archive, xt, name=f"{name}.x_t")
        except Exception:
            pass
    if cad_meshes is not None:
        cad_meshes.append(tess)
    if not keep_a:
        model.delete_part(part_a)
    if not keep_b:
        model.delete_part(part_b)


def _boolean_via_pk(model: StpreModel, cad_meshes, archive,
                    part_a: str, part_b: str, op: str,
                    result_name: str, *,
                    keep_a: bool, keep_b: bool) -> Optional[str]:
    """M33/M39-P1: ``PK_BODY_boolean_2`` on real x_t bodies when available,
    otherwise solid blocks from world AABB."""
    import cab_ps_ops
    if not cab_ps_ops.available():
        return None
    # Preferred: boolean the actual B-rep bodies from the archive members.
    tag_a, tag_b = _find_body_tags(model, archive, part_a, part_b)
    if tag_a and tag_b:
        try:
            import ps_facet2_nodes as _ps
            sess = _ps._get_session()
            res_tags = cab_ps_ops.body_boolean(tag_a, [tag_b], op)
            res_tag = res_tags[0]
            tess = (sess.facet_body_adaptive(res_tag)
                    or sess.facet2(res_tag) or sess.facet_go(res_tag))
            try:
                xt = cab_ps_ops.transmit_parts([res_tag])
            except Exception:
                xt = None
            res = {"tess": tess}
        except Exception:
            res = None
            xt = None
        if res is not None and res["tess"] is not None:
            name = unique_part_name(model, result_name)
            _register_boolean_result(
                model, cad_meshes, archive, name, res["tess"], xt,
                "body" if xt else "polygon",
                keep_a, keep_b, part_a, part_b)
            return name
    # Fallback: AABB blocks (kept for parts without x_t, e.g. primitives).
    ba = part_world_bounds(model, part_a, cad_meshes)
    bb = part_world_bounds(model, part_b, cad_meshes)
    if ba is None or bb is None:
        return None
    # part_world_bounds follows tess units (metres for CAD/primitives)
    a_lo, a_hi = np.asarray(ba[0], dtype=np.float64), np.asarray(
        ba[1], dtype=np.float64)
    b_lo, b_hi = np.asarray(bb[0], dtype=np.float64), np.asarray(
        bb[1], dtype=np.float64)
    a_size = np.maximum(a_hi - a_lo, 1e-9)
    b_size = np.maximum(b_hi - b_lo, 1e-9)
    try:
        tag_a = cab_ps_ops.create_solid_block(
            tuple(a_size), tuple(a_lo))
        tag_b = cab_ps_ops.create_solid_block(
            tuple(b_size), tuple(b_lo))
        tag_a = cab_ps_ops.entity_copy(tag_a)
        tag_b = cab_ps_ops.entity_copy(tag_b)
        results = cab_ps_ops.body_boolean(tag_a, [tag_b], op)
    except Exception:
        return None
    if not results:
        return None
    # Facet result body directly (PK_PART_transmit can fail on some
    # boolean products; tessellation still reflects true B-rep).
    try:
        import ps_facet2_nodes as _ps
        sess = _ps._get_session()
        tess = sess.facet_body_adaptive(results[0])
    except Exception:
        tess = None
    if tess is None or not getattr(tess, "triangles", None).size:
        return None
    xt = None
    try:
        xt = cab_ps_ops.transmit_parts(results)
    except Exception:
        xt = None
    name = unique_part_name(model, result_name)
    _register_boolean_result(
        model, cad_meshes, archive, name, tess, xt,
        "body", keep_a, keep_b, part_a, part_b)
    return name


def boolean_mesh_parts(model: StpreModel, cad_meshes, part_a: str, part_b: str,
                       op: str, result_name: str, *,
                       keep_a: bool = False, keep_b: bool = False,
                       archive=None, prefer_pk: bool = True
                       ) -> Optional[tuple[str, str]]:
    """Boolean → ``(name, backend)`` where backend is ``pk`` or ``csg``.

    M33: try ``PK_BODY_boolean_2`` (solid blocks from world AABB); fall back
    to tessellation CSG against B's AABB.
    """
    import cab_ps_ops
    from cab_parts import PrimitivePart

    if prefer_pk:
        pk_name = _boolean_via_pk(
            model, cad_meshes, archive, part_a, part_b, op, result_name,
            keep_a=keep_a, keep_b=keep_b)
        if pk_name:
            return pk_name, "pk"

    meshes = {getattr(t, "name", None): t for t in (cad_meshes or [])}
    ta, tb = meshes.get(part_a), meshes.get(part_b)
    if ta is None or tb is None:
        return None
    info_a = next((p for p in model.parts() if p.name == part_a), None)
    info_b = next((p for p in model.parts() if p.name == part_b), None)
    bb = cab_ps_ops.tess_world_aabb(
        tb, info_b.transform if info_b else "")
    if bb is None:
        return None
    lo_b, hi_b = bb
    pts = np.asarray(ta.points, dtype=np.float64)
    tris = np.asarray(ta.triangles, dtype=np.int64)
    pts = cab_vtk._apply_transform(
        pts, info_a.transform if info_a else "")
    if op == "unite":
        pts_b = cab_vtk._apply_transform(
            np.asarray(tb.points, dtype=np.float64),
            info_b.transform if info_b else "")
        tris_b = np.asarray(tb.triangles, dtype=np.int64) + len(pts)
        new_pts = np.vstack([pts, pts_b])
        new_tris = np.vstack([tris, tris_b])
    else:
        new_pts, new_tris = cab_ps_ops.mesh_boolean(
            pts, tris, lo_b, hi_b, op)
    if new_tris.size == 0:
        return None
    name = unique_part_name(model, result_name)
    el = model.add_part(name=name, kind="polygon", attribute="solid")
    if el is None:
        return None
    lo, hi = new_pts.min(0) * 1000.0, new_pts.max(0) * 1000.0
    from xml.etree.ElementTree import SubElement
    for tag, val in (
            ("base", ",".join(f"{v:.17g}" for v in lo)),
            ("size", ",".join(f"{v:.17g}" for v in (hi - lo))),
    ):
        c = _first(el, tag)
        if c is None:
            c = SubElement(el, tag)
            c.tail = "\n         "
        set_text(c, val)
    if cad_meshes is not None:
        cad_meshes.append(PrimitivePart(name, new_pts, new_tris.astype(np.int64)))
    if not keep_a:
        model.delete_part(part_a)
    if not keep_b:
        model.delete_part(part_b)
    return name, "csg"


def flip_selected_triangles(cad_meshes, name: str,
                            tri_indices: Optional[list[int]] = None) -> bool:
    """Flip all faces or a subset of triangle indices (M24 face pick)."""
    for tess in cad_meshes or []:
        if getattr(tess, "name", None) != name:
            continue
        arr = np.asarray(tess.triangles)
        if arr.ndim != 2 or arr.shape[1] < 3:
            return False
        arr = arr.copy()
        if tri_indices:
            for i in tri_indices:
                if 0 <= i < len(arr):
                    arr[i, [1, 2]] = arr[i, [2, 1]]
        else:
            arr[:, [1, 2]] = arr[:, [2, 1]]
        tess.triangles = arr
        return True
    return False


def panel_direction_from_normal(n: np.ndarray) -> str:
    """Map a face normal to STpre panel direction ``±X/±Y/±Z``."""
    n = np.asarray(n, dtype=np.float64).ravel()
    if n.size < 3 or float(np.linalg.norm(n)) < 1e-15:
        return "+Z"
    ax = int(np.argmax(np.abs(n[:3])))
    sign = "+" if n[ax] >= 0.0 else "-"
    return f"{sign}{'XYZ'[ax]}"


def panel_params_from_aabb(lo_mm: np.ndarray, hi_mm: np.ndarray,
                           direction: str
                           ) -> tuple[np.ndarray, np.ndarray]:
    """Panel base/size (mm) lying on the AABB face for ``direction``."""
    lo = np.asarray(lo_mm, dtype=np.float64).ravel()[:3].copy()
    hi = np.asarray(hi_mm, dtype=np.float64).ravel()[:3].copy()
    size = hi - lo
    ax = {"X": 0, "Y": 1, "Z": 2}[direction[-1]]
    sign = 1.0 if direction.startswith("+") else -1.0
    base = lo.copy()
    if sign > 0:
        base[ax] = hi[ax]
    else:
        base[ax] = lo[ax]
    size[ax] = 0.0
    # zero-thickness panel needs a tiny extent so meshing/display stays valid
    eps = max(1e-3, 1e-6 * float(np.linalg.norm(hi - lo)))
    size[ax] = eps
    if sign < 0:
        base[ax] -= eps
    return base, size


def face_plane_from_cell(tess, cell_id: int, transform: str = ""
                         ) -> Optional[dict]:
    """M33: plane + coplanar triangle cluster from a picked cell.

    Returns dict with ``normal``, ``origin_m``, ``lo_mm``, ``hi_mm``,
    ``direction``, ``tri_ids`` (metres / mm as named).
    """
    if tess is None or cell_id is None:
        return None
    pts = np.asarray(tess.points, dtype=np.float64)
    tris = np.asarray(tess.triangles, dtype=np.int64)
    cid = int(cell_id)
    if pts.size == 0 or cid < 0 or cid >= len(tris):
        return None
    pts_w = cab_vtk._apply_transform(pts, transform or "")
    i0, i1, i2 = (int(x) for x in tris[cid][:3])
    n = np.cross(pts_w[i1] - pts_w[i0], pts_w[i2] - pts_w[i0])
    nn = float(np.linalg.norm(n))
    if nn < 1e-15:
        return None
    n = n / nn
    origin = pts_w[i0]
    # Grow coplanar connected set (same normal + plane)
    tri_ids = {cid}
    changed = True
    while changed:
        changed = False
        for ti, tri in enumerate(tris):
            if ti in tri_ids:
                continue
            j0, j1, j2 = (int(x) for x in tri[:3])
            tn = np.cross(pts_w[j1] - pts_w[j0], pts_w[j2] - pts_w[j0])
            tn_n = float(np.linalg.norm(tn))
            if tn_n < 1e-15:
                continue
            tn = tn / tn_n
            if abs(float(np.dot(tn, n))) < 0.98:
                continue
            if abs(float(np.dot(pts_w[j0] - origin, n))) > 1e-4:
                continue
            # adjacency by shared vertex with current set
            verts = {j0, j1, j2}
            border = set()
            for k in tri_ids:
                border.update(int(x) for x in tris[k][:3])
            if verts & border:
                tri_ids.add(ti)
                changed = True
    face_pts = []
    for ti in tri_ids:
        for vi in tris[ti][:3]:
            face_pts.append(pts_w[int(vi)])
    face_pts = np.asarray(face_pts, dtype=np.float64)
    lo_m, hi_m = face_pts.min(0), face_pts.max(0)
    direction = panel_direction_from_normal(n)
    return {
        "normal": n,
        "origin_m": origin,
        "lo_mm": lo_m * 1000.0,
        "hi_mm": hi_m * 1000.0,
        "direction": direction,
        "tri_ids": sorted(tri_ids),
    }


def panelize_part_face(model: StpreModel, cad_meshes, name: str,
                       cell_id: Optional[int] = None,
                       *, result_name: Optional[str] = None
                       ) -> Optional[str]:
    """Create a Panel on the picked face plane (M33) or largest AABB face.

    STpre: Esc after face pick panelizes Parasolid faces; sketch/pipe excluded.
    """
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return None
    kind = (getattr(info, "kind", None) or "").lower()
    if kind in ("sketch", "pipe"):
        return None
    bounds = part_world_bounds(model, name, cad_meshes)
    if bounds is None:
        return None
    lo, hi = bounds
    direction = "+Z"
    if cell_id is not None:
        meshes = {getattr(t, "name", None): t for t in (cad_meshes or [])}
        plane = face_plane_from_cell(
            meshes.get(name), int(cell_id),
            info.transform if info else "")
        if plane is not None:
            direction = plane["direction"]
            # Use picked-face extent (not whole-part AABB)
            lo, hi = plane["lo_mm"], plane["hi_mm"]
    else:
        size = hi - lo
        areas = (size[1] * size[2], size[0] * size[2], size[0] * size[1])
        ax = int(np.argmax(areas))
        direction = f"+{'XYZ'[ax]}"

    base, psz = panel_params_from_aabb(lo, hi, direction)
    import cab_parts
    pname = unique_part_name(
        model, result_name or f"{name}_panel")
    ok = cab_parts.register_primitive(
        model, name=pname, kind="panel",
        params={"base": base, "size": psz, "direction": direction},
        material="", attribute="Panel",
        color="80,180,80,255")
    if not ok:
        return None
    tess = cab_parts.panel_tess(base, psz, direction)
    tess.name = pname
    if cad_meshes is not None:
        cad_meshes.append(tess)
    return pname


def extrude_part_face(model: StpreModel, cad_meshes, name: str,
                      height_mm: float, *,
                      cell_id: Optional[int] = None,
                      orientation: Optional[str] = None,
                      displacement: bool = False,
                      result_name: str = "extrusion_1"
                      ) -> Optional[str]:
    """M33 Sweep/Face Extrusion from picked face plane (else part AABB)."""
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return None
    bounds = part_world_bounds(model, name, cad_meshes)
    if bounds is None:
        return None
    lo, hi = bounds
    direction = orientation or "+Z"
    if cell_id is not None:
        meshes = {getattr(t, "name", None): t for t in (cad_meshes or [])}
        plane = face_plane_from_cell(
            meshes.get(name), int(cell_id),
            info.transform if info else "")
        if plane is not None:
            lo, hi = plane["lo_mm"], plane["hi_mm"]
            if not orientation:
                direction = plane["direction"]
    ax = {"X": 0, "Y": 1, "Z": 2}[direction[-1]]
    sign = 1.0 if direction.startswith("+") else -1.0
    h = abs(float(height_mm))
    base = lo.copy()
    size = (hi - lo).copy()
    if sign > 0:
        base[ax] = hi[ax]
    else:
        base[ax] = lo[ax] - h
    size[ax] = h
    out = unique_part_name(model, result_name or "extrusion_1")
    el = model.add_part(name=out, kind="cube", attribute="solid")
    if el is None:
        return None
    from xml.etree.ElementTree import SubElement
    for tag, val in (
            ("base", ",".join(f"{v:.17g}" for v in base)),
            ("size", ",".join(f"{v:.17g}" for v in size)),
    ):
        c = _first(el, tag)
        if c is None:
            c = SubElement(el, tag)
            c.tail = "\n         "
        set_text(c, val)
    if displacement:
        d = np.zeros(3)
        d[ax] = h * sign
        translate_part(model, out, d)
    try:
        import cab_parts
        tess = cab_parts.cube_tess(base, size)
        tess.name = out
        if cad_meshes is not None:
            cad_meshes.append(tess)
    except Exception:
        pass
    return out


def delete_selected_faces_tess(cad_meshes, name: str,
                               cell_id: Optional[int] = None
                               ) -> int:
    """M33: remove coplanar triangle cluster (tessellation face delete).

    Returns number of triangles removed.
    """
    meshes = {getattr(t, "name", None): t for t in (cad_meshes or [])}
    tess = meshes.get(name)
    if tess is None or cell_id is None:
        return 0
    info_tf = ""
    plane = face_plane_from_cell(tess, int(cell_id), info_tf)
    if plane is None:
        return 0
    drop = set(plane["tri_ids"])
    tris = np.asarray(tess.triangles, dtype=np.int64)
    keep = [t for i, t in enumerate(tris) if i not in drop]
    if len(keep) == len(tris):
        return 0
    if not keep:
        return 0
    kept = np.asarray(keep, dtype=np.int64)
    used = np.unique(kept.ravel())
    remap = {old: i for i, old in enumerate(used)}
    pts = np.asarray(tess.points, dtype=np.float64)[used]
    tess.points = pts
    tess.triangles = np.asarray(
        [[remap[int(i)] for i in t] for t in kept], dtype=np.int64)
    return len(drop)
