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

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
                   transform: Optional[tuple[float, ...]] = None) -> list[str]:
    """Append ``<parts type="body">`` entries; returns added part names."""
    added: list[str] = []
    for body in bodies:
        if model.find_part(body.name) is not None:
            continue
        tf = None
        if transform is not None and len(transform) == 16:
            tf = ",".join(f"{v:.17g}" for v in transform)
        el = model.add_part(
            name=body.name,
            property_=material,
            color=color,
            transform=tf,
            group=group,
        )
        if el is not None:
            added.append(body.name)
    return added
