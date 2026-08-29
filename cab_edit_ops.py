"""Model-side helpers for STpre [Edit] menu operations.

Geometry-heavy Parasolid ops (Boolean / Cutting / Sweep / …) are exposed as
best-effort transforms or XML registration so the GUI dialogs stay usable
without the native kernel.  Bounding-box and transform ops are exact.
"""

from __future__ import annotations

import copy
import ctypes as _ctypes
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


_XT_BODY_CACHE: dict[str, list[int]] = {}


def _receive_xt_cached(sess, xt: bytes) -> list[int]:
    """``receive_xt`` with content-hash caching (stable body tags).

    Without the cache every ``_find_body_tags`` call re-receives the same
    stream into new bodies, so face tags captured by a Preview could never
    match the body a later Delete operates on (diag 2026-08-16: tag set
    18xxx vs 32xxx across two calls on identical data).
    """
    import hashlib
    key = hashlib.md5(xt).hexdigest()
    tags = _XT_BODY_CACHE.get(key)
    if tags is None:
        tags = list(sess.expand_to_bodies(sess.receive_xt(xt)))
        _XT_BODY_CACHE[key] = tags
    return tags


def _invalidate_xt_cache(*tags) -> None:
    """Evict cached receives whose bodies were mutated in place.

    ``transform/blend/simplify/boolean`` edit the live session body, so the
    x_t bytes it was received from no longer describe it; a later lookup of
    the same member must re-receive fresh geometry instead of reusing the
    mutated tag (regression 2026-08-16: a translate test shifted the cached
    body +0.02 m and the later mirror/wrap tests resolved the shifted body).
    """
    dead = {int(t) for t in tags if t is not None}
    if not dead:
        return
    for key in [k for k, v in _XT_BODY_CACHE.items()
                if dead.intersection(v)]:
        del _XT_BODY_CACHE[key]


def _find_body_tags(model: StpreModel, archive,
                    part_a: str, part_b: str
                    ) -> tuple[Optional[int], Optional[int]]:
    """Locate live body tags for two parts across archive x_t members.

    Resolution order: (1) each part's own ``<file>`` geometry member —
    after a PK edit writes ``{part}.x_t`` back, the part points at its
    private member and must resolve to that edited body, not the shared
    import member; (2) the ``body_files`` scan, matching bodies by
    Parasolid SDL name, with unmatched single-body members assigned to
    remaining parts in order.
    """
    if archive is None:
        return None, None
    import ps_facet2_nodes as _ps
    if _ps is None:
        return None, None
    members = {m.name: m.data for m in (archive.members or [])}
    sess = _ps._get_session()
    matched: dict[str, int] = {}

    # (1) part-owned geometry members take precedence
    infos = {p.name: p for p in model.parts()}
    for name in (part_a, part_b):
        if not name or name in matched:
            continue
        info = infos.get(name)
        f_el = _first(info.elem, "file") if info is not None else None
        ref = (f_el.text or "").strip() if f_el is not None else ""
        if not ref or ref not in members:
            continue
        try:
            tags = _receive_xt_cached(sess, members[ref])
        except Exception:
            continue
        for tag in tags:
            try:
                if sess.body_name(tag) == name:
                    matched[name] = int(tag)
                    break
            except Exception:
                pass

    # (2) shared body_files scan for anything still unmatched
    bf = model.doc.root.find("body_files")
    refs = []
    if bf is not None:
        for f in bf.findall("file"):
            txt = (f.text or "").strip()
            if txt and txt in members:
                refs.append(members[txt])
    leftovers: list[int] = []
    for xt in refs:
        try:
            tags = _receive_xt_cached(sess, xt)
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
        if name and name not in matched and leftovers:
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
            member_name = f"{name}.x_t"
            cab_import.add_xt_member(archive, xt, name=member_name)
            model.add_body_file(member_name, unit="m")
            f_el = _first(el, "file")
            if f_el is not None:
                set_text(f_el, member_name)
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
            # boolean consumes the tools and mutates the target: their
            # source x_t cache entries are stale from here on
            _invalidate_xt_cache(tag_a, tag_b)
            res_tag = res_tags[0]
            tess = (sess.facet_body_adaptive(res_tag)
                    or sess.facet2(res_tag) or sess.facet_go(res_tag))
            try:
                xt = cab_ps_ops.transmit_parts([res_tag])
            except Exception:
                xt = None
            res = {"tess": tess}
        except Exception:
            # the kernel may have consumed the tools before failing: their
            # cache entries cannot be trusted either
            _invalidate_xt_cache(tag_a, tag_b)
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


def register_tess_part(model: StpreModel, cad_meshes, archive, name: str,
                       tess) -> bool:
    """Register a tessellation result as a polygon part (+ STL member)."""
    from cab_parts import PrimitivePart
    from xml.etree.ElementTree import SubElement
    file_ref = ""
    kind = "polygon"
    if archive is not None:
        import cab_import
        stl = cab_import._tris_to_stl_bytes(
            np.asarray(tess.points, dtype=np.float64),
            np.asarray(tess.triangles, dtype=np.int64), name)
        member = cab_import.add_stl_member(
            archive, stl, name=f"{name}.stl")
        file_ref = member.name
    el = model.add_part(name=name, kind=kind, attribute="solid",
                        file_ref=file_ref)
    if el is None:
        return False
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
    if cad_meshes is not None:
        cad_meshes.append(PrimitivePart(name, pts, np.asarray(
            tess.triangles, dtype=np.int64)))
    return True


def _clip_triangle(pts, tris, d, eps):
    """Clip one triangle against plane d>=0 front / d<0 back."""
    front_poly: list[np.ndarray] = []
    back_poly: list[np.ndarray] = []
    for i in range(3):
        p1 = pts[tris[i]]
        p2 = pts[tris[(i + 1) % 3]]
        d1, d2 = d[tris[i]], d[tris[(i + 1) % 3]]
        if d1 >= -eps:
            front_poly.append(p1)
        if d1 < eps:
            back_poly.append(p1)
        if (d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps):
            t = d1 / (d1 - d2)
            p = p1 + t * (p2 - p1)
            front_poly.append(p)
            back_poly.append(p)
    return front_poly, back_poly


