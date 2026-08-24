"""M1: File->Import support for cab_gui.

Imports Parasolid ``.x_t`` files into the open project:

1. ``PK_PART_receive`` loads the bodies into the shared pskernel session;
2. each body is tessellated with the STpre-same ``PK_TOPOL_facet_2`` table
   path (adaptive per-face local tolerances when available);
3. the raw ``.x_t`` file is appended to the archive as a *separate* member
   (``<project>_import_N.x_t``) and registered in ``<body_files>`` - keeping
   every transmit stream individually valid, unlike byte-level concatenation;
4. ``<parts type="body">`` entries are appended for each imported body.

The GUI load path tessellates every ``.x_t`` member, so imported geometry
survives a save/reload round-trip.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from cab_container import CabArchive, CabMember
from cabxml import StpreModel

try:
    import ps_facet2_nodes as _ps_facet2
except Exception:  # pragma: no cover - headless / missing Cradle
    _ps_facet2 = None


@dataclass
class ImportedBody:
    """One imported body: display mesh plus the session body tag."""

    name: str
    tag: int
    tess: object          # ps_facet2_nodes.TessPart
    transform: Optional[tuple[float, ...]] = None


def parse_stl_bytes(raw: bytes):
    """Parse text or binary STL into ``(points, triangles)`` (metres)."""
    n = None
    if len(raw) >= 84 and (len(raw) - 84) % 50 == 0:
        n = struct.unpack_from("<I", raw, 80)[0]
    if n is not None and 84 + 50 * n == len(raw):
        tris = []
        for i in range(n):
            off = 84 + 50 * i
            tris.append(struct.unpack_from("<9f", raw, off + 12))
        pts = np.asarray(tris, dtype=np.float64).reshape(-1, 3)
        uniq, inv = np.unique(np.round(pts, 9), axis=0, return_inverse=True)
        return uniq, inv.reshape(-1, 3).astype(np.int64)
    text = raw.decode("latin-1", "replace")
    pts: list[tuple[float, float, float]] = []
    index: dict[tuple, int] = {}
    tris: list[list[int]] = []
    for facet in re.split(r"(?i)\bfacet\b", text)[1:]:
        verts = re.findall(
            r"(?i)vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)",
            facet)
        if len(verts) < 3:
            continue
        tri = []
        for x, y, z in verts[:3]:
            key = (round(float(x), 9), round(float(y), 9),
                   round(float(z), 9))
            if key not in index:
                index[key] = len(pts)
                pts.append(key)
            tri.append(index[key])
        tris.append(tri)
    if not tris:
        raise ValueError("no STL facets found")
    return (np.asarray(pts, dtype=np.float64),
            np.asarray(tris, dtype=np.int64))


def import_stl_bytes(raw: bytes, name: str = "stl_part",
                     **kw) -> list[ImportedBody]:
    """Import an STL file as a polygon body (native parse)."""
    if not available():
        raise RuntimeError("Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    pts, tris = parse_stl_bytes(raw)
    part = _ps_facet2.TessPart(
        name=name, points=pts, triangles=tris.astype(np.int32), tag=0)
    return [ImportedBody(name=name, tag=0, tess=part)]


def import_stl_file(path: str | Path, **kw) -> list[ImportedBody]:
    path = Path(path)
    return import_stl_bytes(path.read_bytes(), name=path.stem, **kw)


def import_step_file(path: str | Path, **kw) -> list[ImportedBody]:
    """Import STEP (.step/.stp) via OpenCascade (OCC) tessellation."""
    bodies, _raw, _fmt = import_file_with_payload(path, **kw)
    return bodies


def import_sat_file(path: str | Path, **kw) -> list[ImportedBody]:
    """Import ACIS SAT (.sat/.sab) via OpenCascade (OCC) tessellation."""
    bodies, _raw, _fmt = import_file_with_payload(path, **kw)
    return bodies


def import_file(path: str | Path, **kw) -> list[ImportedBody]:
    """Import by extension: x_t / STL (native) / STEP / SAT (converter)."""
    bodies, _raw, _fmt = import_file_with_payload(path, **kw)
    return bodies


def import_file_with_payload(path: str | Path, **kw
                             ) -> tuple[list[ImportedBody], bytes, str]:
    """Like :func:`import_file` but also returns the raw payload and the
    member format (``xt`` | ``stl``) for cab persistence."""
    suffix = Path(path).suffix.lower()
    if suffix in (".x_t", ".xmt_txt"):
        raw = Path(path).read_bytes()
        return import_xt_bytes(raw, **kw), raw, "xt"
    if suffix == ".stl":
        raw = Path(path).read_bytes()
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix in (".step", ".stp"):
        import cab_occ
        pts, tris = cab_occ.step_to_triangles(Path(path))
        raw = cab_occ.triangles_to_stl(
            pts, tris, name=Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix in (".sat", ".sab"):
        import cab_occ
        pts, tris = cab_occ.sat_to_triangles(Path(path))
        raw = cab_occ.triangles_to_stl(
            pts, tris, name=Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix == ".nas":
        pts, tris, _props = parse_nas_bytes(Path(path).read_bytes())
        raw = _tris_to_stl_bytes(pts, tris, Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix == ".obj":
        pts, tris = parse_obj_file(Path(path))
        raw = _tris_to_stl_bytes(pts, tris, Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix == ".dxf":
        pts, tris = parse_dxf_meshish(Path(path))
        raw = _tris_to_stl_bytes(pts, tris, Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    if suffix == ".mdl":
        # Cradle MDL: treat as text STL-like / fallback OBJ vertices
        try:
            pts, tris = parse_obj_file(Path(path))
        except Exception:
            raise ValueError(
                "MDL import requires OBJ-compatible vertex data "
                "(native Cradle MDL parser not bundled)")
        raw = _tris_to_stl_bytes(pts, tris, Path(path).stem)
        return import_stl_bytes(raw, name=Path(path).stem, **kw), raw, "stl"
    raise ValueError(f"unsupported geometry format: {suffix}")


def parse_obj_file(path: Path):
    """Minimal Wavefront OBJ → points/triangles (metres if file in m)."""
    verts: list[list[float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            idx = []
            for tok in line.split()[1:]:
                i = int(tok.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            if len(idx) >= 3:
                for k in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[k], idx[k + 1]])
    if not faces:
        raise ValueError("no OBJ faces found")
    return (np.asarray(verts, dtype=np.float64),
            np.asarray(faces, dtype=np.int64))


def parse_dxf_meshish(path: Path):
    """Very small DXF reader: 3DFACE entities → triangles (mm→m)."""
    text = path.read_text(encoding="latin-1", errors="replace")
    lines = text.splitlines()
    faces = []
    i = 0
    while i < len(lines):
        if lines[i].strip().upper() == "3DFACE":
            coords = {}
            i += 1
            while i + 1 < len(lines) and lines[i].strip() not in (
                    "0", "ENDSEC"):
                try:
                    code = int(lines[i].strip())
                    val = float(lines[i + 1].strip())
                except ValueError:
                    i += 1
                    continue
                coords[code] = val
                i += 2
            pts = []
            for base in (10, 11, 12, 13):
                if base in coords and base + 10 in coords and base + 20 in coords:
                    pts.append([coords[base] / 1000.0,
                                coords[base + 10] / 1000.0,
                                coords[base + 20] / 1000.0])
            if len(pts) >= 3:
                faces.append(pts[:3])
                if len(pts) == 4:
                    faces.append([pts[0], pts[2], pts[3]])
            continue
        i += 1
    if not faces:
        raise ValueError("no DXF 3DFACE entities found")
    arr = np.asarray(faces, dtype=np.float64).reshape(-1, 3)
    uniq, inv = np.unique(np.round(arr, 9), axis=0, return_inverse=True)
    return uniq, inv.reshape(-1, 3).astype(np.int64)


def _nas_split(line: str) -> list:
    """Split a Nastran bulk-data line into field tokens.

    Handles free-field (comma separated, blanks as empty fields) and fixed
    small-field (8-column) layouts.  Fixed-format cards always left-justify
    the card name in columns 1-8, so plain whitespace splitting works for
    the usual padded layouts; a fixed-width fallback covers tightly packed
    lines.
    """
    s = line.rstrip("\n").rstrip("\r")
    if "," in s:
        return [f.strip() for f in s.split(",")]
    toks = s.split()
    if len(toks) > 1 or len(s) <= 8:
        return toks
    return [s[i:i + 8].strip() for i in range(0, len(s), 8)]


def _nas_float(s: str) -> float:
    """Parse a Nastran number, tolerating D exponent and no-E scientific
    notation (``1.0D+05`` / ``1.0+05``)."""
    s = s.strip().replace('D', 'E').replace('d', 'e')
    if 'e' not in s and 'E' not in s and len(s) >= 3 \
            and s[-3] in '+-' and s[-2:].isdigit():
        s = s[:-3] + 'E' + s[-3:]
    return float(s)


def parse_nas_bytes(raw: bytes):
    """Parse Nastran bulk-data (.nas/.bdf) into a triangle mesh (metres).

    ``GRID`` cards define nodes; ``CTRIA3``/``CTRIAR`` and ``CQUAD4``/
    ``CQUADR`` elements become triangles (quads split along the diagonal).
    ``PSHELL`` property cards are collected so the ``pid -> mid`` material
    map can drive part materials later.  Comment lines (``$``) and the
    ``BEGIN BULK`` / ``ENDDATA`` delimiters are honoured.

    Returns ``(points, triangles, props)`` where ``props`` maps property id
    to material id (an empty dict when no PSHELL cards are present).  Only
    nodes referenced by an element are kept, so stray GRID cards are
    ignored.
    """
    text = raw.decode("latin-1", "replace")
    points: dict[int, tuple[float, float, float]] = {}
    tris: list[tuple[int, int, int]] = []
    props: dict[int, int] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("$"):
            continue
        up = s.upper()
        if up.startswith("ENDDATA") or up.startswith("END BULK"):
            break
        if up.startswith("BEGIN BULK"):
            continue
        fields = _nas_split(line)
        if not fields:
            continue
        card = fields[0].upper()
        if card == "GRID" and len(fields) >= 5:
            try:
                gid = int(fields[1])
                xyz = (_nas_float(fields[2]), _nas_float(fields[3]),
                       _nas_float(fields[4]))
            except ValueError:
                continue
            points[gid] = xyz
        elif card == "PSHELL" and len(fields) >= 3:
            try:
                props[int(fields[1])] = int(fields[2])
            except ValueError:
                continue
        elif card in ("CTRIA3", "CTRIAR") and len(fields) >= 6:
            try:
                g = tuple(int(fields[i]) for i in (3, 4, 5))
            except ValueError:
                continue
            tris.append(g)
        elif card in ("CQUAD4", "CQUADR") and len(fields) >= 7:
            try:
                g = tuple(int(fields[i]) for i in (3, 4, 5, 6))
            except ValueError:
                continue
            tris.append((g[0], g[1], g[2]))
            tris.append((g[0], g[2], g[3]))
    if not points or not tris:
        raise ValueError("no Nastran GRID/CTRIA3/CQUAD4 data found")
    used = {g for tri in tris for g in tri}
    ids = [i for i in points if i in used]
    remap = {old: new for new, old in enumerate(ids)}
    pts = np.asarray([points[i] for i in ids], dtype=np.float64)
    tris_arr = np.asarray([[remap[g] for g in tri] for tri in tris],
                          dtype=np.int64)
    return pts, tris_arr, props


def import_nas_bytes(raw: bytes, name: str = "nas_part",
                     **kw) -> list[ImportedBody]:
    """Import Nastran bulk-data bytes as a polygon body (native parse)."""
    if not available():
        raise RuntimeError("Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    pts, tris, _props = parse_nas_bytes(raw)
    part = _ps_facet2.TessPart(
        name=name, points=pts, triangles=tris.astype(np.int32), tag=0)
    return [ImportedBody(name=name, tag=0, tess=part)]


def import_nas_file(path: str | Path, **kw) -> list[ImportedBody]:
    path = Path(path)
    return import_nas_bytes(path.read_bytes(), name=path.stem, **kw)


def _tris_to_stl_bytes(pts, tris, name: str) -> bytes:
    try:
        import cab_occ
        return cab_occ.triangles_to_stl(pts, tris, name=name)
    except Exception:
        # binary STL fallback
        n = len(tris)
        buf = bytearray(80) + struct.pack("<I", n)
        for t in tris:
            v = pts[list(t)]
            nrm = np.cross(v[1] - v[0], v[2] - v[0])
            ln = np.linalg.norm(nrm) or 1.0
            nrm = nrm / ln
            buf += struct.pack("<3f", *nrm)
            for p in v:
                buf += struct.pack("<3f", *p)
            buf += struct.pack("<H", 0)
        return bytes(buf)


def _tris_to_obj_bytes(pts, tris, name: str) -> bytes:
    """E1: Wavefront OBJ text from a triangle mesh."""
    p = np.asarray(pts, dtype=np.float64)
    t = np.asarray(tris, dtype=np.int64)
    lines = [f"o {name}"]
    for v in p:
        lines.append(f"v {v[0]:.8g} {v[1]:.8g} {v[2]:.8g}")
    for f in t:
        lines.append(f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _tris_to_dxf_bytes(pts, tris, name: str) -> bytes:
    """E1: DXF 3DFACE entities from a triangle mesh (mm)."""
    p = np.asarray(pts, dtype=np.float64) * 1000.0  # m -> mm
    t = np.asarray(tris, dtype=np.int64)
    out = [
        "0", "SECTION", "2", "ENTITIES",
    ]
    for f in t:
        a, b, c = (p[i] for i in f)
        out += [
            "0", "3DFACE", "8", "0",
            "10", f"{a[0]:.8g}", "20", f"{a[1]:.8g}", "30", f"{a[2]:.8g}",
            "11", f"{b[0]:.8g}", "21", f"{b[1]:.8g}", "31", f"{b[2]:.8g}",
            "12", f"{c[0]:.8g}", "22", f"{c[1]:.8g}", "32", f"{c[2]:.8g}",
        ]
    out += ["0", "ENDSEC", "0", "EOF"]
    return ("\r\n".join(out) + "\r\n").encode("ascii")


def _tris_to_mdl_bytes(pts, tris, name: str) -> bytes:
    """E1: Cradle MDL is treated as OBJ-compatible vertex data (best effort)."""
    return _tris_to_obj_bytes(pts, tris, name)


def add_stl_member(archive: CabArchive, stl_bytes: bytes,
                   name: Optional[str] = None) -> CabMember:
    """Append an STL stream as a new cab member (``.stl``)."""
    if name is None:
        existing = [m.name for m in archive.members]
        stem = "model"
        n = 1
        while True:
            candidate = f"{stem}_import_{n:04d}.stl"
            if candidate not in existing:
                name = candidate
                break
            n += 1
    else:
        existing = [m.name for m in archive.members]
        if name in existing:
            stem, ext = Path(name).stem, Path(name).suffix
            n = 2
            while f"{stem}_{n}{ext}" in existing:
                n += 1
            name = f"{stem}_{n}{ext}"
    date, time = _msdos_now()
    member = CabMember(
        name=name, cb_file=len(stl_bytes), uoff_folder_start=0,
        i_folder=0, date=date, time=time, attribs=0x00A0, data=stl_bytes)
    archive.members.append(member)
    return member


def available() -> bool:
    """True when the pskernel-based import path can run."""
    return _ps_facet2 is not None and _ps_facet2.available()


def import_xt_bytes(raw: bytes, *, adaptive: bool = True,
                    progress=None, **kw) -> list[ImportedBody]:
    """Receive a text ``.x_t`` stream and tessellate every body.

    Assemblies (e.g. ``cellular_phone.x_t``) are expanded to solid/sheet
    bodies before faceting.  Per-body failures are skipped so one bad tag
    cannot abort the whole import.  ``progress`` is an optional callable
    ``(done, total, name)`` for GUI status updates.
    """
    if not available():
        raise RuntimeError("Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    sess = _ps_facet2._get_session()
    root_tags = sess.receive_xt(raw)
    tags = sess.expand_to_bodies(root_tags)
    out: list[ImportedBody] = []
    total = len(tags)
    for i, tag in enumerate(tags):
        name = ""
        try:
            name = sess.body_name(tag)
        except Exception:
            name = f"body_{tag}"
        if progress is not None:
            try:
                progress(i, total, name)
            except Exception:
                pass
        part = None
        try:
            if adaptive:
                part = sess.facet_body_adaptive(tag, **kw)
            else:
                part = sess.facet_body(tag, **kw)
        except OSError:
            part = None
        except Exception:
            part = None
        if part is None or not part.triangles.size:
            continue
        try:
            part.vertices = sess.body_vertices(tag)
        except Exception:
            part.vertices = None
        try:
            # STpre "Representative": only sharp-edge vertices (smooth-only
            # vertices are not gridded; P0-1 exact-count fix).
            part.rep_vertices = sess.representative_vertices(tag)
        except Exception:
            part.rep_vertices = None
        out.append(ImportedBody(name=part.name, tag=tag, tess=part))
    if progress is not None:
        try:
            progress(total, total, "done")
        except Exception:
            pass
    return out


def import_xt_file(path: str | Path, *, adaptive: bool = True,
                   **kw) -> list[ImportedBody]:
    """Import one ``.x_t`` file; returns the tessellated bodies."""
    return import_xt_bytes(Path(path).read_bytes(), adaptive=adaptive, **kw)


def _msdos_now() -> tuple[int, int]:
    """Current date/time in MS-DOS format (matches existing cab members)."""
    import datetime

    now = datetime.datetime.now()
    date = ((now.year - 1980) << 9) | (now.month << 5) | now.day
    time = (now.hour << 11) | (now.minute << 5) | (now.second // 2)
    return date, time


def add_member(archive: CabArchive, data: bytes, name: str) -> CabMember:
    # Generic cab member append (reused by x_t/stl/xfem importers).
    date, time = _msdos_now()
    member = CabMember(
        name=name,
        cb_file=len(data),
        uoff_folder_start=0,
        i_folder=0,
        date=date,
        time=time,
        attribs=0x00A0,
        data=data,
    )
    archive.members.append(member)
    return member
def add_xt_member(archive: CabArchive, xt_bytes: bytes,
                  name: Optional[str] = None) -> CabMember:
    """Append an imported x_t stream as a new cab member."""
    if name is None:
        existing = [m.name for m in archive.members if m.name.endswith(".x_t")]
        if existing:
            stem = existing[0].rsplit(".", 1)[0]
        else:
            stem = "model"
        n = 1
        while True:
            candidate = f"{stem}_import_{n:04d}.x_t"
            if candidate not in existing:
                name = candidate
                break
            n += 1
    date, time = _msdos_now()
    member = CabMember(
        name=name,
        cb_file=len(xt_bytes),
        uoff_folder_start=0,
        i_folder=0,
        date=date,
        time=time,
        attribs=0x00A0,
        data=xt_bytes,
    )
    archive.members.append(member)
    return member


# STpre / ex4_e.cab cycling part colors (RGBA). Assemblies get one hue per
# body so imported multi-body XT parts are visually distinct in Draw Window.
STPRE_PART_COLORS: tuple[str, ...] = (
    "25,25,255,255",
    "117,25,255,255",
    "255,117,25,255",
    "255,209,25,255",
    "209,255,25,255",
    "117,255,25,255",
    "25,255,25,255",
    "25,255,117,255",
    "25,255,209,255",
    "25,209,255,255",
    "25,117,255,255",
)


def part_color_for_index(index: int) -> str:
    """Return the ex4_e-style RGBA string for part ``index`` (0-based)."""
    return STPRE_PART_COLORS[int(index) % len(STPRE_PART_COLORS)]


def register_parts(model: StpreModel, bodies: list[ImportedBody], *,
                   group: Optional[str] = None,
                   material: Optional[str] = None,
                   color: Optional[str] = None,
                   transform: Optional[tuple[float, ...]] = None,
                   kind: str = "body",
                   distinct_colors: Optional[bool] = None) -> list[str]:
    """Append ``<parts type="body">`` entries; returns added part names.

    When registering an assembly (multiple bodies) and ``color`` is not
    given, assign cycling STpre/ex4_e palette colors so parts differ in
    the Draw Window.  Pass ``distinct_colors=False`` to force a single
    shared color (default blue).  A single explicit ``color`` still
    paints every added part the same.
    """
    added: list[str] = []
    if distinct_colors is None:
        distinct_colors = color is None and len(bodies) > 1
    # Continue palette from existing parts so re-imports stay distinct
    color_base = len(list(model.parts())) if distinct_colors else 0
    for i, body in enumerate(bodies):
        if model.find_part(body.name) is not None:
            continue
        tf = None
        if transform is not None and len(transform) == 16:
            tf = ",".join(f"{v:.17g}" for v in transform)
        if color is not None:
            col = color
        elif distinct_colors:
            col = part_color_for_index(color_base + len(added))
        else:
            col = part_color_for_index(0)
        el = model.add_part(
            name=body.name, kind=kind,
            property_=material,
            color=col,
            transform=tf,
            group=group,
        )
        if el is not None:
            added.append(body.name)
    return added
