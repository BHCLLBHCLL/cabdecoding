"""M4: meshing (Mesh -> Meshing).

Generates the ``<element>`` occupancy table from the ``<mesh_block>`` axes
and the tessellated CAD surfaces:

1. cell centres are computed on the structured grid;
2. every part is classified cell-by-cell with an even-odd ray cast (+X)
   against its triangle surface (parity per cell);
3. occupied cells are merged into i/j/k boxes and written back as
   ``<element><parts name=...><body><list>`` entries (1-based inclusive
   ``i1,i2,j1,j2,k1,k2,0,1,1``), plus the Domain ``<analysis>`` box.

v1 limitations (documented, to be refined with STpre golden data):
- cells exactly on a surface are resolved with a small epsilon;
- panel/sheet bodies (open surfaces) are not yet handled specially;
- merge is a greedy axis-aligned box merge, not STpre's exact run encoding.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

import cab_vtk
from cabxml import StpreModel


def _inside_yz(a: np.ndarray, b: np.ndarray, c: np.ndarray,
               y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """2D point-in-triangle test on the yz projection (vectorised)."""
    def cross(p, q, r):
        return (q[1] - p[1]) * (r[1] - p[1]) - \
            (q[0] - p[0]) * (r[0] - p[0])
    d1 = (b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (y - a[0])
    d2 = (c[0] - b[0]) * (z - b[1]) - (c[1] - b[1]) * (y - b[0])
    d3 = (a[0] - c[0]) * (z - c[1]) - (a[1] - c[1]) * (y - c[0])
    has_neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    has_pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(has_neg & has_pos)


def classify_part_cells(xc: np.ndarray, yc: np.ndarray, zc: np.ndarray,
                        pts: np.ndarray, tris: np.ndarray,
                        cell_range: Optional[tuple[int, int, int, int, int, int]]
                        = None, samples: str = "center") -> np.ndarray:
    """Even-odd +X ray cast of one closed part over the cell grid.

    ``xc/yc/zc`` are cell centres (metres).  Returns a bool mask of shape
    ``(len(xc), len(yc), len(zc))``.
    """
    if samples == "corners":
        ni, nj, nk = len(xc), len(yc), len(zc)
        votes = np.zeros((ni, nj, nk), dtype=np.int32)
        hx = np.zeros(ni)
        hy = np.zeros(nj)
        hz = np.zeros(nk)
        hx[1:-1] = (xc[2:] - xc[:-2]) / 4.0
        hy[1:-1] = (yc[2:] - yc[:-2]) / 4.0
        hz[1:-1] = (zc[2:] - zc[:-2]) / 4.0
        if ni > 1:
            hx[0] = hx[1] if ni > 2 else (xc[1] - xc[0]) / 2.0
            hx[-1] = hx[-2] if ni > 2 else (xc[-1] - xc[-2]) / 2.0
        if nj > 1:
            hy[0] = hy[1] if nj > 2 else (yc[1] - yc[0]) / 2.0
            hy[-1] = hy[-2] if nj > 2 else (yc[-1] - yc[-2]) / 2.0
        if nk > 1:
            hz[0] = hz[1] if nk > 2 else (zc[1] - zc[0]) / 2.0
            hz[-1] = hz[-2] if nk > 2 else (zc[-1] - zc[-2]) / 2.0
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    votes += classify_part_cells(
                        xc + sx * hx, yc + sy * hy, zc + sz * hz,
                        pts, tris, cell_range=cell_range,
                        samples="center").astype(np.int32)
        return votes >= 5
    ni, nj, nk = len(xc), len(yc), len(zc)
    mask = np.zeros((ni, nj, nk), dtype=np.int32)
    if tris is None or len(tris) == 0 or len(pts) == 0:
        return mask.astype(bool)
    i0, i1, j0, j1, k0, k1 = cell_range or (0, ni - 1, 0, nj - 1, 0, nk - 1)
    i0 = max(0, i0); i1 = min(ni - 1, i1)
    j0 = max(0, j0); j1 = min(nj - 1, j1)
    k0 = max(0, k0); k1 = min(nk - 1, k1)
    if i0 > i1 or j0 > j1 or k0 > k1:
        return mask.astype(bool)
    tri = pts[tris]  # (T,3,3)
    tmin = tri.min(axis=1)
    tmax = tri.max(axis=1)
    eps = 1e-10
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        if abs(n[0]) < 1e-12:
            continue  # ray (+X) parallel to the triangle plane
        # candidate j/k from the yz bbox, i from centres left of tmax x
        jj0 = max(j0, int(np.searchsorted(yc, tmin[t, 1], "left")))
        jj1 = min(j1, int(np.searchsorted(yc, tmax[t, 1], "right")) - 1)
        kk0 = max(k0, int(np.searchsorted(zc, tmin[t, 2], "left")))
        kk1 = min(k1, int(np.searchsorted(zc, tmax[t, 2], "right")) - 1)
        ii1 = min(i1, int(np.searchsorted(xc, tmax[t, 0], "right")) - 1)
        if jj0 > jj1 or kk0 > kk1 or ii1 < i0:
            continue
        Y, Z = np.meshgrid(yc[jj0:jj1 + 1], zc[kk0:kk1 + 1],
                           indexing="ij")
        # Perturb the ray origin slightly so rays that pass exactly through a
        # shared triangle edge (a common case on uniform grids) are counted
        # by exactly one of the two adjacent triangles.
        scale = max(float(zc[-1] - zc[0]), 1e-12)
        Y = Y + 1e-11 * scale
        Z = Z + 2e-11 * scale
        inside = _inside_yz(
            np.array([a[1], a[2]]), np.array([b[1], b[2]]),
            np.array([c[1], c[2]]), Y, Z)
        # x on the triangle plane at (y,z): a + (n_y*(y-a_y)+n_z*(z-a_z))/(-n_x)
        x_int = a[0] + (n[1] * (Y - a[1]) + n[2] * (Z - a[2])) / (-n[0])
        for i in range(i0, ii1 + 1):
            # samples exactly on the surface count as inside (boundary cells)
            hit = inside & (xc[i] < x_int + eps)
            if hit.any():
                mask[i, jj0:jj1 + 1, kk0:kk1 + 1] ^= hit
    return mask.astype(bool)


def _merge_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """Greedy merge of occupied cells into 1-based inclusive boxes."""
    boxes: list[tuple[int, int, int, int, int, int]] = []
    ni, nj, nk = mask.shape
    for j in range(nj):
        for k in range(nk):
            i = 0
            while i < ni:
                if not mask[i, j, k]:
                    i += 1
                    continue
                i2 = i
                while i2 + 1 < ni and mask[i2 + 1, j, k]:
                    i2 += 1
                boxes.append((i, i2, j, j, k, k))
                i = i2 + 1
    changed = True
    while changed:
        changed = False
        merged: list[tuple[int, int, int, int, int, int]] = []
        used = [False] * len(boxes)
        for x in range(len(boxes)):
            if used[x]:
                continue
            cur = boxes[x]
            for y in range(x + 1, len(boxes)):
                if used[y]:
                    continue
                o = boxes[y]
                # merge along j
                if (cur[0] == o[0] and cur[1] == o[1]
                        and cur[4] == o[4] and cur[5] == o[5]
                        and abs(cur[3] - o[2]) <= 1
                        and (cur[2] <= o[3] + 1 and o[2] <= cur[3] + 1)):
                    cur = (cur[0], cur[1], min(cur[2], o[2]),
                           max(cur[3], o[3]), cur[4], cur[5])
                    used[y] = True
                    changed = True
                elif (cur[0] == o[0] and cur[1] == o[1]
                      and cur[2] == o[2] and cur[3] == o[3]
                      and abs(cur[5] - o[4]) <= 1
                      and (cur[4] <= o[5] + 1 and o[4] <= cur[5] + 1)):
                    cur = (cur[0], cur[1], cur[2], cur[3],
                           min(cur[4], o[4]), max(cur[5], o[5]))
                    used[y] = True
                    changed = True
            merged.append(cur)
            used[x] = True
        boxes = merged
    return [(a + 1, b + 1, c + 1, d + 1, e + 1, f + 1)
            for a, b, c, d, e, f in boxes]


def classify_cells(axes_mm: dict[str, list[float]], parts: list,
                   transforms: Optional[dict[str, str]] = None,
                   progress: Optional[Callable[[int, int], None]] = None
                   , samples: str = "center"
                   ) -> tuple[list[tuple[int, int, int, int, int, int]],
                              dict[str, list[tuple[int, int, int, int, int, int]]]]:
    """Classify every part against the structured grid.

    Returns ``(analysis_box, part_boxes)``; boxes are 1-based inclusive
    ``(i1,i2,j1,j2,k1,k2)``.  ``parts`` are TessPart-like objects with
    ``.name/.points/.triangles`` in metres.
    """
    x = np.asarray(axes_mm.get("x", []), float) / 1000.0
    y = np.asarray(axes_mm.get("y", []), float) / 1000.0
    z = np.asarray(axes_mm.get("z", []), float) / 1000.0
    if len(x) < 2 or len(y) < 2 or len(z) < 2:
        raise ValueError("mesh_block needs at least 2 points per axis")
    xc = 0.5 * (x[:-1] + x[1:])
    yc = 0.5 * (y[:-1] + y[1:])
    zc = 0.5 * (z[:-1] + z[1:])
    ni, nj, nk = len(xc), len(yc), len(zc)
    transforms = transforms or {}
    part_boxes: dict[str, list[tuple[int, int, int, int, int, int]]] = {}
    for idx, part in enumerate(parts):
        pts = np.asarray(part.points, dtype=np.float64)
        tris = np.asarray(part.triangles, dtype=np.int64)
        if len(pts) == 0 or len(tris) == 0:
            continue
        pts = cab_vtk._apply_transform(
            pts, transforms.get(part.name, ""))
        lo = pts.min(0)
        hi = pts.max(0)
        i0 = max(0, int(np.searchsorted(xc, lo[0], "left")))
        i1 = min(ni - 1, int(np.searchsorted(xc, hi[0], "right")) - 1)
        j0 = max(0, int(np.searchsorted(yc, lo[1], "left")))
        j1 = min(nj - 1, int(np.searchsorted(yc, hi[1], "right")) - 1)
        k0 = max(0, int(np.searchsorted(zc, lo[2], "left")))
        k1 = min(nk - 1, int(np.searchsorted(zc, hi[2], "right")) - 1)
        if i0 > i1 or j0 > j1 or k0 > k1:
            continue
        mask = classify_part_cells(
            xc, yc, zc, pts, tris,
            cell_range=(i0, i1, j0, j1, k0, k1), samples=samples)
        if mask.any():
            part_boxes[part.name] = _merge_boxes(mask)
        if progress is not None:
            progress(idx + 1, len(parts))
    analysis_box = (1, ni, 1, nj, 1, nk)
    return analysis_box, part_boxes


def apply_elements(model: StpreModel, analysis_name: str,
                   analysis_box: tuple[int, int, int, int, int, int],
                   part_boxes: dict[str, list[tuple[int, int, int, int, int, int]]]
                   ) -> None:
    """Write the ``<element>`` section (replaces an existing one)."""
    import xml.etree.ElementTree as ET

    old = model.doc.root.find("element")
    if old is not None:
        model.doc.root.remove(old)
    el = ET.Element("element")
    el.tail = "\n"
    an = ET.SubElement(el, "analysis")
    an.attrib["name"] = analysis_name
    an.tail = "\n   "
    body = ET.SubElement(an, "body")
    body.attrib["num"] = "1"
    body.tail = "\n      "
    lst = ET.SubElement(body, "list")
    lst.attrib["no"] = "1"
    lst.text = " " + ",".join(str(v) for v in analysis_box) + " "
    lst.tail = "\n      "
    for name, boxes in part_boxes.items():
        p = ET.SubElement(el, "parts")
        p.attrib["name"] = name
        p.tail = "\n   "
        pb = ET.SubElement(p, "body")
        pb.attrib["num"] = str(len(boxes))
        pb.tail = "\n      "
        for n, box in enumerate(boxes, start=1):
            l = ET.SubElement(pb, "list")
            l.attrib["no"] = str(n)
            l.text = " " + ",".join(str(v) for v in box) + " "
            l.tail = "\n      "
    model.doc.root.append(el)


def update_part_elements(model: StpreModel, part_name: str,
                         boxes: list[tuple[int, int, int, int, int, int]]
                         ) -> bool:
    """Create/replace the ``<element>/<parts name=...>`` entry of one part.

    Used by [Meshing of specified part] (Gridding dialog, Others tab).
    Returns False when no ``<element>`` section exists yet (run full
    Meshing first).
    """
    import xml.etree.ElementTree as ET

    el = model.elements()
    if el is None:
        return False
    for parts in el.findall("parts"):
        if parts.attrib.get("name") == part_name:
            el.remove(parts)
    p = ET.SubElement(el, "parts")
    p.attrib["name"] = part_name
    p.tail = "\n   "
    pb = ET.SubElement(p, "body")
    pb.attrib["num"] = str(len(boxes))
    pb.tail = "\n      "
    for n, box in enumerate(boxes, start=1):
        l = ET.SubElement(pb, "list")
        l.attrib["no"] = str(n)
        l.text = " " + ",".join(str(v) for v in box) + " "
        l.tail = "\n      "
    return True


def cell_mask_from_boxes(ni: int, nj: int, nk: int,
                         boxes: list[list[int]]) -> np.ndarray:
    """0-based boolean occupancy mask of 1-based inclusive i/j/k boxes."""
    mask = np.zeros((ni, nj, nk), dtype=bool)
    for b in boxes:
        if len(b) < 6:
            continue
        i0, i1, j0, j1, k0, k1 = [int(v) for v in b[:6]]
        i0 = max(0, i0 - 1); i1 = min(ni - 1, i1 - 1)
        j0 = max(0, j0 - 1); j1 = min(nj - 1, j1 - 1)
        k0 = max(0, k0 - 1); k1 = min(nk - 1, k1 - 1)
        if i0 <= i1 and j0 <= j1 and k0 <= k1:
            mask[i0:i1 + 1, j0:j1 + 1, k0:k1 + 1] = True
    return mask


def _boxes_from_mask(mask: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """Merge an occupancy mask back into 1-based inclusive boxes."""
    return _merge_boxes(mask)


def toggle_cells_effective(model: StpreModel, part_name: str,
                           cells: list[tuple[int, int, int]],
                           effective: bool) -> int:
    """Add/remove individual cells (1-based i/j/k) to/from a part's elements.

    Returns the number of box-list entries of the part after the edit
    (0 when the part has no ``<element>`` entry and cells were removed).
    Used by [Mesh] - [Editing Mesh] (-> Effective / -> Ineffective).
    """
    axes = model.mesh_axes()
    ni = max(len(axes.get("x", [])), 1) - 1
    nj = max(len(axes.get("y", [])), 1) - 1
    nk = max(len(axes.get("z", [])), 1) - 1
    if ni < 1 or nj < 1 or nk < 1:
        return 0
    boxes = [list(b) for b in model.part_boxes(part_name)]
    mask = cell_mask_from_boxes(ni, nj, nk, boxes)
    for (i, j, k) in cells:
        if 1 <= i <= ni and 1 <= j <= nj and 1 <= k <= nk:
            mask[i - 1, j - 1, k - 1] = effective
    new_boxes = _boxes_from_mask(mask)
    update_part_elements(model, part_name, new_boxes)
    return len(new_boxes)


def classify_interferences(model: StpreModel, max_gap: int = 2
                           ) -> list[tuple[str, str, str]]:
    """Element-level interference classification of every part pair.

    Statuses match the STpre [Checking Parts Interferences] dialog:

    - ``Interference`` — index boxes overlap (share at least one cell);
    - ``Contact``      — boxes touch on a face (no shared cell, but faces
      are adjacent in index space);
    - ``Separation``   — boxes are within ``max_gap`` cells of each other
      (close enough that STpre reports a separation/contact candidate).

    Shape-level geometry (CAD surfaces) is not resolved here; the element
    occupancy table is used as the part shape (phase-1 approximation).
    """
    el = model.elements()
    if el is None:
        return []
    boxes: dict[str, list[list[int]]] = {}
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        if name:
            b = model.part_boxes(name)
            if b:
                boxes[name] = b

    def overlap(a: list[int], b: list[int]) -> bool:
        # strict: sharing only a face (<= on one axis) is a Contact, not an
        # Interference (the shared face does not consume any cells)
        return all(a[i] < b[i + 1] and b[i] < a[i + 1] for i in (0, 2, 4))

    def contact(a: list[int], b: list[int]) -> bool:
        """Face adjacency: no axis leaves a gap (touch or shared face)."""
        for i in (0, 2, 4):
            if max(a[i] - b[i + 1] - 1, b[i] - a[i + 1] - 1, 0) > 0:
                return False
        return True

    def gap(a: list[int], b: list[int]) -> int:
        g = 0
        for i in (0, 2, 4):
            g = max(g, max(a[i] - b[i + 1] - 1, b[i] - a[i + 1] - 1, 0))
        return g

    out: list[tuple[str, str, str]] = []
    keys = sorted(boxes)
    for i, na in enumerate(keys):
        for nb in keys[i + 1:]:
            if any(overlap(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Interference"))
                continue
            if any(contact(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Contact"))
                continue
            if any(gap(ba, bb) <= max_gap
                   for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Separation"))
    return out


def find_interferences(model: StpreModel) -> list[tuple[str, str]]:
    """Pairs of parts whose ``element`` index boxes overlap (AABB test).

    Used by the Gridding dialog [Reconstruct] button: interference check
    between meshed parts, like STpre's [List of Parts Interferences after
    Meshing].
    """
    el = model.elements()
    if el is None:
        return []
    import xml.etree.ElementTree as ET  # noqa: F401
    boxes: dict[str, list[list[int]]] = {}
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        if name:
            b = model.part_boxes(name)
            if b:
                boxes[name] = b

    def overlap(a: list[int], b: list[int]) -> bool:
        return all(a[i] <= b[i + 1] and b[i] <= a[i + 1] for i in (0, 2, 4))

    out: list[tuple[str, str]] = []
    keys = sorted(boxes)
    for i, na in enumerate(keys):
        for nb in keys[i + 1:]:
            if any(overlap(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb))
    return out


def resolve_interferences(model: StpreModel) -> int:
    """Trim overlapping cells from lower-priority parts (tree order wins).

    Cell-level resolution: for every interfering pair, the later part's
    boxes are clipped against the earlier part's boxes axis by axis.
    Returns the number of part entries changed.
    """
    import xml.etree.ElementTree as ET

    el = model.elements()
    if el is None:
        return 0
    order = [p.name for p in model.parts()]
    prio = {n: i for i, n in enumerate(order)}
    entries: list[tuple[str, ET.Element, list[list[int]]]] = []
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        body = parts.find("body")
        if body is None:
            continue
        boxes = [[int(x) for x in lst.text.split(",")]
                 for lst in body.findall("list") if lst.text]
        # unregistered parts keep element-section order after real parts
        prio.setdefault(name, len(order) + len(entries))
        entries.append((name, body, boxes))
    changed = 0

    def clip(box: list[int], other: list[int]) -> list[list[int]]:
        """Subtract ``other`` from ``box`` -> up to 6 residual boxes.

        Exact axis-aligned subtraction: the slabs protruding outside
        ``other`` along each axis, with the overlap core dropped.
        """
        if not all(box[i] <= other[i + 1] and other[i] <= box[i + 1]
                   for i in (0, 2, 4)):
            return [box]
        x0, x1 = box[0], box[1]
        y0, y1 = box[2], box[3]
        z0, z1 = box[4], box[5]
        ox0, ox1 = other[0], other[1]
        oy0, oy1 = other[2], other[3]
        oz0, oz1 = other[4], other[5]
        res: list[list[int]] = []
        # x slabs outside other
        if x0 < ox0:
            res.append([x0, ox0 - 1, y0, y1, z0, z1])
        if x1 > ox1:
            res.append([ox1 + 1, x1, y0, y1, z0, z1])
        xa, xb = max(x0, ox0), min(x1, ox1)
        # y slabs outside other (inside x overlap)
        if y0 < oy0:
            res.append([xa, xb, y0, oy0 - 1, z0, z1])
        if y1 > oy1:
            res.append([xa, xb, oy1 + 1, y1, z0, z1])
        ya, yb = max(y0, oy0), min(y1, oy1)
        # z slabs outside other (inside x and y overlap)
        if z0 < oz0:
            res.append([xa, xb, ya, yb, z0, oz0 - 1])
        if z1 > oz1:
            res.append([xa, xb, ya, yb, oz1 + 1, z1])
        return [b for b in res
                if b[0] <= b[1] and b[2] <= b[3] and b[4] <= b[5]]

    fixed: dict[str, list[list[int]]] = {}
    for name, _body, boxes in entries:
        cur = [list(b) for b in boxes]
        for other, _obody, oboxes in entries:
            if prio.get(other, 0) >= prio.get(name, 0):
                continue
            for ob in oboxes:
                nxt: list[list[int]] = []
                for b in cur:
                    nxt.extend(clip(b, ob))
                cur = nxt
        fixed[name] = [b for b in cur if b[0] <= b[1] and b[2] <= b[3]
                       and b[4] <= b[5]]
    for name, body, boxes in entries:
        if fixed.get(name) == boxes:
            continue
        for lst in list(body):
            body.remove(lst)
        body.attrib["num"] = str(len(fixed[name]))
        for n, box in enumerate(fixed[name], start=1):
            l = ET.SubElement(body, "list")
            l.attrib["no"] = str(n)
            l.text = " " + ",".join(str(v) for v in box) + " "
            l.tail = "\n      "
        changed += 1
    return changed