def _fan_tris(poly: list[np.ndarray], vmap: dict,
              vlist: list[np.ndarray]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    if len(poly) < 3:
        return out
    ids = []
    for p in poly:
        key = tuple(np.round(p, 12))
        if key not in vmap:
            vmap[key] = len(vlist)
            vlist.append(p)
        ids.append(vmap[key])
    for i in range(1, len(ids) - 1):
        out.append((ids[0], ids[i], ids[i + 1]))
    return out


def _build_loops(segments: list[tuple[np.ndarray, np.ndarray]]
                 ) -> list[list[np.ndarray]]:
    """Join cut-plane segments into closed boundary loops."""
    from collections import defaultdict
    adj: dict[tuple, list[tuple]] = defaultdict(list)
    pos: dict[tuple, np.ndarray] = {}
    for p, q in segments:
        kp = tuple(np.round(p, 12))
        kq = tuple(np.round(q, 12))
        pos[kp] = p
        pos[kq] = q
        adj[kp].append(kq)
        adj[kq].append(kp)
    loops: list[list[np.ndarray]] = []
    used: set[tuple] = set()
    for start in list(adj):
        if start in used or len(adj[start]) != 2:
            continue
        loop: list[tuple] = [start]
        used.add(start)
        prev, cur = start, adj[start][0]
        guard = 0
        while cur != start and guard < 100000:
            guard += 1
            if cur in used:
                break
            used.add(cur)
            loop.append(cur)
            nxt = [k for k in adj[cur] if k != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        if cur == start and len(loop) >= 3:
            loops.append([pos[k] for k in loop])
    return loops


def _cross2d(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - \
        (b[1] - a[1]) * (c[0] - a[0])


def _point_in_tri2d(a, b, c, p) -> bool:
    d1 = _cross2d(a, b, p)
    d2 = _cross2d(b, c, p)
    d3 = _cross2d(c, a, p)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def _ear_clip(loop: list[np.ndarray], u: np.ndarray, v: np.ndarray
              ) -> list[tuple[int, int, int]]:
    pts2 = [(float(p @ u), float(p @ v)) for p in loop]
    area = 0.0
    for i in range(len(pts2)):
        x1, y1 = pts2[i]
        x2, y2 = pts2[(i + 1) % len(pts2)]
        area += x1 * y2 - x2 * y1
    if area < 0:
        pts2 = pts2[::-1]
    idx = list(range(len(pts2)))
    out: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        found = False
        m = len(idx)
        for i in range(m):
            i0, i1, i2 = idx[(i - 1) % m], idx[i], idx[(i + 1) % m]
            a, b, c = pts2[i0], pts2[i1], pts2[i2]
            if _cross2d(a, b, c) <= 1e-12:
                continue
            inside = any(
                j not in (i0, i1, i2) and
                _point_in_tri2d(a, b, c, pts2[j]) for j in idx)
            if inside:
                continue
            out.append((i0, i1, i2))
            idx.pop(i)
            found = True
            break
        if not found:
            return []
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def cut_tess_with_plane(tess, origin_m, normal) -> dict:
    """True plane cut of a tessellation into front/back shells (+ caps).

    Returns ``{"front": {points, triangles}, "back": {...},
    "capped": bool}``.  Caps are built by ear-clipping the cut loops; when a
    loop cannot be closed (e.g. multiple disjoint cut loops), the shells are
    returned open and ``capped`` is False.
    """
    pts = np.asarray(tess.points, dtype=np.float64)
    tris = np.asarray(tess.triangles, dtype=np.int64)
    n = np.asarray(normal, dtype=float)
    nn = np.linalg.norm(n)
    if nn < 1e-12:
        raise ValueError("cut plane normal must be non-zero")
    n = n / nn
    o = np.asarray(origin_m, dtype=float)
    d = (pts - o) @ n
    eps = 1e-9
    front_vmap: dict = {}
    back_vmap: dict = {}
    front_vlist: list[np.ndarray] = []
    back_vlist: list[np.ndarray] = []
    front_out: list[tuple[int, int, int]] = []
    back_out: list[tuple[int, int, int]] = []
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    coplanar: list[tuple[int, int, int]] = []
    for t in tris:
        ds = d[t]
        if np.all(np.abs(ds) <= eps):
            coplanar.append((int(t[0]), int(t[1]), int(t[2])))
            continue
        front_poly, back_poly = _clip_triangle(pts, t, d, eps)
        front_out.extend(_fan_tris(front_poly, front_vmap, front_vlist))
        back_out.extend(_fan_tris(back_poly, back_vmap, back_vlist))
        inter: list[np.ndarray] = []
        for i in range(3):
            p1 = pts[t[i]]
            p2 = pts[t[(i + 1) % 3]]
            d1, d2 = ds[i], ds[(i + 1) % 3]
            if (d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps):
                tt = d1 / (d1 - d2)
                inter.append(p1 + tt * (p2 - p1))
        if len(inter) == 2:
            segments.append((inter[0], inter[1]))
    # choose plane basis
    ref = np.array([1.0, 0.0, 0.0])
    if abs(n @ ref) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    capped = False
    loops = _build_loops(segments)
    if len(loops) == 1 and len(loops[0]) >= 3:
        loop = loops[0]
        area2 = 0.0
        pts2 = [(float(p @ u), float(p @ v)) for p in loop]
        for i in range(len(pts2)):
            x1, y1 = pts2[i]
            x2, y2 = pts2[(i + 1) % len(pts2)]
            area2 += x1 * y2 - x2 * y1
        loop_use = loop if area2 >= 0 else loop[::-1]
        clip = _ear_clip(loop_use, u, v)
        if len(clip) >= 1:
            # front cap normal must point toward -n; check orientation
            cap_area = 0.0
            for i0, i1, i2 in clip:
                cap_area += float(np.dot(
                    np.cross(loop_use[i1] - loop_use[i0],
                             loop_use[i2] - loop_use[i0]), n))
            if cap_area > 0:
                clip = [(i2, i1, i0) for i0, i1, i2 in clip]
            cap_vmap: dict = {}
            cap_vlist: list[np.ndarray] = []
            cap_tris: list[tuple[int, int, int]] = []
            for i0, i1, i2 in clip:
                ids = []
                for p in (loop_use[i0], loop_use[i1], loop_use[i2]):
                    key = tuple(np.round(p, 12))
                    if key not in cap_vmap:
                        cap_vmap[key] = len(cap_vlist)
                        cap_vlist.append(p)
                    ids.append(cap_vmap[key])
                cap_tris.append(tuple(ids))
            front_out.extend(cap_tris)
            # back cap uses the reversed orientation (+n)
            rev = [(i2, i1, i0) for i0, i1, i2 in clip]
            rev_vmap: dict = {}
            rev_vlist: list[np.ndarray] = []
            rev_tris: list[tuple[int, int, int]] = []
            for i0, i1, i2 in rev:
                ids = []
                for p in (loop_use[i0], loop_use[i1], loop_use[i2]):
                    key = tuple(np.round(p, 12))
                    if key not in rev_vmap:
                        rev_vmap[key] = len(rev_vlist)
                        rev_vlist.append(p)
                    ids.append(rev_vmap[key])
                rev_tris.append(tuple(ids))
            back_out.extend(rev_tris)
            for i0, i1, i2 in coplanar:
                for target_map, target_list, target_out, reverse in (
                        (cap_vmap, cap_vlist, front_out, False),
                        (rev_vmap, rev_vlist, back_out, True)):
                    ids = []
                    for i in ((i2, i1, i0) if reverse else (i0, i1, i2)):
                        p = pts[i]
                        key = tuple(np.round(p, 12))
                        if key not in target_map:
                            target_map[key] = len(target_list)
                            target_list.append(p)
                        ids.append(target_map[key])
                    target_out.append(tuple(ids))
            capped = True
    front_pts = np.array(front_vlist, dtype=float) if front_vlist else \
        np.zeros((0, 3))
    back_pts = np.array(back_vlist, dtype=float) if back_vlist else \
        np.zeros((0, 3))
    return {
        "front": {"points": front_pts,
                  "triangles": np.array(front_out, dtype=np.int64)
                  if front_out else np.zeros((0, 3), dtype=np.int64)},
        "back": {"points": back_pts,
                 "triangles": np.array(back_out, dtype=np.int64)
                 if back_out else np.zeros((0, 3), dtype=np.int64)},
        "capped": capped,
    }


def simplify_tess_grid(tess, tol_mm: float):
    """Vertex-clustering decimation (real simplification, not a stub)."""
    from cab_parts import PrimitivePart
    pts = np.asarray(tess.points, dtype=np.float64)
    tris = np.asarray(tess.triangles, dtype=np.int64)
    tol = float(tol_mm) / 1000.0
    if tol <= 0 or len(pts) == 0 or len(tris) == 0:
        return None
    cell = np.floor(pts / tol).astype(np.int64)
    uniq, inv = np.unique(cell, axis=0, return_inverse=True)
    new_pts = np.zeros((len(uniq), 3), dtype=np.float64)
    counts = np.zeros(len(uniq), dtype=np.int64)
    np.add.at(new_pts, inv, pts)
    np.add.at(counts, inv, 1)
    new_pts /= counts[:, None]
    nt = inv[tris]
    keep = (nt[:, 0] != nt[:, 1]) & (nt[:, 1] != nt[:, 2]) & \
        (nt[:, 0] != nt[:, 2])
    nt = nt[keep]
    if len(nt) == 0:
        return None
    return PrimitivePart(getattr(tess, "name", ""), new_pts, nt)


def convex_hull_tess(points):
    """Convex hull over a point cloud (scipy) with AABB fallback."""
    from cab_parts import PrimitivePart
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 4:
        return None
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(pts)
        return PrimitivePart("", pts, hull.simplices.astype(np.int64))
    except Exception:
        pass
    lo = pts.min(0)
    hi = pts.max(0)
    corners = np.array([
        [lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]],
        [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
        [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]],
        [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]],
    ], dtype=float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return PrimitivePart("", corners, tris)


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


def _transform_plane_to_world(normal_local, origin_local, transform: str):
    """A2: map a local plane (normal, origin) to world via the XML transform."""
    n = np.asarray(normal_local, dtype=np.float64)
    o = np.asarray(origin_local, dtype=np.float64)
    if not transform:
        return n, o
    try:
        m = np.array([float(v) for v in transform.split(",")[:16]]
                     ).reshape(4, 4)
    except (ValueError, IndexError):
        return n, o
    R = m[:3, :3]
    t = m[3, :3]
    ow = o @ R + t
    nw = n @ R
    nn = float(np.linalg.norm(nw))
    if nn > 1e-12:
        nw = nw / nn
    return nw, ow


def delete_face_pk(model: StpreModel, archive, name: str,
                   normal_world, origin_world, *,
                   heal: str = "cap") -> Optional[int]:
    """A2: PK-level face delete for [Edit Solid], matched by world plane.

    Finds the part's live body, matches the picked world plane to a PK_FACE,
    calls ``PK_FACE_delete_2`` and returns the post-delete face count, or
    ``None`` when no x_t body / match is available (caller falls back to the
    tessellation path ``delete_selected_faces_tess``).
    """
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return None
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return None
    info = next((p for p in model.parts() if p.name == name), None)
    tf = info.transform if info else ""
    sess = _ps._get_session()
    faces = sess.body_faces(tag)
    if not faces:
        return None
    n_w = np.asarray(normal_world, dtype=np.float64)
    n_w = n_w / (float(np.linalg.norm(n_w)) or 1.0)
    o_w = np.asarray(origin_world, dtype=np.float64)
    best: Optional[int] = None
    best_score = -1.0
    for ft in faces:
        pl = sess.face_plane(ft)
        if pl is None:
            continue
        fn, fo = _transform_plane_to_world(pl[0], pl[1], tf)
        dot = abs(float(np.dot(fn, n_w)))
        if dot < 0.98:
            continue
        dist = abs(float(np.dot(fo - o_w, n_w)))
        if dist > 1e-3:
            continue
        score = dot - dist * 1e3
        if score > best_score:
            best_score, best = score, int(ft)
    if best is None:
        return None
    cab_ps_ops.face_delete([best], heal=heal)
    after = sess.body_faces(tag)
    return len(after) if after else None


def _face_type_raw(sess, ft: int) -> int:
    """DEPRECATED: PK_FACE_ask_type fails (rc!=0) on every face of this
    kernel build; use facet-derived planarity via ``sess.face_plane``."""
    return 4001 if sess.face_plane(ft) is not None else 0


def _face_area(sess, ft: int) -> float:
    """Facet area of one PK_FACE (sum of its facet triangles)."""
    try:
        result = sess._facet2_call([ft])
        part = sess._decode_result(result, ft, "")
    except Exception:
        return 0.0
    if part is None:
        return 0.0
    tris = getattr(part, "triangles", None)
    pts = getattr(part, "points", None)
    if tris is None or pts is None or len(tris) == 0:
        return 0.0
    p = np.asarray(pts, dtype=np.float64)
    t = np.asarray(tris, dtype=np.int64)
    a = p[t[:, 0]]
    b = p[t[:, 1]]
    c = p[t[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() * 0.5)


def face_geometry_table(model: StpreModel, archive, name: str):
    """Per-face geometry ``(tag, type, area, plane)`` for a part's body.

    ``type`` is the PK surface class, ``area`` the facet area (local
    units, m^2) and ``plane`` ``(normal, origin)`` for planar faces
    (``None`` otherwise).  Returns ``None`` without an x_t body.
    """
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return None
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return None
    sess = _ps._get_session()
    faces = sess.body_faces(tag)
    if not faces:
        return None
    out = []
    for ft in faces:
        # PK_FACE_ask_type returns rc!=0 on this kernel build (type -1 for
        # every face), so planarity is derived from the facet plane, which
        # is verified correct (diag 2026-08-16).
        pl = sess.face_plane(ft)
        out.append({"tag": int(ft), "type": 4001 if pl is not None else 0,
                    "area": _face_area(sess, ft), "plane": pl})
    return out


def auto_faces_by_method(model: StpreModel, archive, name: str,
                         method: str) -> list[int]:
    """Part Simplification method selector (heuristic, PK topology based).

    internal_loop -> non-planar faces (holes / internal loops are
                     typically cylindrical or conical surfaces);
    thin_geometry -> planar faces under 25% of the largest face area
                     (thin-wall walls and projection faces);
    external_2d5  -> planar faces normal to the longest body axis
                     (2.5D extrusion end faces).
    """
    faces = face_geometry_table(model, archive, name)
    if not faces:
        return []
    if method == "internal_loop":
        return [f["tag"] for f in faces if f["type"] != 4001]
    planes = [f for f in faces if f["type"] == 4001 and f["plane"] is not None]
    if not planes:
        return []
    if method == "thin_geometry":
        biggest = max((f["area"] for f in planes), default=0.0)
        return [f["tag"] for f in planes if 0.0 < f["area"] < 0.25 * biggest]
    if method == "external_2d5":
        origins = np.asarray([f["plane"][1] for f in planes],
                             dtype=np.float64)
        axis = int(np.argmax(origins.max(0) - origins.min(0)))
        return [f["tag"] for f in planes
                if abs(float(f["plane"][0][axis])) > 0.98]
    return []


def simplify_part_faces_pk(model: StpreModel, archive, cad_meshes, name: str,
                           face_tags: list[int], *, heal: str = "cap"):
    """``PK_FACE_delete_2`` on selected faces; x_t member written back.

    ``heal="cap"`` (default) closes each removed region with a healing
    face — the STpre Part-Simplification semantic (hole / feature face
    removal, body stays a valid solid); the face count may stay equal,
    so ``deleted`` counts requested faces that were live before the call.
    Returns ``dict(deleted, faces_before, faces_after, tris)`` or
    ``None`` when the PK path is unavailable / nothing matched.
    """
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available() or not face_tags:
        return None
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return None
    sess = _ps._get_session()
    faces = sess.body_faces(tag) or []
    n_before = len(faces)
    live = [int(t) for t in face_tags if int(t) in set(faces)]
    if not live:
        return None
    # Delete one face per call: PK_FACE_delete_2 returns rc 525 on a
    # batch of mutually adjacent faces (slot walls), while the same faces
    # delete cleanly one at a time (diag 2026-08-16).  Cap healing
    # REPLACES the deleted face with a healing face (tag changes,
    # count stays) or merges neighbours, so liveness is re-checked every
    # step and a deletion only counts when the tag really left the set.
    deleted = 0
    for t in live:
        if t not in set(sess.body_faces(tag) or []):
            continue
        try:
            cab_ps_ops.face_delete([t], heal=heal)
        except Exception:
            continue
        if t not in set(sess.body_faces(tag) or []):
            deleted += 1
    if not deleted:
        return None
    n_after = len(sess.body_faces(tag) or [])
    try:
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        xt = None
    if xt:
        info = next((p for p in model.parts() if p.name == name), None)
        if info is not None:
            member_name = f"{name}.x_t"
            old = next((m for m in archive.members
                        if m.name == member_name), None)
            if old is not None:
                # in-place replace: repeated deletes must not pile up
                # duplicate members of the same name.
                old.data = xt
                old.cb_file = len(xt)
            else:
                cab_import.add_xt_member(archive, xt, name=member_name)
            model.add_body_file(member_name, unit="m")
            f_el = _first(info.elem, "file")
            if f_el is not None:
                set_text(f_el, member_name)
    tris = 0
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(tag)
            if tess is None:
                tess = sess.facet_body(tag)
            if tess is not None:
                tess.name = name
                tri_arr = getattr(tess, "triangles", None)
                # NOTE: no ``or []`` here — numpy truthiness raises
                # ValueError and would silently kill the mesh refresh.
                tris = int(len(tri_arr)) if tri_arr is not None else 0
                for i, t in enumerate(cad_meshes):
                    if getattr(t, "name", None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return {"deleted": deleted, "faces_before": n_before,
            "faces_after": n_after, "tris": tris}


def transform_part_pk(model: StpreModel, archive, name: str,
                      fn, *, tolerance: float = 1e-6) -> bool:
    """Apply a PK transform (fn(body_tag)) to a part's body and write x_t back.

    ``fn`` is a callable that takes the live body tag (e.g.
    ``lambda t: cab_ps_ops.body_transform_translate(t, dx, dy, dz)``).  The
    transformed body is transmitted to ``.x_t`` and the part's ``<file>`` +
    ``body_files`` member are updated so a reload shows the new geometry.
    Returns True on success.
    """
    import cab_ps_ops
    import cab_import
    from xml.etree.ElementTree import SubElement
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return False
    try:
        fn(tag)
    except Exception:
        return False
    _invalidate_xt_cache(tag)  # body moved in place
    try:
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        return False
    if not xt:
        return False
    # update the part's x_t member reference
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f"{name}.x_t"
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit="m")
    f_el = _first(el, "file")
    if f_el is not None:
        set_text(f_el, member_name)
    return True


def replace_part_from_library(model: StpreModel, name: str, entry: dict
                            ) -> bool:
    # Replace a part's attributes from a library stub (kind / attribute /
    # material / heat / temperature / base+size params).  Transform and
    # conditions stay untouched; primitive geometry regenerates from the
    # new params on the next tessellation pass (body parts keep geometry).
    from xml.etree.ElementTree import SubElement
    el = model.find_part(name)
    if el is None:
        return False

    def _set(tag, val):
        c = _first(el, tag)
        if c is None:
            c = SubElement(el, tag)
            c.tail = '\n         '
        set_text(c, str(val))

    if entry.get('kind'):
        el.set('type', str(entry['kind']))
    if entry.get('attribute'):
        _set('attribute', entry['attribute'])
    if entry.get('material'):
        _set('property', entry['material'])
    if entry.get('heat_source') is not None:
        _set('heat_source', entry['heat_source'])
    if entry.get('temperature') is not None:
        _set('temperature', entry['temperature'])
    params = entry.get('params') or {}
    base = params.get('base')
    if base:
        _set('base', ','.join(f'{float(v):.17g}' for v in base))
    size = params.get('size')
    if size:
        _set('size', ','.join(f'{float(v):.17g}' for v in size))
    return True
def _writeback_body_xt(model, archive, cad_meshes, name, tag) -> bool:
    # Shared tail: transmit tag -> member -> part file ref + mesh refresh.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    try:
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        return False
    if not xt:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    if cad_meshes is not None:
        try:
            sess = _ps._get_session()
            tess = sess.facet_body_stpre(tag)
            if tess is not None:
                tess.name = name
                for i, m in enumerate(cad_meshes):
                    if getattr(m, 'name', None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return True


def hollow_part_pk(model, archive, cad_meshes, name, thickness,
                   tolerance=1e-4) -> dict:
    """P6 shell: ``PK_BODY_hollow_2`` — thickness>0 removes the interior
    (offset=-thickness, inward), then rewrites the part's x_t body."""
    import cab_ps_ops
    import cab_p6_ops
    if archive is None or not cab_ps_ops.available():
        return {"rc": -1, "ok": False,
                "msg": "Hollow needs pskernel + a saved (x_t) body."}
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return {"rc": -1, "ok": False,
                "msg": "No B-rep body for the target part."}
    try:
        rc = cab_p6_ops.hollow_body(tag, -float(thickness), tolerance)
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"PK_BODY_hollow_2 error: {e}"}
    if rc != 0:
        return {"rc": rc, "ok": False,
                "msg": f"PK_BODY_hollow_2 rc={rc} (need a closed solid)."}
    _invalidate_xt_cache(tag)
    ok = _writeback_body_xt(model, archive, cad_meshes, name, tag)
    return {"rc": rc, "ok": ok,
            "msg": "x_t rewritten" if ok else "writeback FAILED"}


def offset_part_pk(model, archive, cad_meshes, name, offset,
                   tolerance=1e-4) -> dict:
    """P6: ``PK_BODY_offset_2`` — offset>0 grow outward, offset<0 inward."""
    import cab_ps_ops
    import cab_p6_ops
    if archive is None or not cab_ps_ops.available():
        return {"rc": -1, "ok": False,
                "msg": "Offset needs pskernel + a saved (x_t) body."}
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return {"rc": -1, "ok": False,
                "msg": "No B-rep body for the target part."}
    try:
        rc = cab_p6_ops.offset_body(tag, float(offset), tolerance)
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"PK_BODY_offset_2 error: {e}"}
    if rc != 0:
        return {"rc": rc, "ok": False,
                "msg": f"PK_BODY_offset_2 rc={rc} (check offset magnitude)."}
    _invalidate_xt_cache(tag)
    ok = _writeback_body_xt(model, archive, cad_meshes, name, tag)
    return {"rc": rc, "ok": ok,
            "msg": "x_t rewritten" if ok else "writeback FAILED"}


def replace_face_pk(model, archive, cad_meshes, name, face_tag,
                    location, normal, tolerance=1e-4) -> dict:
    """P6: ``PK_FACE_replace_surfs_2`` — flatten one face to a plane through
    ``location`` (metres) with ``normal``, then rewrite the part's x_t."""
    import cab_ps_ops
    import cab_p6_ops
    if archive is None or not cab_ps_ops.available():
        return {"rc": -1, "ok": False,
                "msg": "Replace needs pskernel + a saved (x_t) body."}
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return {"rc": -1, "ok": False,
                "msg": "No B-rep body for the target part."}
    try:
        surf = cab_ps_ops.create_plane_normal(location, normal)
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"PK_PLANE_create error: {e}"}
    try:
        rc = cab_p6_ops.replace_faces(
            tag, [int(face_tag)], [surf], [1], tolerance)
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"PK_FACE_replace_surfs_2 error: {e}"}
    if rc != 0:
        return {"rc": rc, "ok": False,
                "msg": f"PK_FACE_replace_surfs_2 rc={rc}."}
    _invalidate_xt_cache(tag)
    ok = _writeback_body_xt(model, archive, cad_meshes, name, tag)
    return {"rc": rc, "ok": ok,
            "msg": "x_t rewritten" if ok else "writeback FAILED"}


