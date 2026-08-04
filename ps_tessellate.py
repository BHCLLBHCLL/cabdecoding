"""Tessellate Parasolid ``.x_t`` bodies via Cradle ``pskernel.dll`` + GO.

Requires a Cradle CFD install with ``Programs_x64/pskernel.dll`` and
``Schemas/``.  When the kernel is unavailable, callers should fall back to
mesh occupancy boxes.

Faceting uses explicit surface distance/angle tolerances instead of the
kernel-internal defaults so curved B-rep faces are fine enough to match the
STpre look.  Tune with ``tessellate_xt(..., facet_tol=..., facet_angle_deg=...)``.
"""

from __future__ import annotations

import ctypes
import os
import tempfile
from ctypes import (
    CFUNCTYPE, POINTER, Structure, byref, c_char, c_char_p,
    c_double, c_int, c_void_p, cast, memmove, memset, sizeof, string_at,
)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# GO tokens (Parasolid Graphical Output)
_SGTPFT = 2016          # facet segment
_L3TPFV = 3007          # facet vertices (ngeom = #vectors)
_L3TPFN = 3008          # facet vertices plus surface normals

_DEFAULT_CRADLE = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
DEFAULT_FACET_TOL = 1e-4       # surface-to-facet distance bound (model units)
DEFAULT_FACET_ANGLE_DEG = 12.0 # max surface normal swing per facet (degrees)


class _FacetMeshOptions(Structure):
    """PK_TOPOL_facet_mesh_o_t layout (x64 Windows / Cradle pack)."""

    _fields_ = [
        ("o_t_version", c_int),
        ("shape", c_int), ("match", c_int), ("density", c_int), ("cull", c_int),
        ("n_loops", c_int), ("loops", c_void_p),
        ("max_facet_sides", c_int),
        ("is_min_facet_width", c_int), ("min_facet_width", c_double),
        ("is_max_facet_width", c_int), ("max_facet_width", c_double),
        ("is_curve_chord_tol", c_int), ("curve_chord_tol", c_double),
        ("is_curve_chord_max", c_int), ("curve_chord_max", c_double),
        ("is_curve_chord_ang", c_int), ("curve_chord_ang", c_double),
        ("is_surface_plane_tol", c_int), ("surface_plane_tol", c_double),
        ("is_surface_plane_ang", c_int), ("surface_plane_ang", c_double),
        ("is_facet_plane_tol", c_int), ("facet_plane_tol", c_double),
        ("is_facet_plane_ang", c_int), ("facet_plane_ang", c_double),
        ("is_local_density_tol", c_int), ("local_density_tol", c_double),
        ("is_local_density_ang", c_int), ("local_density_ang", c_double),
        ("degen", c_int),
        ("n_view_directions", c_int), ("view_directions", c_void_p),
        ("n_local_tols", c_int), ("local_tols", c_void_p),
        ("n_topols_with_local_tols", c_int),
        ("topols_with_local_tols", c_void_p),
        ("local_tols_for_topols", c_void_p),
        ("ignore", c_int), ("ignore_value", c_double), ("ignore_scope", c_int),
        ("wire_edges", c_int),
        ("incremental_facetting", c_int), ("incremental_method", c_int),
        ("incremental_propagation", c_int),
        ("incremental_transformation", c_int),
        ("incremental_refinement", c_int), ("incremental_report", c_int),
        ("inflect", c_int), ("quality", c_int), ("vertices_on_planar", c_int),
        ("respect_offset", c_int),
        ("n_bodies_with_scales", c_int), ("bodies_with_scales", c_void_p),
        ("scale_factors", c_void_p),
        ("n_viewports", c_int), ("viewports", c_void_p),
    ]


class _RenderFacetGoOptions(Structure):
    """PK_TOPOL_render_facet_go_o_t layout."""

    _fields_ = [
        ("o_t_version", c_int),
        ("go_normals", c_int),
        ("go_parameters", c_int),
        ("go_curvatures", c_int),
        ("go_edges", c_int),
        ("go_strips", c_int),
        ("go_max_facets_per_strip", c_int),
        ("go_interleaved", c_int),
        ("split_strips", c_int),
        ("consistent_parms", c_int),
    ]


