"""Standalone reverse-engineered scSTREAM Pre x_t -> facet nodes generator.

This script reproduces, in pure ctypes, the node-generation path that
scSTREAM Pre uses to turn Parasolid ``.x_t`` B-rep bodies into display
mesh nodes (vertices + triangles).  It was written from disassembly of
the Cradle CFD 2025.2 binaries under ``Programs_x64``:

Call chain (all RVAs are relative to the DLL image base 0x180000000):

  STpreBase_Bx64.dll
    ?MakeFacet@PreBody@@QEAAHHPEAVFacetParam@@@Z        RVA 0x293A20
    ?MakeFacetParam@PreBody@@QEAAPEAVFacetParam@@QEAN@Z RVA 0x293C20
      |  (FacetParam carries the chord/surface tolerances, see
      |   ?Get@FacetParam@@QEAAXPEAN@Z RVA 0x36160)
      v
  ParasolidGW_Bx64.dll  (Cradle's Parasolid wrapper)
    ?PKBody_GetTriangles@LocalParasolid@@...            RVA 0xA49A0 etc.
    ?PKFaces_RenderV3@LocalParasolid@@...               RVA 0x1415C0 / 0x141850
      |  (fills PK_TOPOL_facet_2_o_t, then calls virtual slot vtable+0x1C50)
      v
  pskernel.dll  (the actual Parasolid kernel)
    PK_TOPOL_facet_2                                    RVA 0x44DFA0
    PK_TOPOL_facet_2_r_f                                RVA 0x44FCE0

The kernel is commercial closed-source, so the *facet geometry algorithm*
itself (surface sampling, chord/angle subdivision, fin generation) cannot
be copied.  What the disassembly does give us - and what this script
implements - is the exact public API contract used by STpre:

* ``PK_TOPOL_facet_2`` accepts ``PK_TOPOL_facet_2_o_t`` whose version is
  in range 5..26 (the option converter at pskernel RVA 0x443550 switches
  on ``version-5`` with a 22-entry jump table).
* The version-5 option layout is a 312-byte mesh-control block followed by
  **18 consecutive byte flags** at offsets 0x138..0x149.  Each flag
  requests one facet table (converter writes caller bytes 0x138..0x149
  into the internal choice flags at 0x1C8..0x1DF).
* Table tokens (fctab) observed on this kernel (the V35 documentation
  order and the kernel's own V5 enum differ in the middle block):

    0x57B2 facet_fin      0x57B7 data_point_idx 0x57BD data_curv_idx
    0x57B3 strip_boundary 0x57B8 data_normal_idx 0x57BE param_uv
    0x57B4 strip_zigzag   0x57B9 data_param_idx  0x57BF deriv_dp
    0x57B5 fin_fin        0x57BA data_deriv_idx  0x57C0 deriv_d2p
    0x57B6 fin_data       0x57BB point_vec       0x57C1 curv_dirs
                         0x57BC normal_vec       0x57C2 fin_edge
                                                 0x57C3 strip_face

  i.e. the kernel places ``point_vec``/``normal_vec`` *before*
  ``data_curv_idx``, opposite to the V35 header order.  This was confirmed
  three ways: single-choice probes (offset 0x141 -> token 0x57BB etc.),
  data semantics (0x57BB holds the 8 box corners, identical to the GO
  path), and STpre's own table decoder in ParasolidGW_Bx64.dll, which
  reads 24-byte coordinates from the table stored in its ``data_curv_idx``
  slot (token 0x57BB).

  (ParasolidGW's ``?PKTopol_facet_2_r_f@...`` at RVA 0x18B290 frees a
  16-byte table entry array; it switches on ``fctab-0x57B2`` with 18
  cases, which is exactly the 18 flags above.  pskernel's own
  ``PK_TOPOL_facet_2_r_f`` switches on ``fctab-0x57B2`` with 25 cases,
  i.e. this kernel also knows the newer fin_edge/point_topol/fin_topol/
  error_object/incr_faces tables.)
* Every table pointer in ``PK_TOPOL_facet_2_r_t.tables[]`` points to a
  16-byte wrapper whose first qword is the actual data array and whose
  second dword is the element count (``PK_TOPOL_fctab_*_t`` layout:
  ``{ pointer-to-data; int length; }``).
* Data encodings observed on this kernel (V35 header ``pk_topol_fctab_*_t``):
  - facet_fin:       lookup table of 8-byte records ``{int facet; int fin}``,
    ``length`` records, 3 consecutive records per triangle facet
  - fin_data:        indexed table ``int data[fin]`` (length = fins)
  - data_point_idx:  indexed table ``int point[data]``
    (length = data indices; ``data[fin]`` indexes into it)
  - point_vec:       indexed table of ``length`` PK_VECTOR_t entries
    (24 bytes each: x, y, z doubles); entry i is the coordinate of point i
    (token 0x57BB on this kernel)
  - normal_vec:      same layout, unit face normals (token 0x57BC)
  - fin_edge:        8-byte records ``{int fin; PK_EDGE_t edge}``.  The
    kernel's token 0x57C2 is *not* the V35-documented facet_face table; it
    maps the two boundary fins of every triangle facet to the model edge
    they lie on (verified on box against PK_BODY_ask_edges: 12 distinct edge
    tags, each appearing twice; the 12 missing fins are the face-interior
    diagonals, i.e. fin indices 3*facet).
* To call the kernel from a foreign process the argument checker must be
  disabled (``PK_SESSION_set_check_arguments(0)``), otherwise a struct
  version mismatch raises ``PK_ERROR_o_t_version_incorrect`` (5022)
  before any faceting happens.  STpre itself always passes a matching
  version; the checker-off call is the reverse-engineering workaround.

Facet geometry is generated by ``PK_TOPOL_facet_2`` exactly as STpre does
(the wrapper sets ``max_facet_sides=3`` plus explicit surface plane
tolerance/angle; ``PKFaces_RenderV3`` at RVA 0x141850 additionally scales
the chord tolerance by body size).  The returned tables are then walked
facet -> fin -> data -> point -> coordinate to produce node/triangle
arrays.

If ``PK_TOPOL_facet_2`` is unavailable or returns no tables, the script
falls back to ``PK_TOPOL_render_facet`` (GO callback path, same kernel),
which is the equivalent display-faceting route also used by
``ps_tessellate.py``.

Usage:
    python ps_facet2_nodes.py tests/box/_box_all.x_t
    python ps_facet2_nodes.py --obj out.obj tests/tr03/_tr03_all.x_t
"""