def imprint_part_pk(model, archive, cad_meshes, target, tool_name,
                    tolerance=0.0) -> dict:
    """P6: ``PK_BODY_imprint_faces_2`` — imprint every B-rep face of ``tool``
    onto ``target`` (same live session), then rewrite target's x_t."""
    import cab_ps_ops
    import cab_p6_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return {"rc": -1, "ok": False,
                "msg": "Imprint needs pskernel + saved (x_t) bodies."}
    ttag, _ = _find_body_tags(model, archive, target, "")
    tool_tag, _ = _find_body_tags(model, archive, tool_name, "")
    if ttag is None or tool_tag is None:
        return {"rc": -1, "ok": False,
                "msg": "Both target and tool need B-rep bodies (x_t)."}
    try:
        sess = _ps._get_session()
        tool_faces = list(sess.body_faces(tool_tag) or [])
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"tool face query error: {e}"}
    if not tool_faces:
        return {"rc": -1, "ok": False,
                "msg": "Tool body has no B-rep faces."}
    try:
        out = cab_p6_ops.imprint_faces(ttag, tool_faces, False, tolerance)
    except Exception as e:
        return {"rc": -1, "ok": False,
                "msg": f"PK_BODY_imprint_faces_2 error: {e}"}
    rc = int(out.get("rc", -1))
    if rc != 0:
        return {"rc": rc, "ok": False,
                "msg": f"PK_BODY_imprint_faces_2 rc={rc}."}
    _invalidate_xt_cache(ttag)
    ok = _writeback_body_xt(model, archive, cad_meshes, target, ttag)
    return {"rc": rc, "ok": ok, "n_edges": int(out.get("n_edges", 0)),
            "msg": "x_t rewritten" if ok else "writeback FAILED"}


