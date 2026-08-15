"""IFC (Industry Foundation Classes) import/export for STpre-style parts.

Import reads IFC-SPF (STEP physical file, IFC2X3/IFC4) building models and
creates cube parts (walls/slabs/columns/beams/proxies) with 4x4 part
transforms, reproducing the STpre CAD-Interface behaviour of turning BIM
extrusions into rectangular solids.  Export writes a minimal, schema-valid
IFC2X3 file from the current cuboid/panel parts.

Units: IFC is SI (metres); the model is millimetres, so import multiplies
by 1000 and export divides by 1000.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from cab_edit_ops import _ear_clip
from cab_import import ImportedBody

_PRODUCTS = {
    'IFCWALL', 'IFCWALLSTANDARDCASE', 'IFCSLAB', 'IFCCOLUMN', 'IFCBEAM',
    'IFCFOOTING', 'IFCPLATE', 'IFCROOF', 'IFCPROXY',
    'IFCBUILDINGELEMENTPROXY', 'IFCFLOWSEGMENT', 'IFCSTAIR', 'IFCRAMP',
    'IFCMEMBER', 'IFCCURTAINWALL', 'IFCPILE', 'IFCRAILING',
}


@dataclass
class IfcSolid:
    name: str
    entity: str
    base: tuple
    size: tuple
    matrix: tuple
    global_id: str = ''
    radius: float = 0.0      # circle-profile extrusions (mm)
    kind: str = 'cube'       # cube | cylinder | polygon
    points: tuple = ()       # polygon-profile footprint (mm, xy pairs)


def _split_args(s: str) -> list:
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in ' \t\r\n':
            i += 1
            continue
        if c == '(':
            depth = 1
            j = i + 1
            while j < n and depth:
                if s[j] == '(':
                    depth += 1
                elif s[j] == ')':
                    depth -= 1
                j += 1
            out.append(_split_args(s[i + 1:j - 1]))
            i = j
            continue
        if c == ',':
            i += 1
            continue
        if c == chr(39):
            j = i + 1
            buf = []
            while j < n:
                if s[j] == chr(39):
                    if j + 1 < n and s[j + 1] == chr(39):
                        buf.append(chr(39))
                        j += 2
                        continue
                    break
                buf.append(s[j])
                j += 1
            out.append(''.join(buf))
            i = j + 1
            continue
        j = i
        while j < n and s[j] not in ',) \t\r\n':
            j += 1
        out.append(s[i:j])
        i = j
    return out


def parse_ifc_statements(text: str) -> dict:
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    stmts = {}
    for m in re.finditer(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*?)\);',
                         text, flags=re.S):
        stmts[int(m.group(1))] = (m.group(2), _split_args(m.group(3)))
    return stmts


def _ref_id(arg):
    if isinstance(arg, str) and arg.startswith('#'):
        try:
            return int(arg[1:])
        except ValueError:
            return None
    return None


def _vec(args, default=(0.0, 0.0, 1.0)) -> tuple:
    if not args:
        return tuple(default)
    vals = []
    for a in args:
        try:
            vals.append(float(a))
        except (TypeError, ValueError):
            pass
    if len(vals) < 3:
        vals = list(default)
    return (vals[0], vals[1], vals[2])

def _placement_matrix(stmts, pid) -> np.ndarray:
    m = np.eye(4)
    while pid is not None:
        ent, args = stmts.get(pid, (None, []))
        if ent is None:
            break
        if ent == 'IFCLOCALPLACEMENT':
            rel = _ref_id(args[0]) if args else None
            parent = _ref_id(args[1]) if len(args) > 1 else None
            if (rel is not None
                    and stmts.get(rel, ('',))[0] == 'IFCAXIS2PLACEMENT3D'):
                m = _axis2placement(stmts, rel) @ m
            pid = parent
        elif ent == 'IFCAXIS2PLACEMENT3D':
            m = _axis2placement(stmts, pid) @ m
            pid = None
        else:
            pid = None
    return m


def _axis2placement(stmts, pid: int) -> np.ndarray:
    _, args = stmts.get(pid, ('', []))
    if not args:
        return np.eye(4)
    p = _vec(_point_args(stmts, args[0]))
    z = _vec(_dir_args(stmts, args[1]) if len(args) > 1 else None,
             (0.0, 0.0, 1.0))
    x = _vec(_dir_args(stmts, args[2]) if len(args) > 2 else None,
             (1.0, 0.0, 0.0))
    z = np.asarray(z, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    nz = np.linalg.norm(z)
    z = z / nz if nz > 0 else np.array([0.0, 0.0, 1.0])
    x = x - (x @ z) * z
    nx = np.linalg.norm(x)
    if nx < 1e-12:
        cand = np.array([1.0, 0.0, 0.0])
        cand = cand - (cand @ z) * z
        if np.linalg.norm(cand) < 1e-12:
            cand = np.array([0.0, 1.0, 0.0])
            cand = cand - (cand @ z) * z
        x = cand
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    m = np.eye(4)
    m[:3, 0] = x
    m[:3, 1] = y
    m[:3, 2] = z
    m[:3, 3] = p
    return m


def _point_args(stmts, arg):
    pid = _ref_id(arg)
    if pid is None:
        return arg if isinstance(arg, list) else None
    ent, args = stmts.get(pid, (None, []))
    return args[0] if ent == 'IFCCARTESIANPOINT' else None


def _dir_args(stmts, arg):
    pid = _ref_id(arg)
    if pid is None:
        return arg if isinstance(arg, list) else None
    ent, args = stmts.get(pid, (None, []))
    return args[0] if ent == 'IFCDIRECTION' else None


def _iter_args(arg):
    if arg is None:
        return []
    if isinstance(arg, list):
        out = []
        for a in arg:
            out.extend(_iter_args(a))
        return out
    return [arg]

def _product_info(stmts, pid: int) -> tuple:
    ent, args = stmts.get(pid, ('', []))
    name = ''
    if len(args) > 2 and isinstance(args[2], str) and args[2] != '$':
        name = args[2]
    if not name:
        for a in args[:5]:
            if (isinstance(a, str) and not a.startswith('#') and a != '$'
                    and not re.fullmatch(r'[0-9A-Za-z_$]{20,24}', a)):
                name = a
                break
    placement = []
    reprs = []
    for a in args:
        for p in _iter_args(a):
            rid = _ref_id(p)
            if rid is not None:
                pe = stmts.get(rid, ('',))[0]
                if pe in ('IFCLOCALPLACEMENT', 'IFCGRIDPLACEMENT'):
                    placement.append(rid)
                elif pe == 'IFCPRODUCTDEFINITIONSHAPE':
                    reprs.append(rid)
    return name, placement[0] if placement else None, reprs


def _extruded_boxes(stmts, repr_ids) -> list:
    boxes = []
    for rid in repr_ids:
        _, args = stmts.get(rid, ('', []))
        reps = args[2] if len(args) > 2 else None
        for rep in _iter_args(reps):
            srid = _ref_id(rep)
            if srid is None:
                continue
            sent, sargs = stmts.get(srid, ('', []))
            if sent != 'IFCSHAPEREPRESENTATION':
                continue
            items = sargs[3] if len(sargs) > 3 else None
            for item in _iter_args(items):
                eid = _ref_id(item)
                if eid is None:
                    continue
                eent, eargs = stmts.get(eid, ('', []))
                if eent != 'IFCEXTRUDEDAREASOLID' or len(eargs) < 4:
                    continue
                prof_id = _ref_id(eargs[0])
                sol_pl = _ref_id(eargs[1])
                if prof_id is None:
                    continue
                pent, pargs = stmts.get(prof_id, ('', []))
                depth = float(eargs[3])
                sm = _placement_matrix(stmts, sol_pl)
                if pent == 'IFCCIRCLEPROFILEDEF' and len(pargs) >= 3:
                    # IFC2X3: (ProfileType, ProfileName, Position, Radius)
                    idx = 3 if len(pargs) >= 4 else 2
                    try:
                        radius = float(pargs[idx])
                    except (TypeError, ValueError):
                        continue
                    boxes.append({'kind': 'circle', 'radius': radius,
                                  'depth': depth, 'solid': sm})
                    continue
                if pent == 'IFCARBITRARYCLOSEDPROFILEDEF' and pargs:
                    # IFC2X3: (ProfileType, ProfileName, OuterCurve)
                    cur_id = _ref_id(pargs[2] if len(pargs) > 2 else None)
                    if cur_id is None:
                        continue
                    cent, cargs = stmts.get(cur_id, ('', []))
                    if cent != 'IFCPOLYLINE' or not cargs:
                        continue
                    fp = []
                    for pref in _iter_args(cargs[0]):
                        pid2 = _ref_id(pref)
                        if pid2 is None:
                            continue
                        _, ppargs = stmts.get(pid2, ('', []))
                        if not ppargs:
                            continue
                        pt = _point_args(stmts, ppargs[0])
                        fp.append((float(pt[0]), float(pt[1])))
                    if len(fp) >= 3:
                        boxes.append({'kind': 'polygon', 'points': fp,
                                      'depth': depth, 'solid': sm})
                    continue
                if pent != 'IFCRECTANGLEPROFILEDEF' or len(pargs) < 5:
                    continue
                px = py = 0.0
                pos2 = _ref_id(pargs[2])
                if pos2 is not None:
                    qent, qargs = stmts.get(pos2, ('', []))
                    if qent == 'IFCAXIS2PLACEMENT2D' and qargs:
                        px, py, _ = _vec(_point_args(stmts, qargs[0]),
                                         (0.0, 0.0, 0.0))
                xdim = float(pargs[3])
                ydim = float(pargs[4])
                depth = float(eargs[3])
                sm = _placement_matrix(stmts, sol_pl)
                boxes.append({'px': px, 'py': py, 'xdim': xdim,
                              'ydim': ydim, 'depth': depth, 'solid': sm})
    return boxes


def parse_ifc(text: str) -> list:
    stmts = parse_ifc_statements(text)
    out = []
    for pid, (ent, args) in sorted(stmts.items()):
        if ent not in _PRODUCTS:
            continue
        name, placement_id, repr_ids = _product_info(stmts, pid)
        boxes = _extruded_boxes(stmts, repr_ids)
        if not boxes:
            continue
        pm = _placement_matrix(stmts, placement_id)
        for bi, box in enumerate(boxes):
            m = pm @ box['solid']
            mrot = m.copy()
            mrot[:3, 3] = 0.0
            mat = tuple(float(v) for v in mrot.T.reshape(-1))
            nm = name or (ent + str(pid))
            if len(boxes) > 1:
                nm = nm + '_' + str(bi + 1)
            if box.get('kind') == 'polygon':
                fp_mm = [(x * 1000.0, y * 1000.0) for x, y in
                         box['points']]
                d = box['depth'] * 1000.0
                xs = [x for x, _y in fp_mm]
                ys = [_y for _x, _y in fp_mm]
                o = m @ np.array([0.0, 0.0, 0.0, 1.0])
                base = tuple(float(v) * 1000.0 for v in o[:3])
                out.append(IfcSolid(
                    name=nm, entity=ent, base=base,
                    size=(max(xs) - min(xs), max(ys) - min(ys), d),
                    matrix=mat, kind='polygon',
                    points=tuple(fp_mm)))
                continue
            if box.get('kind') == 'circle':
                r = box['radius'] * 1000.0
                d = box['depth'] * 1000.0
                o = m @ np.array([0.0, 0.0, 0.0, 1.0])
                base = tuple(float(v) * 1000.0 for v in o[:3])
                out.append(IfcSolid(name=nm, entity=ent, base=base,
                                    size=(2.0 * r, 2.0 * r, d),
                                    matrix=mat, radius=r,
                                    kind='cylinder'))
                continue
            o = m @ np.array([box['px'], box['py'], 0.0, 1.0])
            base = tuple(float(v) * 1000.0 for v in o[:3])
            size = (box['xdim'] * 1000.0, box['ydim'] * 1000.0,
                    box['depth'] * 1000.0)
            out.append(IfcSolid(name=nm, entity=ent, base=base, size=size,
                                matrix=mat))
    return out


def import_ifc_path(path) -> list:
    return parse_ifc(Path(path).read_text(encoding='utf-8',
                                          errors='replace'))


def _prism_stl_bytes(points_mm, depth_mm) -> bytes:
    """Polyline footprint + depth -> text STL bytes (metres).

    Ear-clips the footprint polygon and extrudes it into a closed
    triangular prism (bottom + top fans + side quads).
    """
    fp = [np.array([x / 1000.0, y / 1000.0, 0.0]) for x, y in points_mm]
    d = depth_mm / 1000.0
    n = len(fp)
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])
    tris = _ear_clip(fp, u, v)
    if not tris:
        return b''
    def facet(a, b, c):
        return ('facet normal 0 0 0\n outer loop\n'
                + ''.join(f'  vertex {q[0]:.12g} {q[1]:.12g} {q[2]:.12g}\n'
                          for q in (a, b, c))
                + ' endloop\nendfacet\n')
    out = ['solid profile']
    for i, j, k in tris:
        out.append(facet(fp[i], fp[j], fp[k]))
    for i, j, k in tris:
        top = [np.array([q[0], q[1], d]) for q in fp]
        out.append(facet(top[i], top[k], top[j]))
    for i in range(n):
        j = (i + 1) % n
        a, b = fp[i], fp[j]
        c, dd = np.array([a[0], a[1], d]), np.array([b[0], b[1], d])
        out.append(facet(a, b, dd))
        out.append(facet(a, dd, c))
    out.append('endsolid profile')
    return ('\n'.join(out) + '\n').encode('ascii')


def register_ifc_parts(model, solids, kind_map=None, archive=None) -> list:
    from cab_parts import register_primitive
    km = kind_map or {}
    names = []
    for s in solids:
        kind = km.get(s.entity, s.kind if s.kind != 'cube' else 'cube')
        name = s.name
        i = 2
        while model.find_part(name) is not None:
            name = s.name + '_' + str(i)
            i += 1
        if s.kind == 'polygon' and archive is not None:
            from cab_import import add_stl_member, register_parts
            raw = _prism_stl_bytes(s.points, s.size[2])
            if not raw:
                continue
            member = f'{name}.stl'
            add_stl_member(archive, raw, name=member)
            register_parts(model, [ImportedBody(name=name, tag=0,
                                            tess=None)],
                           kind='polygon',
                           transform=tuple(float(v) for v in s.matrix))
            from cabxml import _first, set_text
            el = model.find_part(name)
            if el is not None:
                f = _first(el, 'file')
                if f is None:
                    import xml.etree.ElementTree as ET
                    f = ET.SubElement(el, 'file')
                    f.tail = '\n         '
                set_text(f, member)
            names.append(name)
            continue
        params = {'base': s.base, 'size': s.size}
        if s.kind == 'cylinder':
            params = {'center': s.base, 'radius': s.radius,
                      'height': s.size[2], 'direction': '+Z'}
        ok = register_primitive(model, name=name, kind=kind, params=params)
        if ok:
            model.set_part_transform(
                name, ','.join(format(v, '.12g') for v in s.matrix))
            names.append(name)
    return names

def _fmt(v) -> str:
    return format(v, '.12g')


class _IfcWriter:
    def __init__(self):
        self.lines = []
        self.n = 0

    def _scalar(self, a) -> str:
        if isinstance(a, (int, float)):
            return _fmt(a)
        if isinstance(a, str):
            if a.startswith('#') or a == '$' or a.startswith('.'):
                return a
            return chr(39) + a.replace(chr(39), chr(39) * 2) + chr(39)
        return str(a)

    def add(self, entity: str, args: list) -> int:
        self.n += 1
        rendered = []
        for a in args:
            if isinstance(a, (list, tuple)):
                rendered.append('(' + ','.join(self._scalar(x) for x in a)
                                + ')')
            else:
                rendered.append(self._scalar(a))
        self.lines.append('#' + str(self.n) + '=' + entity + '('
                          + ','.join(rendered) + ');')
        return self.n

    def text(self) -> str:
        q = chr(39)
        header = (
            'ISO-10303-21;\nHEADER;\n'
            + 'FILE_DESCRIPTION((' + q + 'scSTREAM Pre export' + q
            + '),' + q + '2;1' + q + ');\n'
            + 'FILE_NAME(' + q + 'model.ifc' + q + ',' + q
            + '2026-01-01T00:00:00' + q + ',(' + q + q + '),(' + q + q
            + '),' + q + 'scSTREAM Pre' + q + ',' + q + 'scSTREAM Pre' + q
            + ',' + q + q + ');\n'
            + 'FILE_SCHEMA((' + q + 'IFC2X3' + q + '));\n'
            + 'ENDSEC;\n\nDATA;\n')
        return header + '\n'.join(self.lines)
        + '\nENDSEC;\nEND-ISO-10303-21;\n'


def _parse_triple(text, default):
    if not (text or '').strip():
        return list(default)
    v = [float(x) for x in text.replace(',', ' ').split()]
    return (v + list(default))[:3]


def _part_box(p):
    """(base, size, matrix) of a cuboid-ish PartInfo in mm."""
    if not (p.base or '').strip() or not (p.size or '').strip():
        return None
    base = _parse_triple(p.base, (0.0, 0.0, 0.0))
    size = _parse_triple(p.size, (0.0, 0.0, 0.0))
    t = _parse_triple(p.transform, (1.0, 0.0, 0.0))
    while len(t) < 16:
        t.append(0.0)
    m = np.asarray(t[:16], dtype=np.float64).reshape(4, 4)
    return base, size, m

def model_to_ifc(model) -> str:
    w = _IfcWriter()
    g = '0' * 22
    proj = w.add('IFCPROJECT', [g, 'scSTREAM Pre', 'model', 'model',
                                '$', '$', '$', [], '$'])
    site = w.add('IFCSITE', [g, 'Site'] + ['$'] * 11)
    bld = w.add('IFCBUILDING', [g, 'Building'] + ['$'] * 11)
    storey = w.add('IFCBUILDINGSTOREY', [g, 'Storey'] + ['$'] * 9)
    contained = []
    for p in model.parts():
        box = _part_box(p)
        if box is None:
            continue
        base, size, m = box
        name = p.name
        ox, oy, oz = base
        zx, zy, zz = float(m[0, 2]), float(m[1, 2]), float(m[2, 2])
        xx, xy, xz = float(m[0, 0]), float(m[1, 0]), float(m[2, 0])
        pt = w.add('IFCCARTESIANPOINT', [[ox / 1000.0, oy / 1000.0,
                                          oz / 1000.0]])
        axis = w.add('IFCAXIS2PLACEMENT3D', ['#' + str(pt),
                                             [zx, zy, zz], [xx, xy, xz]])
        loc = w.add('IFCLOCALPLACEMENT', ['#' + str(axis)])
        p2 = w.add('IFCCARTESIANPOINT', [[0, 0]])
        pos2 = w.add('IFCAXIS2PLACEMENT2D', ['#' + str(p2)])
        prof = w.add('IFCRECTANGLEPROFILEDEF', ['.RECTANGLE.', '$',
                                                '#' + str(pos2),
                                                size[0] / 1000.0,
                                                size[1] / 1000.0])
        extr = w.add('IFCEXTRUDEDAREASOLID', ['#' + str(prof), '$',
                                              [0, 0, 1], size[2] / 1000.0])
        ctx = w.add('IFCREPRESENTATIONCONTEXT', ['Body', 'Body', 'Model',
                                                 '$', '$'])
        rep = w.add('IFCSHAPEREPRESENTATION', ['#' + str(ctx), 'Body',
                                               'SweptSolid',
                                               ['#' + str(extr)]])
        shape = w.add('IFCPRODUCTDEFINITIONSHAPE', ['$', '$',
                                                    ['#' + str(rep)]])
        sx, sy, sz = size
        is_slab = sz < 400.0 and max(sx, sy) > 0
        if is_slab:
            ent = 'IFCSLAB'
        elif sz > max(sx, sy):
            ent = 'IFCWALLSTANDARDCASE'
        else:
            ent = 'IFCPROXY'
        prod = w.add(ent, [g, name, '$', '$', '$', '#' + str(loc),
                           '#' + str(shape), '$', '$', '$', '$'])
        contained.append(prod)
    w.add('IFCRELAGGREGATES', [g, '$', '$', '$', '#' + str(proj),
                               ['#' + str(site), '#' + str(bld),
                                '#' + str(storey)]])
    w.add('IFCRELCONTAINEDINSPATIALSTRUCTURE',
          [g, '$', '$', '$', ['#' + str(p) for p in contained],
           '#' + str(storey)])
    return w.text()