from __future__ import annotations

import argparse
import ctypes as C
import os
import struct
import tempfile
from ctypes import (
    CFUNCTYPE, POINTER, Structure, byref, c_byte, c_char, c_char_p,
    c_double, c_int, c_void_p, cast, memmove, memset, sizeof, string_at,
)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Reverse-engineered constants
# ---------------------------------------------------------------------------

# PK_TOPOL_fctab_*_c tokens (pskernel facet tables), base 0x57B2.
FCTAB_FACET_FIN = 0x57B2
FCTAB_STRIP_BOUNDARY = 0x57B3
FCTAB_STRIP_ZIGZAG = 0x57B4
FCTAB_FIN_FIN = 0x57B5
FCTAB_FIN_DATA = 0x57B6
FCTAB_DATA_POINT_IDX = 0x57B7
FCTAB_DATA_NORMAL_IDX = 0x57B8
FCTAB_DATA_PARAM_IDX = 0x57B9
FCTAB_DATA_DERIV_IDX = 0x57BA
FCTAB_DATA_CURV_IDX = 0x57BD
FCTAB_POINT_VEC = 0x57BB
FCTAB_NORMAL_VEC = 0x57BC
FCTAB_PARAM_UV = 0x57BE
FCTAB_DERIV_DP = 0x57BF
FCTAB_DERIV_D2P = 0x57C0
FCTAB_CURV_DIRS = 0x57C1
FCTAB_FACET_FACE = 0x57C2
FCTAB_STRIP_FACE = 0x57C3

# Choice byte offsets inside PK_TOPOL_facet_2_o_t version 5 (control is
# 0x138 bytes; the 18 flags follow at 0x138..0x149).  NOTE: the kernel's V5
# layout puts point_vec/normal_vec *before* data_curv_idx (verified by
# single-choice probes and by the returned data), unlike the V35 docs.
CHOICE_OFFSET = {
    "facet_fin": 0x138, "strip_boundary": 0x139, "strip_zigzag": 0x13A,
    "fin_fin": 0x13B, "fin_data": 0x13C, "data_point_idx": 0x13D,
    "data_normal_idx": 0x13E, "data_param_idx": 0x13F,
    "data_deriv_idx": 0x140, "point_vec": 0x141, "normal_vec": 0x142,
    "data_curv_idx": 0x143, "param_uv": 0x144, "deriv_dp": 0x145,
    "deriv_d2p": 0x146, "curv_dirs": 0x147, "fin_edge": 0x148,
    "strip_face": 0x149,
}

_DEFAULT_CRADLE = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
DEFAULT_FACET_TOL = 1e-4        # surface-to-facet distance bound
DEFAULT_FACET_ANGLE_DEG = 12.0  # max normal swing per facet (degrees)

# Adaptive refinement defaults (see tessellate_xt / facet_body_adaptive).
DEFAULT_REFINE_ANGLE_DEG = 6.0  # local surface_plane_ang for selected faces
DEFAULT_REFINE_TOL = 1e-5       # local surface_plane_tol for selected faces
DEFAULT_SMOOTH_ANGLE_DEG = 8.0  # refine faces whose intra-face dihedral > this
DEFAULT_MIN_REL_AREA = 1e-4     # face area must be >= this * body bbox area
DEFAULT_MIN_FACE_FACETS = 8     # skip trivial faces with fewer facets

# GO segment types used by the render_facet fallback.
_SGTPFT = 2016  # facet segment


@dataclass
class TessPart:
    """Tessellated CAD body: node list + triangle list."""

    name: str
    points: np.ndarray          # (N, 3) float64
    triangles: np.ndarray       # (M, 3) int32 into points
    tag: int = 0
    vertices: Optional[np.ndarray] = None  # real B-rep vertices (M, 3)


# ---------------------------------------------------------------------------
# PK_TOPOL_facet_2_o_t, version 5 (layout recovered from the option
# converter disassembly at pskernel RVA 0x443550, case "version-5").
# ---------------------------------------------------------------------------


class _MeshControlV5(Structure):
    """PK_TOPOL_facet_mesh_2_o_t, version 5: 312 bytes."""

    _fields_ = [
        ("o_t_version", c_int),
        ("shape", c_int), ("match", c_int), ("density", c_int),
        ("n_view_directions", c_int), ("_pad0", c_int),
        ("view_directions", c_void_p),
        ("cull", c_int), ("n_cull_transfs", c_int), ("cull_transfs", c_void_p),
        ("n_loops", c_int), ("_pad1", c_int), ("loops", c_void_p),
        ("max_facet_sides", c_int),
        ("is_min_facet_width", c_int), ("min_facet_width", c_double),
        ("is_max_facet_width", c_int), ("_pad2", c_int),
        ("max_facet_width", c_double),
        ("is_curve_chord_tol", c_int), ("_pad3", c_int),
        ("curve_chord_tol", c_double),
        ("is_curve_chord_max", c_int), ("_pad4", c_int),
        ("curve_chord_max", c_double),
        ("is_curve_chord_ang", c_int), ("_pad5", c_int),
        ("curve_chord_ang", c_double),
        ("is_surface_plane_tol", c_int), ("_pad6", c_int),
        ("surface_plane_tol", c_double),
        ("is_surface_plane_ang", c_int), ("_pad7", c_int),
        ("surface_plane_ang", c_double),
        ("is_facet_plane_tol", c_int), ("_pad8", c_int),
        ("facet_plane_tol", c_double),
        ("is_facet_plane_ang", c_int), ("_pad9", c_int),
        ("facet_plane_ang", c_double),
        ("is_local_density_tol", c_int), ("_pad10", c_int),
        ("local_density_tol", c_double),
        ("is_local_density_ang", c_int), ("_pad11", c_int),
        ("local_density_ang", c_double),
        ("n_local_tols", c_int), ("_pad12", c_int), ("local_tols", c_void_p),
        ("n_topols_with_local_tols", c_int), ("_pad13", c_int),
        ("topols_with_local_tols", c_void_p),
        ("local_tols_for_topols", c_void_p),
        ("ignore", c_int), ("_pad14", c_int), ("ignore_value", c_double),
        ("ignore_scope", c_int), ("wire_edges", c_int),
        ("incremental_facetting", c_int), ("incremental_method", c_int),
    ]