def sheet_from_face_pk(model, archive, cad_meshes, name, face_tag):
    # R3.1e: Create sheet from edges - PK_FACE_make_sheet_body on the
    # picked face -> new sheet part + x_t member.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return None
    sess = _ps._get_session()
    try:
        sheet = cab_ps_ops.make_sheet_from_faces(sess.pk, [face_tag])
        if not sheet:
            return None
        xt = cab_ps_ops.transmit_parts([sheet])
    except Exception:
        return None
    if not xt:
        return None
    new_name = unique_part_name(model, f'{name}_sheet')
    el = model.add_part(name=new_name, kind='body',
                        attribute='sheet', file_ref='x_t')
    if el is None:
        return None
    member_name = f'{new_name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(sheet)
            if tess is not None:
                tess.name = new_name
                cad_meshes.append(tess)
        except Exception:
            pass
    return new_name


def unify_faces_pk(model, archive, cad_meshes, name, face_tag):
    # R3.1f: Unify surfaces - PK_EDGE_delete on the picked face edges.
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return 0, False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return 0, False
    sess = _ps._get_session()
    try:
        edges = cab_ps_ops.face_edges(sess.pk, face_tag)
    except Exception:
        return 0, False
    merged = 0
    for e in edges:
        try:
            if cab_ps_ops.delete_edges(sess.pk, [e]) == 0:
                merged += 1
        except Exception:
            continue
    ok = (_writeback_body_xt(model, archive, cad_meshes, name, tag)
          if merged else True)
    return merged, ok