class _RenderFacetOptions(Structure):
    """PK_TOPOL_render_facet_o_t = control + go_option."""

    _fields_ = [
        ("control", _FacetMeshOptions),
        ("go_option", _RenderFacetGoOptions),
    ]


@dataclass
class TessPart:
    """Tessellated CAD body."""

    name: str
    points: np.ndarray          # (N, 3) float64
    triangles: np.ndarray       # (M, 3) int32 into points
    tag: int = 0


@dataclass
class _GoCapture:
    segs: list = field(default_factory=list)


_session: Optional["_PsSession"] = None


class _FRU(Structure):
    _fields_ = [(n, c_void_p) for n in (
        "fstart fabort fstop fmallo fmfree gosgmt goopsg goclsg gopixl gooppx "
        "goclpx ffoprd ffopwr ffclos ffread ffwrit ffoprb ffseek fftell fgcrcu "
        "fgcrsu fgevcu fgevsu fgprcu fgprsu ucoprd ucopwr"
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


def find_cradle_programs() -> Optional[Path]:
    """Locate Cradle ``Programs_x64`` containing ``pskernel.dll``."""
    env = os.environ.get("CRADLE_PROGRAMS") or os.environ.get("P_SCHEMA")
    candidates: list[Path] = []
    if env:
        p = Path(env)
        candidates.append(p if p.name.lower() != "schemas" else p.parent)
    candidates.append(_DEFAULT_CRADLE)
    # common sibling installs
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
    return find_cradle_programs() is not None


class _PsSession:
    """One Parasolid session + frustrum for GO faceting."""

    def __init__(self, prog: Path):
        self.prog = prog
        self.schema = prog / "Schemas"
        os.add_dll_directory(str(prog))
        os.environ["PATH"] = str(prog) + ";" + os.environ.get("PATH", "")
        os.environ["P_SCHEMA"] = str(self.schema)
        self.pk = ctypes.WinDLL(str(prog / "pskernel.dll"))
        self._files: dict = {}
        self._next_id = 1
        self._mallo_bufs: list = []
        self._cap = _GoCapture()
        self._build_frustrum()
        self._start()

    def _build_frustrum(self) -> None:
        pk = self.pk
        files = self._files
        schema = self.schema
        cap = self._cap
        mallo = self._mallo_bufs

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
            if is_bin:
                data, loc = raw, 0
            else:
                data = raw.decode("latin-1", "replace")
                loc = 0
                if skiphd[0] == 1:
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
                # L3TPFV: ngeom is vector count → 3*ngeom doubles
                nfloat = ng * 3 if (st == _SGTPFT or
                                    (lt[1:2] == [_L3TPFV])) else ng
                coords = ([geom[i] for i in range(nfloat)]
                          if nfloat and geom else [])
                cap.segs.append((st, coords, lt))
            except Exception:
                pass
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOOPSG(segtyp, ntags, tags, ngeom, geom, nlntp, lntp, ifail):
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOCLSG(segtyp, ntags, tags, ngeom, geom, nlntp, lntp, ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int))
        def GOPIXL(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOOPPX(a, ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOCLPX(a, ifail):
            ifail[0] = 0

        # keep refs
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
        self._fru = fru
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
        pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
        pk.PK_SESSION_set_check_arguments.restype = c_int
        pk.PK_SESSION_set_check_arguments(0)

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
            rc = pk.PK_PART_ask_all_attribs(
                tag, aname, byref(na), byref(attrs))
            if rc != 0 or not na.value:
                continue
            for a in cast(attrs, POINTER(c_int * na.value)).contents:
                s = c_char_p()
                if pk.PK_ATTRIB_ask_string(a, 0, byref(s)) == 0 and s.value:
                    raw = s.value
                    try:
                        text = raw.decode("ascii")
                    except UnicodeDecodeError:
                        # Some non-string attributes return uninitialised
                        # bytes through ask_string; ignore non-ASCII garbage
                        # so a real name like "box" is not shadowed.
                        continue
                    if text and all(32 <= ord(ch) < 127 for ch in text) \
                            and len(text) > len(best):
                        best = text
        return best or f"body_{tag}"

    def facet_body(self, tag: int, *,
                   facet_tol: float = DEFAULT_FACET_TOL,
                   facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG
                   ) -> TessPart:
        """Render one body through GO; return triangle mesh."""
        pk = self.pk
        self._cap.segs.clear()
        # PK_TOPOL_render_facet(n, topols, topol_transfs, view_transf, options)
        opts = _RenderFacetOptions()
        opts.control.o_t_version = 1
        opts.go_option.o_t_version = 1
        # Explicit surface tolerances instead of kernel-internal defaults:
        # STpre-style smooth B-rep needs a chordal distance + angle bound.
        opts.control.max_facet_sides = 3
        opts.control.is_surface_plane_tol = 1
        opts.control.surface_plane_tol = max(float(facet_tol), 1e-12)
        opts.control.is_surface_plane_ang = 1
        opts.control.surface_plane_ang = max(
            float(facet_angle_deg) * 0.017453292519943295, 1e-6)
        pk.PK_TOPOL_render_facet.restype = c_int
        pk.PK_TOPOL_render_facet.argtypes = [
            c_int, POINTER(c_int), c_void_p, c_void_p,
            POINTER(_RenderFacetOptions)]
        rc = pk.PK_TOPOL_render_facet(
            1, (c_int * 1)(tag), None, None, byref(opts))
        if rc != 0:
            raise RuntimeError(f"PK_TOPOL_render_facet failed: {rc}")

        pts: list[list[float]] = []
        tris: list[list[int]] = []
        index: dict[tuple[float, float, float], int] = {}

        def vid(x: float, y: float, z: float) -> int:
            key = (round(x, 12), round(y, 12), round(z, 12))
            i = index.get(key)
            if i is None:
                i = len(pts)
                index[key] = i
                pts.append([x, y, z])
            return i

        for st, coords, lt in self._cap.segs:
            if st != _SGTPFT or len(coords) < 9:
                continue
            # lntp: [occ, L3TPFV, n_loops, nverts0, ...]
            n_loops = lt[2] if len(lt) > 2 else 1
            if n_loops != 1:
                continue
            nverts = lt[3] if len(lt) > 3 else len(coords) // 3
            if nverts < 3:
                continue
            # fan triangulation for n-gons (usually triangles)
            v0 = vid(coords[0], coords[1], coords[2])
            prev = vid(coords[3], coords[4], coords[5])
            for k in range(2, nverts):
                cur = vid(coords[3 * k], coords[3 * k + 1],
                          coords[3 * k + 2])
                tris.append([v0, prev, cur])
                prev = cur

        name = self.body_name(tag)
        return TessPart(
            name=name,
            points=np.asarray(pts, dtype=np.float64),
            triangles=np.asarray(tris, dtype=np.int32),
            tag=tag,
        )


def _get_session() -> _PsSession:
    global _session
    if _session is not None:
        return _session
    try:
        # PK_SESSION_start is process-global: only one pskernel session can
        # exist per process.  If ps_facet2_nodes already started one, reuse
        # it (same receive_xt/body_name/facet_body contract; it prefers the
        # STpre PK_TOPOL_facet_2 table path and falls back to GO).
        import ps_facet2_nodes as _f2
        if _f2._session is not None:
            _session = _f2._session
            return _session
    except Exception:
        pass
    prog = find_cradle_programs()
    if prog is None:
        raise RuntimeError(
            "Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    _session = _PsSession(prog)
    return _session


def tessellate_xt(xt_bytes: bytes, *,
                  facet_tol: float = DEFAULT_FACET_TOL,
                  facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG
                  ) -> list[TessPart]:
    """Receive a text ``.x_t`` stream and tessellate every body."""
    sess = _get_session()
    tags = sess.receive_xt(xt_bytes)
    out: list[TessPart] = []
    for tag in tags:
        try:
            part = sess.facet_body(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        except RuntimeError:
            continue
        if part.triangles.size:
            out.append(part)
    return out


def tessellate_xt_file(path: str | Path) -> list[TessPart]:
    return tessellate_xt(Path(path).read_bytes())