class _Facet2OptionsV5(Structure):
    """PK_TOPOL_facet_2_o_t, version 5: control + 18 byte choice flags."""

    _fields_ = [("control", _MeshControlV5)] + [
        (name, c_byte) for name in CHOICE_OFFSET
    ]


class _Facet2Result(Structure):
    """PK_TOPOL_facet_2_r_t."""

    _fields_ = [
        ("number_of_facets", c_int),
        ("number_of_strips", c_int),
        ("number_of_fins", c_int),
        ("number_of_tables", c_int),
        ("tables", c_void_p),
    ]


class _FacetTable(Structure):
    """PK_TOPOL_facet_table_t: token + union pointer (16 bytes)."""

    _fields_ = [("fctab", c_int), ("_pad", c_int), ("ptr", c_void_p)]


class _FacetLocalTolerances(Structure):
    """PK_facet_local_tolerances_t: 5 doubles, zero keeps the global value."""

    _fields_ = [
        ("curve_chord_tol", c_double),
        ("curve_chord_max", c_double),
        ("curve_chord_ang", c_double),
        ("surface_plane_tol", c_double),
        ("surface_plane_ang", c_double),
    ]


# ---------------------------------------------------------------------------
# Kernel session (FRU + GO callbacks), same contract as ps_tessellate.py
# ---------------------------------------------------------------------------

_session: Optional["_PsSession"] = None


def find_cradle_programs() -> Optional[Path]:
    env = os.environ.get("CRADLE_PROGRAMS") or os.environ.get("P_SCHEMA")
    candidates: list[Path] = []
    if env:
        p = Path(env)
        candidates.append(p if p.name.lower() != "schemas" else p.parent)
    candidates.append(_DEFAULT_CRADLE)
    cradle_root = Path(r"C:\Program Files\Cradle")
    if cradle_root.is_dir():
        for child in sorted(cradle_root.glob("CradleCFD*/Programs_x64"),
                            reverse=True):
            candidates.append(child)
    seen: set[Path] = set()
    for c in candidates:
        c = c.resolve() if c.exists() else c
        if c in seen:
            continue
        seen.add(c)
        if (c / "pskernel.dll").is_file() and (c / "Schemas").is_dir():
            return c
    return None


def available() -> bool:
    """True when a Cradle ``pskernel.dll`` install can be located."""
    return find_cradle_programs() is not None


class _FRU(Structure):
    _fields_ = [(n, c_void_p) for n in (
        "fstart fabort fstop fmallo fmfree gosgmt goopsg goclsg gopixl "
        "gooppx goclpx ffoprd ffopwr ffclos ffread ffwrit ffoprb ffseek "
        "fftell fgcrcu fgcrsu fgevcu fgevsu fgprcu fgprsu ucoprd ucopwr"
    ).split()]


class _START(Structure):
    _fields_ = [("o_t_version", c_int), ("journal_file", c_char_p),
                ("user_field", c_int), ("reserved", c_int)]


class _RECV(Structure):
    _fields_ = [
        ("o_t_version", c_int), ("transmit_format", c_int),
        ("receive_user_fields", c_int), ("attdef_mismatch", c_int),
        ("part_index", c_int), ("n_part_indices", c_int),
        ("part_indices", c_void_p), ("n_identifiers", c_int),
        ("identifiers", c_void_p), ("receive_indexed_context", c_void_p),
        ("key_is_partition", c_int), ("receive_compound", c_int),
        ("receive_using_seek", c_int), ("receive_mixed", c_int),
    ]