def simplify_body_pk(model, archive, cad_meshes, name) -> bool:
    # R3.1g: Remove redundant edges - PK_BODY_simplify_geom in place.
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return False
    sess = _ps._get_session()
    try:
        if cab_ps_ops.simplify_body_geom(sess.pk, tag) != 0:
            return False
    except Exception:
        return False
    return _writeback_body_xt(model, archive, cad_meshes, name, tag)


def extract_empty_region_pk(model, archive, cad_meshes, name):
    # R3.1h: Extract empty region - region solids except the outer.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return None
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return None
    sess = _ps._get_session()
    try:
        body_vol = None
        bp = sess.facet_body_stpre(tag)
        if bp is not None and len(bp.triangles):
            body_vol = cab_ps_ops.mesh_volume_m3(bp.points, bp.triangles)
        cands = cab_ps_ops.extract_empty_regions(sess.pk, tag)
    except Exception:
        return None
    created = []
    for ct in cands:
        try:
            cp = sess.facet_body_stpre(ct)
        except Exception:
            continue
        if cp is None or not len(cp.triangles):
            continue
        vol = cab_ps_ops.mesh_volume_m3(cp.points, cp.triangles)
        if vol <= 1e-15:
            continue
        if body_vol is not None and abs(vol - body_vol) < 1e-12 * max(1.0, body_vol):
            continue
        new_name = unique_part_name(model, f'{name}_void')
        try:
            xt = cab_ps_ops.transmit_parts([ct])
        except Exception:
            continue
        if not xt:
            continue
        el = model.add_part(name=new_name, kind='body',
                            attribute='solid', file_ref='x_t')
        if el is None:
            continue
        member_name = f'{new_name}.x_t'
        cab_import.add_xt_member(archive, xt, name=member_name)
        model.add_body_file(member_name, unit='m')
        f_el = _first(el, 'file')
        if f_el is not None:
            set_text(f_el, member_name)
        if cad_meshes is not None:
            cp.name = new_name
            cad_meshes.append(cp)
        created.append(new_name)
    return created

