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
import subprocess
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


def _cradle_programs() -> Optional[Path]:
    try:
        import ps_facet2_nodes
        return ps_facet2_nodes.find_cradle_programs()
    except Exception:
        return None


def _convert_with_cadthru(in_path: Path, out_path: Path,
                          exe_names: list[str]) -> bool:
    """Best-effort CADthru/STEPAssistant CLI conversion to x_t."""
    prog = _cradle_programs()
    exe = None
    if prog is not None:
        for n in exe_names:
            p = prog / n
            if p.is_file():
                exe = str(p)
                break
    if exe is None:
        return False
    patterns = [
        [in_path, out_path],
        ["-i", in_path, "-o", out_path],
        ["/i", in_path, "/o", out_path],
        ["InterOp", in_path, out_path],
    ]
    for args in patterns:
        if out_path.exists():
            out_path.unlink()
        try:
            subprocess.run([exe] + [str(a) for a in args],
                           timeout=90, capture_output=True)
        except Exception:
            continue
        if out_path.exists() and out_path.stat().st_size > 0:
            return True
    return False


def _convert_cad_to_xt(path: Path, suffix: str) -> bytes:
    """Convert STEP/SAT/IGES to x_t via the Cradle CAD conversion library."""
    exe_names = ["CADthru_Bx64net.exe"]
    if suffix in (".step", ".stp", ".igs", ".iges"):
        exe_names.append("STEPAssistant_Bx64.exe")
    out = path.with_suffix(".x_t")
    ok = _convert_with_cadthru(path, out, exe_names)
    if not ok:
        raise RuntimeError(
            f"CAD conversion failed for {path.name}: Cradle CADthru/"
            "STEPAssistant did not produce an x_t file. Convert the file "
            "with your own tool first and import the resulting .x_t.")
    raw = out.read_bytes()
    try:
        out.unlink()
    except Exception:
        pass
    return raw


def import_step_file(path: str | Path, **kw) -> list[ImportedBody]:
    """Import STEP (.step/.stp) via CAD conversion to x_t."""
    raw = _convert_cad_to_xt(Path(path), Path(path).suffix.lower())
    return import_xt_bytes(raw, **kw)


def import_sat_file(path: str | Path, **kw) -> list[ImportedBody]:
    """Import ACIS SAT (.sat/.sab) via CAD conversion to x_t."""
    raw = _convert_cad_to_xt(Path(path), Path(path).suffix.lower())
    return import_xt_bytes(raw, **kw)


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
        raw = _convert_cad_to_xt(Path(path), suffix)
        return import_xt_bytes(raw, **kw), raw, "xt"
    if suffix in (".sat", ".sab"):
        raw = _convert_cad_to_xt(Path(path), suffix)
        return import_xt_bytes(raw, **kw), raw, "xt"
    raise ValueError(f"unsupported geometry format: {suffix}")


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
                    **kw) -> list[ImportedBody]:
    """Receive a text ``.x_t`` stream and tessellate every body."""
    if not available():
        raise RuntimeError("Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    sess = _ps_facet2._get_session()
    tags = sess.receive_xt(raw)
    out: list[ImportedBody] = []
    for tag in tags:
        if adaptive:
            part = sess.facet_body_adaptive(tag, **kw)
        else:
            part = sess.facet_body(tag, **kw)
        if part is None or not part.triangles.size:
            continue
        try:
            part.vertices = sess.body_vertices(tag)
        except Exception:
            part.vertices = None
        out.append(ImportedBody(name=part.name, tag=tag, tess=part))
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


def register_parts(model: StpreModel, bodies: list[ImportedBody], *,
                   group: Optional[str] = None,
                   material: Optional[str] = None,
                   color: Optional[str] = None,
                   transform: Optional[tuple[float, ...]] = None,
                   kind: str = "body") -> list[str]:
    """Append ``<parts type="body">`` entries; returns added part names."""
    added: list[str] = []
    for body in bodies:
        if model.find_part(body.name) is not None:
            continue
        tf = None
        if transform is not None and len(transform) == 16:
            tf = ",".join(f"{v:.17g}" for v in transform)
        el = model.add_part(
            name=body.name, kind=kind,
            property_=material,
            color=color,
            transform=tf,
            group=group,
        )
        if el is not None:
            added.append(body.name)
    return added