class _PsSession:
    """One pskernel session with text x_t receive + facet_2 + GO fallback."""

    def __init__(self, prog: Path):
        self.prog = prog
        self.schema = prog / "Schemas"
        os.add_dll_directory(str(prog))
        os.environ["PATH"] = str(prog) + ";" + os.environ.get("PATH", "")
        os.environ["P_SCHEMA"] = str(self.schema)
        self.pk = C.WinDLL(str(prog / "pskernel.dll"))
        self._files: dict = {}
        self._next_id = 1
        self._mallo_bufs: list = []
        self._segs: list = []
        self._build_frustrum()
        self._start()

    # -- frustrum ----------------------------------------------------------
    def _build_frustrum(self) -> None:
        pk = self.pk
        files = self._files
        schema = self.schema
        mallo = self._mallo_bufs
        segs = self._segs

        @CFUNCTYPE(None, POINTER(c_int))
        def FSTART(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int))
        def FSTOP(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_char_p), POINTER(c_int))
        def FMALLO(nbytes, memory, ifail):
            n = nbytes[0]
            buf = (c_char * n)()
            mallo.append(buf)
            memory[0] = cast(buf, c_char_p)
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_char_p), POINTER(c_int))
        def FMFREE(n, m, i):
            i[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), c_void_p, POINTER(c_int),
            POINTER(c_int), POINTER(c_int), POINTER(c_int),
        )
        def FFOPRD(guise, format_, name, namlen, skiphd, strid, ifail):
            key = string_at(name, namlen[0]).decode("ascii", "replace")
            g = guise[0]
            path = None
            if g == 6:
                hits = [c for c in schema.glob(f"*{key}*")
                        if c.suffix in (".sch_txt", ".s_t")]
                hits = sorted(hits, key=lambda p: (
                    0 if p.suffix == ".sch_txt" else 1, len(p.name)))
                path = hits[0] if hits else None
            else:
                for cand in (Path(key), Path(key + ".x_t")):
                    if cand.is_file():
                        path = cand
                        break
            if not path:
                ifail[0] = 2
                strid[0] = -1
                return
            raw = path.read_bytes()
            is_bin = path.suffix == ".s_t"
            data = raw if is_bin else raw.decode("latin-1", "replace")
            loc = 0
            if not is_bin and skiphd[0] == 1:
                i = data.find("**END_OF_HEADER")
                if i >= 0:
                    nl = data.find("\n", i)
                    loc = nl + 1 if nl >= 0 else i
            sid = self._next_id
            self._next_id += 1
            files[sid] = {"data": data, "loc": loc, "bin": is_bin}
            strid[0] = sid
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), c_void_p, POINTER(c_int),
            c_void_p, POINTER(c_int), POINTER(c_int), POINTER(c_int),
        )
        def FFOPWR(*a):
            a[-2][0] = 1
            a[-1][0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int), c_void_p,
            POINTER(c_int), POINTER(c_int),
        )
        def FFREAD(guise, strid, nmax, buffer, nactual, ifail):
            f = files.get(strid[0])
            if not f:
                ifail[0] = 99
                nactual[0] = 0
                return
            data, loc, is_bin = f["data"], f["loc"], f["bin"]
            if loc >= len(data):
                nactual[0] = 0
                ifail[0] = 4
                return
            maxn = nmax[0]
            if is_bin:
                n = min(maxn, len(data) - loc)
                memmove(buffer, data[loc:loc + n], n)
                f["loc"] = loc + n
                nactual[0] = n
                ifail[0] = 0
                return
            end = loc
            while end < len(data) and (end - loc) < maxn:
                if data[end] == "\n":
                    end += 1
                    break
                end += 1
            chunk = data[loc:end]
            n = len(chunk)
            memmove(buffer, chunk.encode("latin-1"), n)
            f["loc"] = end
            nactual[0] = n
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
                   c_void_p, POINTER(c_int))
        def FFWRIT(*a):
            a[-1][0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
                   POINTER(c_int))
        def FFCLOS(guise, strid, action, ifail):
            ifail[0] = 0 if files.pop(strid[0], None) is not None else 14

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOSGMT(segtyp, ntags, tags, ngeom, geom, nlntp, lntp, ifail):
            try:
                st = segtyp[0]
                ng = ngeom[0]
                nl = nlntp[0]
                lt = [lntp[i] for i in range(nl)] if nl and lntp else []
                nfloat = ng * 3 if st == _SGTPFT else ng
                coords = ([geom[i] for i in range(nfloat)]
                          if nfloat and geom else [])
                segs.append((st, coords, lt))
            except Exception:
                pass
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOOPSG(*a):
            a[-1][0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOCLSG(*a):
            a[-1][0] = 0

        @CFUNCTYPE(None, POINTER(c_int))
        def GOPIXL(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOOPPX(a, ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOCLPX(a, ifail):
            ifail[0] = 0

        self._cbs = (FSTART, FSTOP, FMALLO, FMFREE, FFOPRD, FFOPWR, FFREAD,
                     FFWRIT, FFCLOS, GOSGMT, GOOPSG, GOCLSG, GOPIXL, GOOPPX,
                     GOCLPX)
        fru = _FRU()
        memset(byref(fru), 0, sizeof(fru))
        for name, fn in [
            ("fstart", FSTART), ("fstop", FSTOP), ("fmallo", FMALLO),
            ("fmfree", FMFREE), ("ffoprd", FFOPRD), ("ffopwr", FFOPWR),
            ("ffclos", FFCLOS), ("ffread", FFREAD), ("ffwrit", FFWRIT),
            ("gosgmt", GOSGMT), ("goopsg", GOOPSG), ("goclsg", GOCLSG),
            ("gopixl", GOPIXL), ("gooppx", GOOPPX), ("goclpx", GOCLPX),
        ]:
            setattr(fru, name, cast(fn, c_void_p))
        pk.PK_SESSION_register_frustrum.argtypes = [POINTER(_FRU)]
        pk.PK_SESSION_register_frustrum.restype = c_int
        rc = pk.PK_SESSION_register_frustrum(byref(fru))
        if rc != 0:
            raise RuntimeError(f"PK_SESSION_register_frustrum failed: {rc}")

    def _start(self) -> None:
        pk = self.pk
        pk.PK_SESSION_start.argtypes = [POINTER(_START)]
        pk.PK_SESSION_start.restype = c_int
        rc = pk.PK_SESSION_start(byref(_START(1, None, 0, 1)))
        if rc != 0:
            raise RuntimeError(f"PK_SESSION_start failed: {rc}")
        # Reverse-engineering workaround: the caller struct version 5 is
        # accepted by the option converter, but the argument checker still
        # compares it against the kernel's own schema constant and would
        # raise PK_ERROR_o_t_version_incorrect (5022).
        pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
        pk.PK_SESSION_set_check_arguments.restype = c_int
        pk.PK_SESSION_set_check_arguments(0)

    # -- part receive ------------------------------------------------------
    def receive_xt(self, xt_bytes: bytes) -> list[int]:
        tmpdir = Path(tempfile.mkdtemp(prefix="cab_ps_"))
        xtp = tmpdir / "part.x_t"
        xtp.write_bytes(xt_bytes)
        key = str(xtp.with_suffix("")).encode()
        pk = self.pk
        pk.PK_PART_receive.restype = c_int
        pk.PK_PART_receive.argtypes = [
            c_char_p, POINTER(_RECV), POINTER(c_int), POINTER(c_void_p)]
        opts = _RECV()
        memset(byref(opts), 0, sizeof(opts))
        opts.o_t_version = 1
        opts.transmit_format = 0  # text
        n = c_int(0)
        parts = c_void_p()
        rc = pk.PK_PART_receive(key, byref(opts), byref(n), byref(parts))
        if rc != 0:
            raise RuntimeError(f"PK_PART_receive failed: {rc}")
        return list(cast(parts, POINTER(c_int * n.value)).contents)

    def body_name(self, tag: int) -> str:
        pk = self.pk
        pk.PK_PART_ask_all_attribs.restype = c_int
        pk.PK_PART_ask_all_attribs.argtypes = [
            c_int, c_char_p, POINTER(c_int), POINTER(c_void_p)]
        pk.PK_ATTRIB_ask_string.restype = c_int
        pk.PK_ATTRIB_ask_string.argtypes = [
            c_int, c_int, POINTER(c_char_p)]
        best = ""
        for aname in (b"SDL/TYSA_NAME", b"SDL/TYSA_UNAME"):
            na = c_int(0)
            attrs = c_void_p()
            rc = pk.PK_PART_ask_all_attribs(tag, aname, byref(na), byref(attrs))
            if rc != 0 or not na.value:
                continue
            for a in cast(attrs, POINTER(c_int * na.value)).contents:
                s = c_char_p()
                if pk.PK_ATTRIB_ask_string(a, 0, byref(s)) == 0 and s.value:
                    raw = s.value
                    try:
                        text = raw.decode("ascii")
                    except UnicodeDecodeError:
                        continue
                    if text and all(32 <= ord(ch) < 127 for ch in text) \
                            and len(text) > len(best):
                        best = text
        return best or f"body_{tag}"

    # -- PK_TOPOL_facet_2 (reverse-engineered table path) -------------------
    def _facet2_call(self, tags: list[int], *,
                     facet_tol: float = DEFAULT_FACET_TOL,
                     facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
                     local_tols: Optional[list[tuple[int, tuple[float, ...]]]]
                     = None) -> Optional["_Facet2Result"]:
        """Build a V5 option block and call PK_TOPOL_facet_2 once.

        ``local_tols`` is a list of ``(topol_tag, tolerance5)`` pairs; the
        kernel overrides the global surface tolerances on exactly those
        faces/bodies (PK_facet_local_tolerances_t, zero entries keep the
        global value).  The result owns kernel memory; decode with
        ``_decode_result``.
        """
        pk = self.pk
        pk.PK_TOPOL_facet_2.restype = c_int
        pk.PK_TOPOL_facet_2.argtypes = [
            c_int, POINTER(c_int), c_void_p, POINTER(_Facet2OptionsV5),
            POINTER(_Facet2Result)]
        opts = _Facet2OptionsV5()
        memset(byref(opts), 0, sizeof(opts))
        opts.control.o_t_version = 5
        opts.control.max_facet_sides = 3
        opts.control.is_surface_plane_tol = 1
        opts.control.surface_plane_tol = max(float(facet_tol), 1e-12)
        opts.control.is_surface_plane_ang = 1
        opts.control.surface_plane_ang = max(
            float(facet_angle_deg) * 0.017453292519943295, 1e-6)
        if local_tols:
            n = len(local_tols)
            tols = (_FacetLocalTolerances * n)()
            topols = (c_int * n)()
            idx = (c_int * n)()
            for i, (tg, t5) in enumerate(local_tols):
                topols[i] = int(tg)
                idx[i] = i
                tols[i] = _FacetLocalTolerances(*t5)
            opts.control.n_local_tols = n
            opts.control.local_tols = cast(tols, c_void_p)
            opts.control.n_topols_with_local_tols = n
            opts.control.topols_with_local_tols = cast(topols, c_void_p)
            opts.control.local_tols_for_topols = cast(idx, c_void_p)
        opts.facet_fin = 1
        opts.fin_data = 1
        opts.data_point_idx = 1
        opts.point_vec = 1
        result = _Facet2Result()
        memset(byref(result), 0, sizeof(result))
        rc = pk.PK_TOPOL_facet_2(
            len(tags), (c_int * len(tags))(*tags), None, byref(opts),
            byref(result))
        if rc != 0 or result.number_of_tables <= 0 or not result.tables:
            return None
        return result

    def _decode_result(self, result, tag: int, name: str) -> Optional[TessPart]:
        """Decode PK_TOPOL_facet_2_r_t tables into a TessPart."""
        tables = cast(result.tables,
                      POINTER(_FacetTable * result.number_of_tables)).contents
        # t.ptr points at the PK_TOPOL_fctab_*_t wrapper {data*, length}.
        data = {}
        for t in tables:
            if t.ptr:
                data[t.fctab] = t.ptr
        if FCTAB_FACET_FIN not in data or FCTAB_FIN_DATA not in data \
                or FCTAB_DATA_POINT_IDX not in data \
                or FCTAB_POINT_VEC not in data:
            return None

        def table_wrapper(ptr: int) -> tuple[int, int]:
            """(data_ptr, length) from a 16-byte PK_TOPOL_fctab_*_t."""
            raw = string_at(ptr, 16)
            return struct.unpack_from("<Qi", raw)

        def pairs(ptr: int, count: int) -> list[tuple[int, int]]:
            """Read ``count`` 8-byte (int, int) lookup-table records."""
            raw = string_at(ptr, count * 8)
            return [(struct.unpack_from("<i", raw, i * 8)[0],
                     struct.unpack_from("<i", raw, i * 8 + 4)[0])
                    for i in range(count)]

        def ints(ptr: int, count: int) -> list[int]:
            """Read ``count`` 4-byte ints from an indexed table."""
            if count <= 0 or not ptr:
                return []
            raw = string_at(ptr, count * 4)
            return list(struct.unpack_from("<%di" % count, raw))

        # facet_fin: lookup table {facet, fin} (8 bytes/record); triangle
        # facets own 3 consecutive fins.  -1 separates hole loops (only with
        # shape=any) and must be skipped.
        ff_ptr, ff_len = table_wrapper(data[FCTAB_FACET_FIN])
        fin_of_facet: dict[int, list[int]] = {}
        for facet, fin in pairs(ff_ptr, ff_len):
            if fin >= 0 and facet >= 0:
                fin_of_facet.setdefault(facet, []).append(fin)

        # fin_data: indexed table data[fin] -> data index.
        fd_ptr, fd_len = table_wrapper(data[FCTAB_FIN_DATA])
        fin_data = ints(fd_ptr, fd_len)
        # data_point_idx: indexed table point[data] -> point_vec index.
        dp_ptr, dp_len = table_wrapper(data[FCTAB_DATA_POINT_IDX])
        point_of_data = ints(dp_ptr, dp_len)
        # point_vec: indexed table of PK_VECTOR_t coordinates.
        pv_ptr, pv_len = table_wrapper(data[FCTAB_POINT_VEC])
        if pv_len <= 0 or not pv_ptr:
            return None
        raw = string_at(pv_ptr, pv_len * 24)
        points = np.frombuffer(
            raw, dtype="<f8", count=pv_len * 3).reshape(-1, 3).copy()

        tris: list[list[int]] = []
        for facet in sorted(fin_of_facet):
            fins = fin_of_facet[facet]
            if len(fins) < 3:
                continue
            verts: list[int] = []
            ok = True
            for f in fins[:3]:
                if not (0 <= f < len(fin_data)):
                    ok = False
                    break
                di = fin_data[f]
                if not (0 <= di < len(point_of_data)):
                    ok = False
                    break
                pi = point_of_data[di]
                if not (0 <= pi < len(points)):
                    ok = False
                    break
                verts.append(pi)
            if ok and len(set(verts)) == 3:
                tris.append(verts)
        if not tris:
            return None
        return TessPart(
            name=name,
            points=points,
            triangles=np.asarray(tris, dtype=np.int32),
            tag=tag,
        )

    def facet2(self, tag: int, *,
               facet_tol: float = DEFAULT_FACET_TOL,
               facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
               local_tols: Optional[list[tuple[int, tuple[float, ...]]]]
               = None) -> Optional[TessPart]:
        """Facet one body through PK_TOPOL_facet_2 and decode tables."""
        result = self._facet2_call(
            [tag], facet_tol=facet_tol, facet_angle_deg=facet_angle_deg,
            local_tols=local_tols)
        if result is None:
            return None
        return self._decode_result(result, tag, self.body_name(tag))

    def body_faces(self, tag: int) -> Optional[list[int]]:
        """Return the PK_FACE tags owned by a body (per-face probing)."""
        pk = self.pk
        pk.PK_BODY_ask_faces.restype = c_int
        pk.PK_BODY_ask_faces.argtypes = [
            c_int, POINTER(c_int), POINTER(c_void_p)]
        n = c_int(0)
        faces = c_void_p()
        rc = pk.PK_BODY_ask_faces(tag, byref(n), byref(faces))
        if rc != 0 or n.value <= 0 or not faces:
            return None
        return list(cast(faces, POINTER(c_int * n.value)).contents)

    def body_vertices(self, tag: int) -> Optional[np.ndarray]:
        """Real B-rep vertex coordinates of a body (PK_FACE_ask_vertices).

        Used by the gridding "All / Representative" vertex detection:
        STpre reads the Parasolid vertices, not the display mesh points.
        """
        faces = self.body_faces(tag)
        if not faces:
            return None
        pk = self.pk
        pk.PK_FACE_ask_vertices.restype = c_int
        pk.PK_FACE_ask_vertices.argtypes = [
            c_int, POINTER(c_int), POINTER(c_void_p)]
        pk.PK_VERTEX_ask_point.restype = c_int
        pk.PK_VERTEX_ask_point.argtypes = [c_int, POINTER(c_double)]
        pts: list[list[float]] = []
        seen: set[int] = set()
        for ft in faces:
            n = c_int(0)
            arr = c_void_p()
            if pk.PK_FACE_ask_vertices(ft, byref(n), byref(arr)) != 0:
                continue
            if n.value <= 0 or not arr:
                continue
            for vt in cast(arr, POINTER(c_int * n.value)).contents:
                if vt in seen:
                    continue
                seen.add(vt)
                xyz = (c_double * 3)()
                if pk.PK_VERTEX_ask_point(vt, xyz) == 0:
                    pts.append([xyz[0], xyz[1], xyz[2]])
        if not pts:
            return None
        return np.asarray(pts, dtype=np.float64)

    def _face_metrics(self, tag: int, *, facet_tol: float,
                      facet_angle_deg: float
                      ) -> Optional[tuple[int, float, float, np.ndarray]]:
        """Facet one face at base tolerances; return
        ``(n_facets, area, max_intra_face_dihedral_deg, points)``."""
        result = self._facet2_call(
            [tag], facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        if result is None:
            return None
        part = self._decode_result(result, tag, "")
        if part is None or len(part.triangles) == 0:
            return None
        pts = part.points
        tris = part.triangles.astype(np.int64)
        a = pts[tris[:, 0]]
        b = pts[tris[:, 1]]
        c = pts[tris[:, 2]]
        nrm = np.cross(b - a, c - a)
        ln = np.linalg.norm(nrm, axis=1)
        ln[ln < 1e-300] = 1.0
        nrm = nrm / ln[:, None]
        area = float(0.5 * ln.sum())
        edges: dict[tuple[int, int], list[int]] = {}
        for i, (t0, t1, t2) in enumerate(tris.tolist()):
            for e in ((t0, t1), (t1, t2), (t2, t0)):
                key = (min(e), max(e))
                edges.setdefault(key, []).append(i)
        max_ang = 0.0
        for idxs in edges.values():
            if len(idxs) < 2:
                continue
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    d = float(np.clip(
                        np.dot(nrm[idxs[i]], nrm[idxs[j]]), -1.0, 1.0))
                    ang = float(np.degrees(np.arccos(d)))
                    if ang > max_ang:
                        max_ang = ang
        return len(part.triangles), area, max_ang, pts

    def _adaptive_facet2(self, tag: int, *,
                         facet_tol: float = DEFAULT_FACET_TOL,
                         facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
                         refine_angle_deg: float = DEFAULT_REFINE_ANGLE_DEG,
                         refine_tol: float = DEFAULT_REFINE_TOL,
                         smooth_angle_deg: float = DEFAULT_SMOOTH_ANGLE_DEG,
                         min_rel_area: float = DEFAULT_MIN_REL_AREA,
                         min_face_facets: int = DEFAULT_MIN_FACE_FACETS
                         ) -> Optional[TessPart]:
        """Adaptive PK_TOPOL_facet_2 with per-face local tolerances.

        Strategy (preventive, not post-hoc):
          1. Probe every PK_FACE of the body at the base tolerances.
          2. For each face measure facet count, area and the *intra-face*
             maximum dihedral angle (edges shared inside the same face only,
             so sharp model edges between faces do not pollute the metric).
          3. Select faces whose mesh is angularly coarse (dihedral above
             ``smooth_angle_deg``) AND physically large enough (area >=
             ``min_rel_area`` x body bbox area, at least ``min_face_facets``
             facets).  Tiny fillets stay cheap; large curved faces get a
             tighter local ``surface_plane_ang/tol``.
          4. One final body-level facet_2 call attaches the local tolerance
             sets to exactly those faces (PK_facet_local_tolerances_t).

        Falls back to a plain body facet_2 when probing is not possible.
        """
        faces = self.body_faces(tag)
        if not faces:
            return self.facet2(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        rows: list[tuple[int, int, float, float]] = []
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        for ft in faces:
            m = self._face_metrics(
                ft, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
            if m is None:
                return self.facet2(
                    tag, facet_tol=facet_tol,
                    facet_angle_deg=facet_angle_deg)
            nf, area, ang, pts = m
            rows.append((ft, nf, area, ang))
            pmin = pts.min(0)
            pmax = pts.max(0)
            lo = np.minimum(lo, pmin)
            hi = np.maximum(hi, pmax)
        d = hi - lo
        bbox_area = 2.0 * (d[0] * d[1] + d[1] * d[2] + d[2] * d[0])
        if bbox_area <= 0:
            bbox_area = 1.0
        sel = [
            (ft, nf) for ft, nf, area, ang in rows
            if ang > float(smooth_angle_deg)
            and area >= float(min_rel_area) * bbox_area
            and nf >= int(min_face_facets)
        ]
        if not sel:
            return self.facet2(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        local = [
            (ft, (0.0, 0.0, 0.0, float(refine_tol),
                  float(refine_angle_deg) * 0.017453292519943295))
            for ft, _nf in sel
        ]
        return self.facet2(
            tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg,
            local_tols=local)

    def facet_body_adaptive(self, tag: int, **kw) -> Optional[TessPart]:
        """Adaptive facet_2, with the GO path as final fallback."""
        part = self._adaptive_facet2(tag, **kw)
        if part is not None:
            return part
        return self.facet_go(
            tag, facet_tol=kw.get("facet_tol", DEFAULT_FACET_TOL),
            facet_angle_deg=kw.get("facet_angle_deg",
                                   DEFAULT_FACET_ANGLE_DEG))

    # -- PK_TOPOL_render_facet GO fallback ---------------------------------
    def facet_go(self, tag: int, *,
                 facet_tol: float = DEFAULT_FACET_TOL,
                 facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG
                 ) -> Optional[TessPart]:
        pk = self.pk
        self._segs.clear()

        class _GoOpts(Structure):
            _fields_ = [
                ("o_t_version", c_int), ("go_normals", c_int),
                ("go_parameters", c_int), ("go_curvatures", c_int),
                ("go_edges", c_int), ("go_strips", c_int),
                ("go_max_facets_per_strip", c_int),
                ("go_interleaved", c_int), ("split_strips", c_int),
                ("consistent_parms", c_int),
            ]

        class _MeshOpts(Structure):
            _fields_ = [
                ("o_t_version", c_int),
                ("shape", c_int), ("match", c_int), ("density", c_int),
                ("cull", c_int), ("n_loops", c_int), ("loops", c_void_p),
                ("max_facet_sides", c_int),
                ("is_min_facet_width", c_int), ("min_facet_width", c_double),
                ("is_max_facet_width", c_int), ("max_facet_width", c_double),
                ("is_curve_chord_tol", c_int), ("curve_chord_tol", c_double),
                ("is_curve_chord_max", c_int), ("curve_chord_max", c_double),
                ("is_curve_chord_ang", c_int), ("curve_chord_ang", c_double),
                ("is_surface_plane_tol", c_int),
                ("surface_plane_tol", c_double),
                ("is_surface_plane_ang", c_int),
                ("surface_plane_ang", c_double),
                ("is_facet_plane_tol", c_int), ("facet_plane_tol", c_double),
                ("is_facet_plane_ang", c_int), ("facet_plane_ang", c_double),
                ("is_local_density_tol", c_int),
                ("local_density_tol", c_double),
                ("is_local_density_ang", c_int),
                ("local_density_ang", c_double),
                ("degen", c_int), ("n_view_directions", c_int),
                ("view_directions", c_void_p), ("n_local_tols", c_int),
                ("local_tols", c_void_p),
                ("n_topols_with_local_tols", c_int),
                ("topols_with_local_tols", c_void_p),
                ("local_tols_for_topols", c_void_p),
                ("ignore", c_int), ("ignore_value", c_double),
                ("ignore_scope", c_int), ("wire_edges", c_int),
                ("incremental_facetting", c_int),
                ("incremental_method", c_int),
                ("incremental_propagation", c_int),
                ("incremental_transformation", c_int),
                ("incremental_refinement", c_int),
                ("incremental_report", c_int),
                ("inflect", c_int), ("quality", c_int),
                ("vertices_on_planar", c_int), ("respect_offset", c_int),
                ("n_bodies_with_scales", c_int),
                ("bodies_with_scales", c_void_p),
                ("scale_factors", c_void_p),
                ("n_viewports", c_int), ("viewports", c_void_p),
            ]

        class _RenderOpts(Structure):
            _fields_ = [("control", _MeshOpts), ("go_option", _GoOpts)]

        opts = _RenderOpts()
        opts.control.o_t_version = 1
        opts.go_option.o_t_version = 1
        opts.control.max_facet_sides = 3
        opts.control.is_surface_plane_tol = 1
        opts.control.surface_plane_tol = max(float(facet_tol), 1e-12)
        opts.control.is_surface_plane_ang = 1
        opts.control.surface_plane_ang = max(
            float(facet_angle_deg) * 0.017453292519943295, 1e-6)
        pk.PK_TOPOL_render_facet.restype = c_int
        pk.PK_TOPOL_render_facet.argtypes = [
            c_int, POINTER(c_int), c_void_p, c_void_p,
            POINTER(_RenderOpts)]
        rc = pk.PK_TOPOL_render_facet(
            1, (c_int * 1)(tag), None, None, byref(opts))
        if rc != 0:
            return None
        pts: list[list[float]] = []
        tris: list[list[int]] = []
        index: dict[tuple[float, float, float], int] = {}

        def vid(x, y, z):
            key = (round(x, 12), round(y, 12), round(z, 12))
            i = index.get(key)
            if i is None:
                i = len(pts)
                index[key] = i
                pts.append([x, y, z])
            return i

        for st, coords, lt in self._segs:
            if st != _SGTPFT or len(coords) < 9:
                continue
            if len(lt) > 2 and lt[2] != 1:
                continue
            nverts = lt[3] if len(lt) > 3 else len(coords) // 3
            if nverts < 3:
                continue
            v0 = vid(coords[0], coords[1], coords[2])
            prev = vid(coords[3], coords[4], coords[5])
            for k in range(2, nverts):
                cur = vid(coords[3 * k], coords[3 * k + 1],
                          coords[3 * k + 2])
                tris.append([v0, prev, cur])
                prev = cur
        if not tris:
            return None
        return TessPart(
            name=self.body_name(tag),
            points=np.asarray(pts, dtype=np.float64),
            triangles=np.asarray(tris, dtype=np.int32),
            tag=tag,
        )

    def facet_body(self, tag: int, **kw) -> Optional[TessPart]:
        part = self.facet2(tag, **kw)
        if part is None:
            part = self.facet_go(tag, **kw)
        return part


def _get_session() -> _PsSession:
    global _session
    if _session is not None:
        return _session
    prog = find_cradle_programs()
    if prog is None:
        raise RuntimeError(
            "Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    _session = _PsSession(prog)
    return _session


def tessellate_xt_file(path: str | Path, **kw) -> list[TessPart]:
    return tessellate_xt(Path(path).read_bytes(), **kw)


def tessellate_xt(xt_bytes: bytes, *, adaptive: bool = False,
                  **kw) -> list[TessPart]:
    """Tessellate every body in a text ``.x_t`` byte stream.

    Uses the reverse-engineered ``PK_TOPOL_facet_2`` table path (the same
    one STpre uses), with a ``PK_TOPOL_render_facet`` GO fallback per body.
    Pass ``adaptive=True`` to enable per-face local-tolerance refinement of
    large, angularly-coarse curved faces (see ``facet_body_adaptive``); the
    default stays on the plain STpre-style tolerances.
    """
    sess = _get_session()
    tags = sess.receive_xt(xt_bytes)
    out: list[TessPart] = []
    for tag in tags:
        if adaptive:
            part = sess.facet_body_adaptive(tag, **kw)
        else:
            part = sess.facet_body(tag, **kw)
        if part is not None and part.triangles.size:
            out.append(part)
    return out


def write_obj(path: str | Path, parts: list[TessPart]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        base = 0
        for part in parts:
            f.write(f"o {part.name}\n")
            for x, y, z in part.points:
                f.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
            for a, b, c in part.triangles:
                f.write(f"f {a + 1 + base} {b + 1 + base} {c + 1 + base}\n")
            base += len(part.points)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Tessellate a Parasolid .x_t via pskernel PK_TOPOL_facet_2 "
                    "(reverse-engineered STpre node path).")
    ap.add_argument("xt", type=Path, help="input text .x_t file")
    ap.add_argument("--obj", type=Path, default=None,
                    help="optional Wavefront OBJ output")
    ap.add_argument("--tol", type=float, default=DEFAULT_FACET_TOL,
                    help="surface facet distance tolerance")
    ap.add_argument("--angle", type=float, default=DEFAULT_FACET_ANGLE_DEG,
                    help="surface facet angle tolerance (degrees)")
    ap.add_argument("--adaptive", action="store_true",
                    help="per-face adaptive refinement of large curved faces")
    ap.add_argument("--refine-angle", type=float,
                    default=DEFAULT_REFINE_ANGLE_DEG,
                    help="local angle tolerance for refined faces (degrees)")
    args = ap.parse_args()
    parts = tessellate_xt_file(
        args.xt, facet_tol=args.tol, facet_angle_deg=args.angle,
        adaptive=args.adaptive, refine_angle_deg=args.refine_angle)
    for p in parts:
        print(f"{p.name}: {len(p.points)} nodes, {len(p.triangles)} triangles")
    if args.obj:
        write_obj(args.obj, parts)
        print(f"wrote {args.obj}")


if __name__ == "__main__":
    main()