def sweep_part_body_pk(model: StpreModel, archive, cad_meshes, name,
                       vector_m) -> bool:
    # R3.1c/d: PK_BODY_sweep in place on the part's body (sheet/wire),
    # x_t writeback + mesh refresh.  Returns False to fall back to tess.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return False
    sess = _ps._get_session()
    try:
        rc = cab_ps_ops.sweep_body(sess.pk, tag, vector_m)
        if rc != 0:
            return False
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        return False
    if not xt:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    el.set('type', 'body')
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(tag)
            if tess is not None:
                tess.name = name
                for i, m in enumerate(cad_meshes):
                    if getattr(m, 'name', None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return True


def spin_part_body_pk(model: StpreModel, archive, cad_meshes, name,
                      origin_m, axis_dir, angle_deg: float) -> bool:
    # R3.5: PK_BODY_spin in place on the part's sheet/wire body (revolve
    # to solid), x_t writeback + mesh refresh.  Returns False on failure.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return False
    sess = _ps._get_session()
    try:
        rc, n_lat, _ = cab_ps_ops.spin_body(sess.pk, tag, origin_m,
                                            axis_dir, angle_deg)
        if rc != 0:
            return False
        _invalidate_xt_cache(tag)  # spun in place
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        return False
    if not xt:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    el.set('type', 'body')
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(tag)
            if tess is not None:
                tess.name = name
                for i, m in enumerate(cad_meshes):
                    if getattr(m, 'name', None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return True

def fill_part_sheet_pk(model: StpreModel, archive, cad_meshes, name) -> bool:
    # R3.1b: Edit Solid 'Fill sheet' / 'Create cover' - heal-cap the part's
    # sheet body into a solid and write x_t back in place.
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return False
    sess = _ps._get_session()
    try:
        solid = cab_ps_ops.fill_sheet_body(sess.pk, tag)
        if not solid:
            return False
        xt = cab_ps_ops.transmit_parts([solid])
    except Exception:
        return False
    if not xt:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    el.set('type', 'body')
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(solid)
            if tess is not None:
                tess.name = name
                for i, m in enumerate(cad_meshes):
                    if getattr(m, 'name', None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return True

def sew_part_sheets_pk(model: StpreModel, archive, cad_meshes, names,
                       *, gap: float = 0.0) -> bool:
    # R3.1a: Edit Solid 'Sew sheets' - stitch N sheet/polygon parts into
    # one sheet body via PK_BODY_sew_bodies and write x_t back in place of
    # the first part (the others are removed).
    import cab_ps_ops
    import cab_import
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available() or len(names) < 2:
        return False
    tags = []
    for nm in names:
        tag, _ = _find_body_tags(model, archive, nm, '')
        if tag is None:
            return False
        tags.append(tag)
    sess = _ps._get_session()
    try:
        sewn = cab_ps_ops.sew_sheet_bodies(
            sess.pk, tags, gap=gap, allow_disjoint=True)
        if not sewn:
            return False
        xt = cab_ps_ops.transmit_parts([sewn])
    except Exception:
        return False
    if not xt:
        return False
    first = names[0]
    info = next((p for p in model.parts() if p.name == first), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{first}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    el.set('type', 'body')
    for other in names[1:]:
        model.delete_part(other)
    if cad_meshes is not None:
        try:
            tess = sess.facet_body_stpre(sewn)
            if tess is not None:
                tess.name = first
                keep = [m for m in cad_meshes
                        if getattr(m, 'name', None) not in names]
                keep.append(tess)
                cad_meshes[:] = keep
        except Exception:
            pass
    return True


def blend_part_edge_pk(model: StpreModel, archive, cad_meshes, name: str,
                       radius: float, edge_index: int = 0, *,
                       chamfer: bool = False,
                       range1: Optional[float] = None,
                       chain: bool = False,
                       tolerance: float = 1e-6,
                       variable: bool = False,
                       radii: Optional[list] = None) -> bool:
    # Blend (or chamfer) one edge of a part's body in place, write x_t back.
    # Decoded V37 blend ABI (cab_blend): PK_EDGE_set_blend_* +
    # PK_BODY_fix_blends, then PK_PART_transmit -> new .x_t member and a
    # refreshed tessellation in cad_meshes.  Returns True on success.
    import cab_ps_ops
    import cab_import
    import cab_blend
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, '')
    if tag is None:
        return False
    sess = _ps._get_session()
    edges = cab_blend.body_edges(sess.pk, tag)
    if not edges or not (0 <= edge_index < len(edges)):
        return False
    try:

        sel = [edges[edge_index]]
        if chain and not variable:
            sel = cab_blend.find_g1_edges(sess.pk, edges[edge_index])
        if variable:
            # R3.5: PK_EDGE_set_blend_variable legacy v1 ABI - the radius
            # varies along the edge; radii is [(fraction, radius_m), ...].
            profile = radii if radii else [(0.0, float(radius)),
                                           (1.0, float(range1 or radius))]
            rc, n_set = cab_blend.variable_blend_edge(
                sess.pk, edges[edge_index], profile)
        else:
            rc, n_set = cab_blend.blend_edge(
                sess.pk, sel, radius, chamfer=chamfer,
                range1=range1)
        if rc != 0 or n_set < 1:
            return False
        rc2, n_blends, _ = cab_blend.fix_blends(sess.pk, tag)
        if rc2 != 0 or n_blends < 1:
            return False
    except Exception:
        return False
    _invalidate_xt_cache(tag)  # edge blended in place
    try:
        xt = cab_ps_ops.transmit_parts([tag])
    except Exception:
        return False
    if not xt:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    el = info.elem
    member_name = f'{name}.x_t'
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit='m')
    f_el = _first(el, 'file')
    if f_el is not None:
        set_text(f_el, member_name)
    if cad_meshes is not None:
        try:
            tess = (sess.facet_body_stpre(tag)
                    or sess.facet_body(tag, facet_tol=tolerance))
            if tess is not None:
                tess.name = name
                for i, t in enumerate(cad_meshes):
                    if getattr(t, 'name', None) == name:
                        cad_meshes[i] = tess
                        break
                else:
                    cad_meshes.append(tess)
        except Exception:
            pass
    return True


def cut_part_by_plane_pk(model: StpreModel, archive, cad_meshes, name: str,
                         origin_m, normal, *,
                         result_base: Optional[str] = None
                         ) -> Optional[list[str]]:
    """A3/A4: PK-level plane cut of a part, registered as two new parts.

    ``origin_m``/``normal`` are in the body's **local** coordinates.  The two
    halves are real B-rep bodies (``PK_BODY_boolean_2``) and are transmitted to
    real ``.x_t`` members (``PK_PART_transmit``), falling back to the STL +
    polygon-part path only when transmit fails.  Returns the two new names.
    """
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    from xml.etree.ElementTree import SubElement
    if archive is None or not cab_ps_ops.available():
        return None
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return None
    sess = _ps._get_session()
    res = cab_ps_ops.cut_body_by_plane(tag, origin_m, normal)
    base = result_base or name
    created: list[str] = []
    for key, prefix in (("front", "front"), ("back", "back")):
        btag = res[key]
        tess = (sess.facet_body_adaptive(btag)
                or sess.facet2(btag) or sess.facet_go(btag))
        if tess is None or not getattr(tess, "triangles", None).size:
            continue
        new_name = unique_part_name(model, f"{base}_{prefix}")
        try:
            xt = cab_ps_ops.transmit_parts([btag])
        except Exception:
            xt = None
        if xt:
            el = model.add_part(name=new_name, kind="body",
                                attribute="solid", file_ref="x_t")
            if el is not None:
                tess.name = new_name
                pts = np.asarray(tess.points, dtype=np.float64)
                lo, hi = pts.min(0) * 1000.0, pts.max(0) * 1000.0
                for t, v in (("base", ",".join(f"{x:.17g}" for x in lo)),
                             ("size", ",".join(f"{x:.17g}" for x in (hi - lo))),
                             ):
                    c = _first(el, t)
                    if c is None:
                        c = SubElement(el, t)
                        c.tail = "\n         "
                    set_text(c, v)
                import cab_import
                member_name = f"{new_name}.x_t"
                cab_import.add_xt_member(archive, xt, name=member_name)
                model.add_body_file(member_name, unit="m")
                f_el = _first(el, "file")
                if f_el is not None:
                    set_text(f_el, member_name)
                if cad_meshes is not None:
                    cad_meshes.append(tess)
                created.append(new_name)
        else:
            if register_tess_part(model, cad_meshes, archive, new_name, tess):
                created.append(new_name)
    if created:
        model.delete_part(name)
    return created or None


# -------------------------------------------- PK-level Mirror / Align / Place

def _world_delta_to_local_m(transform: str, delta_world_mm) -> np.ndarray:
    """Convert a world translation (mm) to the body's local frame (metres)."""
    m = parse_transform(transform)
    R = m[:3, :3]
    d_w = np.asarray(delta_world_mm, dtype=np.float64).reshape(3) / 1000.0
    try:
        return np.linalg.solve(R, d_w)
    except np.linalg.LinAlgError:
        return d_w


def _world_plane_to_local(transform: str, axis: str, plane_mm: float
                          ) -> tuple[np.ndarray, np.ndarray]:
    """World mirror plane (axis + position mm) -> local (normal, origin_m)."""
    m = parse_transform(transform)
    idx = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    n_w = np.zeros(3)
    n_w[idx] = 1.0
    p_w = np.zeros(3)
    p_w[idx] = float(plane_mm) / 1000.0
    R = m[:3, :3]
    try:
        n_l = np.linalg.solve(R, n_w)
    except np.linalg.LinAlgError:
        n_l = n_w
    n_l = n_l / (float(np.linalg.norm(n_l)) or 1.0)
    p_h = np.ones(4)
    p_h[:3] = p_w
    p_l_h = np.linalg.solve(m, p_h)
    return n_l, p_l_h[:3]


def _attach_xt_member(model: StpreModel, archive, part_el, xt: bytes,
                      member_name: str) -> None:
    """Attach a transmitted x_t stream to a part element + body_files."""
    import cab_import
    cab_import.add_xt_member(archive, xt, name=member_name)
    model.add_body_file(member_name, unit="m")
    f_el = _first(part_el, "file")
    if f_el is not None:
        set_text(f_el, member_name)


def _translate_part_pk(model: StpreModel, archive, cad_meshes, name: str,
                       delta_world_mm) -> bool:
    """Apply a world translation to a part's body via PK, writing x_t back."""
    import cab_ps_ops
    if archive is None or not cab_ps_ops.available():
        return False
    tag, _ = _find_body_tags(model, archive, name, "")
    if tag is None:
        return False
    info = next((p for p in model.parts() if p.name == name), None)
    if info is None:
        return False
    d_l = _world_delta_to_local_m(info.transform, delta_world_mm)
    try:
        cab_ps_ops.body_transform_translate(
            int(tag), float(d_l[0]), float(d_l[1]), float(d_l[2]))
    except Exception:
        return False
    try:
        xt = cab_ps_ops.transmit_parts([int(tag)])
    except Exception:
        return False
    if not xt:
        return False
    _attach_xt_member(model, archive, info.elem, xt, f"{name}.x_t")
    if cad_meshes is not None:
        import ps_facet2_nodes as _ps
        sess = _ps._get_session()
        tess = (sess.facet_body_adaptive(int(tag)) or sess.facet2(int(tag))
                or sess.facet_go(int(tag)))
        if tess is not None:
            tess.name = name
            for i, t in enumerate(cad_meshes):
                if getattr(t, "name", None) == name:
                    cad_meshes[i] = tess
                    break
            else:
                cad_meshes.append(tess)
    return True


def mirror_copy_parts_pk(model: StpreModel, archive, cad_meshes,
                         names: list[str], axis: str, plane_mm: float
                         ) -> Optional[list[str]]:
    """Mirror copy via PK: clone the body, reflect about the local mirror
    plane, transmit to x_t and register as new body parts.  Returns the new
    names, or ``None`` when PK/x_t is unavailable (caller falls back to the
    XML-transform path)."""
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    if archive is None or not cab_ps_ops.available():
        return None
    sess = _ps._get_session()
    created: list[str] = []
    for name in names:
        tag, _ = _find_body_tags(model, archive, name, "")
        if tag is None:
            continue
        info = next((p for p in model.parts() if p.name == name), None)
        if info is None:
            continue
        try:
            clone = cab_ps_ops.entity_copy(int(tag))
        except Exception:
            continue
        n_l, p_l = _world_plane_to_local(info.transform, axis, plane_mm)
        try:
            cab_ps_ops.body_transform_reflect(
                clone, tuple(float(v) for v in p_l),
                tuple(float(v) for v in n_l))
        except Exception:
            continue
        try:
            xt = cab_ps_ops.transmit_parts([clone])
        except Exception:
            xt = None
        if not xt:
            continue
        new_name = unique_part_name(model, f"{name}_m")
        el = clone_part_element(model, name, new_name)  # keeps source transform
        if el is None:
            continue
        _attach_xt_member(model, archive, el, xt, f"{new_name}.x_t")
        tess = (sess.facet_body_adaptive(clone) or sess.facet2(clone)
                or sess.facet_go(clone))
        if tess is not None:
            tess.name = new_name
            if cad_meshes is not None:
                cad_meshes.append(tess)
        created.append(new_name)
    return created or None


def align_parts_pk(model: StpreModel, archive, cad_meshes,
                   part_a: str, part_b: str, axis: str, location: str
                   ) -> Optional[bool]:
    """Align Part B to Part A on one axis via PK translation of B's body."""
    ba = part_world_bounds(model, part_a, cad_meshes)
    bb = part_world_bounds(model, part_b, cad_meshes)
    if ba is None or bb is None:
        return None
    a_lo, a_hi = ba
    b_lo, b_hi = bb
    idx = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    loc = location.lower()
    if loc in ("min", "minimum"):
        delta = a_lo[idx] - b_lo[idx]
    elif loc in ("max", "maximum"):
        delta = a_hi[idx] - b_hi[idx]
    else:
        delta = 0.5 * ((a_lo[idx] + a_hi[idx]) - (b_lo[idx] + b_hi[idx]))
    d = np.zeros(3)
    d[idx] = delta
    ok = _translate_part_pk(model, archive, cad_meshes, part_b, d)
    return ok if ok else None


def place_part_pk(model: StpreModel, archive, cad_meshes,
                  move_name: str, ref_name: str,
                  offset: tuple[float, float, float] = (0, 0, 0)
                  ) -> Optional[bool]:
    """Place (center-align) a part via PK translation of its body."""
    ba = part_world_bounds(model, ref_name, cad_meshes)
    bb = part_world_bounds(model, move_name, cad_meshes)
    if ba is None or bb is None:
        return None
    a_c = 0.5 * (ba[0] + ba[1])
    b_c = 0.5 * (bb[0] + bb[1])
    delta = a_c - b_c + np.asarray(offset, dtype=np.float64)
    ok = _translate_part_pk(model, archive, cad_meshes, move_name, delta)
    return ok if ok else None


def wrap_part_pk(model: StpreModel, archive, cad_meshes, name: str,
                 *, accuracy: Optional[float] = None) -> Optional[str]:
    """Wrap a part into a convex-hull solid and write a real ``.x_t``.

    ``accuracy`` (0..1) enables STpre "Specify wrapping accuracy": the point
    cloud is vertex-clustered at ``accuracy * diag / 4`` before the hull, so a
    higher accuracy yields a coarser wrapped body.  The hull is built in
    **world** coordinates (transform applied) and registered with an identity
    transform.  Returns the new part name, or ``None`` when PK/x_t is
    unavailable (caller falls back to the STL convex-hull path).
    """
    import cab_ps_ops
    import ps_facet2_nodes as _ps
    from cab_parts import PrimitivePart
    if archive is None or not cab_ps_ops.available():
        return None
    tess = next((m for m in (cad_meshes or [])
                 if getattr(m, "name", None) == name), None)
    if tess is None or not len(getattr(tess, "points", [])):
        return None
    info = next((p for p in model.parts() if p.name == name), None)
    pts = np.asarray(tess.points, dtype=np.float64)
    pts_w = cab_vtk._apply_transform(
        pts, info.transform if info else "")
    if accuracy is not None and accuracy > 0:
        diag_mm = float(np.ptp(pts_w, axis=0).sum()) * 1000.0
        simp = simplify_tess_grid(
            PrimitivePart(name, pts_w, np.asarray(tess.triangles)),
            accuracy * diag_mm * 0.25)
        if simp is not None and len(getattr(simp, "points", [])) >= 4:
            pts_w = np.asarray(simp.points)
    try:
        tag = cab_ps_ops.convex_hull_solid(pts_w)
    except Exception:
        return None
    try:
        xt = cab_ps_ops.transmit_parts([int(tag)])
    except Exception:
        xt = None
    if not xt:
        return None
    new_name = unique_part_name(model, f"{name}_wrap")
    el = model.add_part(name=new_name, kind="body", attribute="solid",
                        file_ref="x_t", transform=IDENTITY)
    if el is None:
        return None
    _attach_xt_member(model, archive, el, xt, f"{new_name}.x_t")
    sess = _ps._get_session()
    t = (sess.facet_body_adaptive(int(tag)) or sess.facet2(int(tag))
         or sess.facet_go(int(tag)))
    if t is not None:
        t.name = new_name
        if cad_meshes is not None:
            cad_meshes.append(t)
    return new_name

def facets_to_solid_part(model: StpreModel, archive, cad_meshes, name: str,
                         *, gap: float = 1e-4) -> Optional[str]:
    """Convert a faceted part (STL / polygon) into a solid B-rep x_t part.

    Classic Parasolid route (no Convergent Modeling): one trimmed planar
    sheet body per triangle (``PK_PLANE_create`` + ``PK_BCURVE_create`` +
    ``PK_SPCURVE_create`` + ``PK_SURF_make_sheet_trimmed``), stitch with
    ``PK_BODY_sew_bodies``, then ``PK_FACE_make_solid_bodies`` per sheet.
    The resulting solid is transmitted to a real ``.x_t`` member and
    registered as a new ``body`` part.  Returns the new part name, or
    ``None`` when PK/x_t is unavailable or the mesh cannot be converted.
    """
    import cab_ps_ops
    if archive is None or not cab_ps_ops.available():
        return None
    tess = next((m for m in (cad_meshes or [])
                 if getattr(m, "name", None) == name), None)
    if tess is None or not len(getattr(tess, "points", [])):
        return None
    info = next((p for p in model.parts() if p.name == name), None)
    pts = np.asarray(tess.points, dtype=np.float64)
    pts_w = cab_vtk._apply_transform(
        pts, info.transform if info else "")
    tris = np.asarray(getattr(tess, "triangles", []), dtype=np.int64)
    if tris.size == 0:
        return None
    try:
        solids = cab_ps_ops.triangles_to_brep(pts_w, tris, gap=gap)
    except Exception:
        return None
    if not solids:
        return None
    try:
        xt = cab_ps_ops.transmit_parts([int(s) for s in solids])
    except Exception:
        xt = None
    if not xt:
        return None
    new_name = unique_part_name(model, f"{name}_solid")
    el = model.add_part(name=new_name, kind="body", attribute="solid",
                        file_ref="x_t", transform=IDENTITY)
    if el is None:
        return None
    _attach_xt_member(model, archive, el, xt, f"{new_name}.x_t")
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    t = (sess.facet_body_adaptive(int(solids[0]))
         or sess.facet2(int(solids[0])) or sess.facet_go(int(solids[0])))
    if t is not None:
        t.name = new_name
        if cad_meshes is not None:
            cad_meshes.append(t)
    return new_name

