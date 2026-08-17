# -*- coding: utf-8 -*-
"""Cradle ``.ccel`` binary container — reader/writer (R20, 2026-08-16).

Reverse-engineered from 11 official samples under
``CradleCFD_2023.2_ST_Example/Exercise_e/Function`` (probe:
``_ccel_probe.py``; all samples walk cleanly to EOF).

Wire format
-----------
Stream of records, all integers/floats big-endian::

    record := [len:int32][payload: len bytes][len:int32]   # frame doubled

Record kinds (a "tag" is itself a record whose payload is the 4-char
keyword)::

    CODE  STR 'UTF8'
    VERS  DESC (12, 2)
    PART                                # start of a part (no payload tag)
      NAME   DESC (1, N) + STR          # part name
      TYPE   DESC (1, N) + STR          # 'Cube' | 'Any_Body' | 'Cylinder' | 'Sphere'
      FACE   DESC (face_no, slice_no)   # CAD face f, tessellated slice s (0-)
        NODE   DESC (n, 24) + n × PT    # PT = 3 × float64, metres
        CONN   DESC (m, 16) + m × QUAD  # QUAD = 4 × int32, face-local 0-based,
                                        # -1 pads a degenerate triangle
      ATTR   DESC (1, N) + STR          # 'BODY' | 'PANEL' | 'FLUID' | 'CBODY'
    ASEM  NAME '组'  PART _string(member) …        # assembly members
    FSET  NAME  PART _string(member) …  FACE (1,2) DESC (a, b)
                                                       # named face set
    EOF   STR 'EOF '

Correspondence to the ``.s`` side (exA23-2b / exA23-4 evidence): parts
registered for cut-cell carry a *negative* PARTS id with an empty box
list, the ``.s`` header carries a ``CCEL`` line naming this file, and the
file lives next to ``.s``/``.cab`` (not inside the archive).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

_BEI = ">i"
_BED = ">ddd"
_BE4I = ">iiii"

_EOF_PAYLOAD = b"EOF "
_VERS = (12, 2)
_TAGS = ("CODE", "VERS", "PART", "NAME", "TYPE", "FACE", "NODE", "CONN",
         "ATTR", "FSET", "ASEM", "EOF ")


class CcelError(ValueError):
    """Malformed .ccel stream."""


@dataclass
class CcelFace:
    """One tessellated CAD face slice (nodes in metres, local quads)."""

    nodes: list[tuple[float, float, float]] = field(default_factory=list)
    quads: list[tuple[int, int, int, int]] = field(default_factory=list)
    face_no: int = 1
    slice_no: int = 0


@dataclass
class CcelPart:
    name: str = ""
    type_str: str = "Any_Body"     # Cube | Any_Body | Cylinder | Sphere
    attr: str = "BODY"             # BODY | PANEL | FLUID | CBODY
    faces: list[CcelFace] = field(default_factory=list)


@dataclass
class CcelAssembly:
    """ASEM group: assembly name + member part names."""

    name: str = ""
    members: list[str] = field(default_factory=list)


@dataclass
class CcelFaceSet:
    """FSET group: named face selection (boundary-condition face group).

    ``face_sel`` carries the trailing FACE DESC pair (a, b); read as
    (start face, count) or (face, sub) — both consistent with samples.
    """

    name: str = ""
    members: list[str] = field(default_factory=list)
    face_sel: tuple[int, int] = (1, 1)


# -- low-level record framing -----------------------------------------------

def _rec(payload: bytes) -> bytes:
    n = len(payload)
    return struct.pack(_BEI, n) + payload + struct.pack(_BEI, n)


def _desc(a: int, b: int) -> bytes:
    return _rec(struct.pack(">ii", a, b))


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return _desc(1, len(data)) + _rec(data)


def _walk(data: bytes):
    """Yield ``(payload, length_ok)`` per record; raise on broken frames."""
    p, n = 0, len(data)
    while p < n:
        if p + 4 > n:
            raise CcelError(f"truncated head at {p}")
        (length,) = struct.unpack_from(_BEI, data, p)
        if length < 0 or p + 8 + length > n:
            raise CcelError(f"bad length {length} at {p}")
        (tail,) = struct.unpack_from(_BEI, data, p + 4 + length)
        if tail != length:
            raise CcelError(f"frame mismatch at {p} ({length} != {tail})")
        yield data[p + 4:p + 4 + length]
        p += 8 + length


def _is_tag(payload: bytes) -> bool:
    return len(payload) == 4 and payload.decode("ascii", "ignore") in _TAGS


# -- writer ------------------------------------------------------------------

def write_ccel(parts: list[CcelPart], assemblies: list[CcelAssembly] | None = None,
               face_sets: list[CcelFaceSet] | None = None) -> bytes:
    """Serialise parts (+ optional ASEM/FSET groups) to a .ccel stream."""
    out = [_rec(b"CODE"), _rec(b"UTF8"), _rec(b"VERS"),
           _desc(*_VERS)]
    for part in parts:
        out.append(_rec(b"PART"))
        out.append(_rec(b"NAME"))
        out.append(_string(part.name))
        out.append(_rec(b"TYPE"))
        out.append(_string(part.type_str))
        for face in part.faces:
            out.append(_rec(b"FACE"))
            out.append(_desc(face.face_no, face.slice_no))
            out.append(_rec(b"NODE"))
            out.append(_desc(len(face.nodes), 24))
            for x, y, z in face.nodes:
                out.append(_rec(struct.pack(_BED, x, y, z)))
            out.append(_rec(b"CONN"))
            out.append(_desc(len(face.quads), 16))
            for q in face.quads:
                out.append(_rec(struct.pack(_BE4I, *q)))
        out.append(_rec(b"ATTR"))
        out.append(_string(part.attr))
    for asm in assemblies or []:
        out.append(_rec(b"ASEM"))
        out.append(_rec(b"NAME"))
        out.append(_string(asm.name))
        for m in asm.members:
            out.append(_rec(b"PART"))
            out.append(_string(m))
    for fs in face_sets or []:
        out.append(_rec(b"FSET"))
        out.append(_rec(b"NAME"))
        out.append(_string(fs.name))
        for m in fs.members:
            out.append(_rec(b"PART"))
            out.append(_string(m))
        out.append(_rec(b"FACE"))
        out.append(_desc(1, 2))
        out.append(_desc(*fs.face_sel))
    out.append(_rec(_EOF_PAYLOAD))
    return b"".join(out)


# -- reader ------------------------------------------------------------------

def read_ccel(data: bytes) -> list[CcelPart]:
    """Parse a .ccel stream (parts incl. assemblies/face-sets metadata)."""
    doc = read_ccel_doc(data)
    return doc[0]


def read_ccel_doc(data: bytes) -> tuple[list[CcelPart], list[CcelAssembly],
                                        list[CcelFaceSet]]:
    """Full parse → (parts, assemblies, face_sets).

    Raises :class:`CcelError` on any frame/structure corruption.
    """
    payloads = list(_walk(data))
    if not payloads:
        raise CcelError("empty stream")
    pos = 0

    def at(i: int) -> bytes:
        return payloads[i] if 0 <= i < len(payloads) else b""

    if at(pos) != b"CODE" or at(pos + 1) != b"UTF8":
        raise CcelError("missing CODE/UTF8 prologue")
    pos += 2
    if at(pos) != b"VERS":
        raise CcelError("missing VERS")
    pos += 2  # tag + desc payload (value unchecked, (12,2) in all samples)

    parts: list[CcelPart] = []
    assemblies: list[CcelAssembly] = []
    face_sets: list[CcelFaceSet] = []
    part: CcelPart | None = None
    face: CcelFace | None = None
    while pos < len(payloads):
        p = at(pos)
        if p == b"EOF ":
            if pos != len(payloads) - 1:
                raise CcelError("records after EOF")
            break
        if p == b"PART" and _is_tag(at(pos + 1)):
            part = CcelPart()
            parts.append(part)
            face = None
            pos += 1
            continue
        if p in (b"ASEM", b"FSET"):
            pos, group = _read_group(payloads, pos, p == b"ASEM")
            (assemblies if p == b"ASEM" else face_sets).append(group)
            continue
        if part is None:
            raise CcelError(f"data before first PART at record {pos}")
        if p == b"NAME":
            part.name = _read_string(payloads, pos)
            pos = _skip_string(payloads, pos)
        elif p == b"TYPE":
            part.type_str = _read_string(payloads, pos)
            pos = _skip_string(payloads, pos)
        elif p == b"ATTR":
            part.attr = _read_string(payloads, pos)
            pos = _skip_string(payloads, pos)
        elif p == b"FACE":
            a, b = struct.unpack(">ii", at(pos + 1))
            face = CcelFace(face_no=a, slice_no=b)
            part.faces.append(face)
            pos += 2
        elif p == b"NODE":
            if face is None:
                raise CcelError("NODE outside FACE")
            count, size = struct.unpack(">ii", at(pos + 1))
            if size != 24:
                raise CcelError(f"NODE item size {size} != 24")
            for i in range(count):
                face.nodes.append(struct.unpack(_BED, at(pos + 2 + i)))
            pos += 2 + count
        elif p == b"CONN":
            if face is None:
                raise CcelError("CONN outside FACE")
            count, size = struct.unpack(">ii", at(pos + 1))
            if size != 16:
                raise CcelError(f"CONN item size {size} != 16")
            for i in range(count):
                face.quads.append(struct.unpack(_BE4I, at(pos + 2 + i)))
            pos += 2 + count
        else:
            raise CcelError(f"unexpected payload at record {pos}: {p!r}")
    else:
        raise CcelError("missing EOF sentinel")
    return parts, assemblies, face_sets


def _read_group(payloads: list[bytes], pos: int, is_asem: bool
                ) -> tuple[int, CcelAssembly | CcelFaceSet]:
    """Parse one ASEM/FSET group starting at its tag record.

    Members are ``PART`` tag + :func:`_string` pairs (sample evidence:
    exA02-4a 'Lens' → DESC (1,4), exA23-1a 'Extrusion1' → (1,10) — the
    DESC counts characters, not members).
    """
    group: CcelAssembly | CcelFaceSet
    group = CcelAssembly() if is_asem else CcelFaceSet()
    p = pos + 1
    if payloads[p] == b"NAME":
        group.name = _read_string(payloads, p)
        p = _skip_string(payloads, p)
    while p < len(payloads) and payloads[p] == b"PART":
        group.members.append(_read_string(payloads, p))
        p += 3                                     # tag + DESC + member
    if not is_asem and p < len(payloads) and payloads[p] == b"FACE":
        p += 1                                    # tag
        p += 1                                    # DESC (1, 2)
        sel = struct.unpack(">ii", payloads[p])   # the selection DESC
        p += 1
        group.face_sel = sel                      # type: ignore[assignment]
    return p, group


def _read_string(payloads: list[bytes], pos: int) -> str:
    return payloads[pos + 2].decode("utf-8", "replace")


def _skip_string(payloads: list[bytes], pos: int) -> int:
    return pos + 3  # tag + DESC + one string record


# -- geometry helpers --------------------------------------------------------

def faces_from_box(min_m, max_m) -> list[CcelFace]:
    """Six quad faces of an axis-aligned box (TYPE 'Cube' geometry)."""
    x0, y0, z0 = (float(v) for v in min_m)
    x1, y1, z1 = (float(v) for v in max_m)
    quads = [
        ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]),   # z-
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),   # z+
        ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)]),   # x-
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),   # x+
        ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),   # y-
        ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]),   # y+
    ]
    return [CcelFace(nodes=pts, quads=[(0, 1, 2, 3)], face_no=i + 1)
            for i, pts in enumerate(quads)]


def faces_from_triangles(points_m, triangles) -> list[CcelFace]:
    """Triangles (n×3 verts metres, m×3 indices) → one CCEL face.

    Input points follow the TessPart convention (metres, part transform
    already applied). Triangles become degenerate quads padded with -1
    (official CONN convention). Vertices are de-duplicated to keep
    files compact.
    """
    import numpy as np

    pts = np.asarray(points_m, dtype=float)
    tris = np.asarray(triangles)
    if pts.size == 0 or tris.size == 0:
        return []
    uniq, inverse = np.unique(pts, axis=0, return_inverse=True)
    nodes = [tuple(v) for v in uniq]
    quads = [(int(inverse[t[0]]), int(inverse[t[1]]),
              int(inverse[t[2]]), -1) for t in tris]
    return [CcelFace(nodes=nodes, quads=quads, face_no=1)]
