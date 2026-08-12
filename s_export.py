"""P3: SDAT (.s) solver-input exporter for scSTREAM Pre cab projects.

Generates the same section layout as the official exporter (sample
``tests/ex4_e.s``). Values are derived from the cab XML members:

- CXYZ            <- ``mesh_block`` axis coordinates (mm -> m)
- PARTS           <- ``element`` part box tables + material mapping
- REGION / A_MDR  <- ``analysis_region`` face lists + ``element`` faces
- INIT/FLUX/AMOM/AENT/VENT/VFWL <- ``value`` + ``condition`` bindings
- analysis/control sections <- ``analysis_set`` / ``output`` / ``steady_param``

Some opaque flag lines (header counts, EQUA mask, HSOL, VFDE extras) are kept
as sample-derived constants and flagged for multi-sample verification (P5).
"""

from __future__ import annotations

import re

from cabxml import PropertyModel, StpreModel


def _child_text(el, tag: str, default: str = "") -> str:
    from cabxml import _first
    if el is None:
        return default
    c = _first(el, tag)
    return c.text.strip() if c is not None and c.text else default


def _f(v: float, w: int = 26) -> str:
    return f"{v:{w}.14e}"


def _i(v: int, w: int = 12) -> str:
    return f"{v:{w}d}"


def _name_key(name: str):
    """Sort key that orders Wall1..Wall4 / HeatSource1..8 numerically."""
    m = re.search(r"(\d+)$", name)
    return (name[:m.start()], int(m.group(1))) if m else (name, 0)


class SExport:
    """Builds the SDAT text from a project model."""

    def __init__(self, model: StpreModel, props: PropertyModel):
        self.m = model
        self.p = props
        self.lines: list[str] = []
        self.materials = self._material_order()
        self.parts = self._part_list()

    # -- material / part bookkeeping --------------------------------------

    def _material_order(self) -> dict[str, int]:
        from xemt_export import _ordered_materials, _used_material_names
        return _ordered_materials(self.m, self.p)

    def _part_list(self) -> list[dict]:
        """Ordered part descriptors: id, name, material, fraction, boxes."""
        out: list[dict] = []
        ar = self.m.analysis_region()
        from cabxml import _first
        fluid_name = ""
        if ar is not None:
            prop = _first(ar, "property")
            fluid_name = prop.text.strip() if prop is not None else ""
        mat = self.materials.get(fluid_name, 1)
        out.append({
            "id": 1, "name": _child_text(ar, "name", "Domain"),
            "material": mat, "fraction": 1.0,
            "boxes": self.m.part_boxes(_child_text(ar, "name", "Domain")),
        })
        pid = 1
        for p in self.m.parts():
            pid += 1
            out.append({
                "id": pid, "name": p.name,
                "material": self.materials.get(p.property, 1),
                "fraction": 0.0 if p.attribute == "solid" else 1.0,
                "boxes": self.m.part_boxes(p.name),
            })
        return out

    # -- main render ------------------------------------------------------

    def render(self) -> str:
        self._header()
        self._vfex_unit()
        self._heatpath()
        self._equations()
        self._property()
        self._cxyz()
        self._parts()
        self._regions()
        self._init_region()
        self._flux_region()
        self._amom_region()
        self._aent_region()
        self._vent_region()
        self._vfwl_region()
        self._vfem_vfde()
        self._autofixp()
        self._fout()
        self._meix_var()
        self._balances()
        self._tprt()
        self.lines.append("GOGO")
        return "\r\n".join(self.lines) + "\r\n"

    # -- sections ---------------------------------------------------------

    def _header(self):
        aset = self.m.root.find("analysis_set")
        files = aset.find("file") if aset is not None else None
        def fname(tag: str) -> str:
            return _child_text(files, tag, "ex4_e")
        self.lines += [
            "SDAT",
            "STREAM  ",
            "        2023           0           0    UTF-8",
            "           3",
            "! STpre  Version.2023.2  1623.20302.20231027",
            "POST",
            self.m.project_name,
            "RO",
            fname("ro"),
            "VF",
            fname("vf"),
            "OT",
            fname("ot"),
            "HPT",
            fname("hpt"),
            "/",
            _child_text(self.m.project, "comment", ""),
            "           1",
        ]
        axes = self.m.mesh_axes()
        ni = len(axes.get("x", [])) - 1
        nj = len(axes.get("y", [])) - 1
        nk = len(axes.get("z", [])) - 1
        self.lines.append(
            f"{_i(ni)}{_i(nj)}{_i(nk)}{_i(1)}{_i(1)}{_i(0)}{_i(0)}{_i(0)}")
        self.lines.append(
            f"{_i(0)}{_i(4)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}")

    def _vfex_unit(self):
        aset = self.m.root.find("analysis_set")
        rad = aset.find("radiation") if aset is not None else None
        method = _child_text(rad, "method", "1") if rad is not None else "1"
        self.lines += [
            "VFEX",
            f"{_i(int(method))}{_i(1)}",
            "UNIT",
            f"   temperature{_i(1, 15)}{_i(1)}",
            "/",
        ]

    def _heatpath(self):
        proj = self.m.project
        ambient = _child_text(proj, "ambient_temperature", "20")
        self.lines += [
            "HEATPATH",
            "atmosphere",
            _f(float(ambient), 29),
            "timing",
            f"{_i(0, 5)}:L",
            "/",
        ]

    def _equations(self):
        self.lines += ["EQUA", "11111000"]
        aset = self.m.root.find("analysis_set")
        grav_abs = float(_child_text(aset, "grav_abs", "9.8"))
        grav_vec = [float(x) for x in _child_text(aset, "grav_vec",
                                                   "0,0,-1").split(",")[:3]]
        ambient = float(_child_text(self.m.project, "ambient_temperature", "20"))
        self.lines += [
            "GRAV",
            f"{_f(grav_vec[0] * grav_abs, 29)}"
            f"{_f(grav_vec[1] * grav_abs)}{_f(grav_vec[2] * grav_abs)}"
            f"{_f(ambient)}{_i(0)}",
            "HSOL",
            f"{_i(1)}",
            f"{_i(3)}{_i(1)}{_i(1)}",
            "CYCS",
            f"{_i(1)}{_i(100, 10)}",
            "UNDR",
            f"{_i(5)}{_f(0.99)}",
            "/",
        ]

    def _property(self):
        self.lines += ["PROPERTY", f"{_i(1)}"]
        # fluid entry: viscosity / capacity / conductivity then density / expansion
        from cabxml import _first
        def prop(name: str, key: str) -> str:
            ent = self.p.find_entry(name)
            if ent is None:
                return "0"
            c = _first(ent, key)
            return c.text.strip() if c is not None and c.text else "0"
        fname = self.m.analysis_region()
        from cabxml import _first as _f1
        fluid_prop = _child_text(fname, "property", "air(incompressible/20C)")
        visc = float(prop(fluid_prop, "viscosity"))
        cap = float(prop(fluid_prop, "capacity"))
        cond = float(prop(fluid_prop, "conductivity"))
        dens = float(prop(fluid_prop, "density"))
        exp = float(prop(fluid_prop, "expansion"))
        self.lines.append(
            f"{'boussinesq':>18}{_f(visc, 37)}{_f(cap)}{_f(cond)}"
            f"   {fluid_prop} ! (1)")
        self.lines.append(f"{_f(dens, 29)}{_f(exp)}")
        # collect unique solid materials in EMT numbering order
        solid_mats = [name for name in self.materials
                      if name != fluid_prop]
        self.lines.append(f"{_i(len(solid_mats))}")
        for no, name in enumerate(solid_mats, start=2):
            d = float(prop(name, "density"))
            c = float(prop(name, "capacity"))
            k = float(prop(name, "conductivity"))
            self.lines.append(
                f"{_f(d, 29)}{_f(c)}{_f(k)}   {name} ! ({no})")

    def _cxyz(self):
        self.lines.append("CXYZ")
        axes = self.m.mesh_axes()
        for axis in ("x", "y", "z"):
            vals = [v / 1000.0 for v in axes.get(axis, [])]
            self.lines.append("   0")
            for i in range(0, len(vals), 5):
                row = vals[i:i + 5]
                self.lines.append(
                    " " * 8 + "     ".join(f"{v:21.14e}" for v in row))

    def _parts(self):
        self.lines.append("PARTS")
        for idx, p in enumerate(self.parts):
            self.lines.append(
                f"{_i(p['id'])}{_i(p['material'])}{p['fraction']:8.1f}"
                f"    {p['name']}")
            if idx == 0:
                continue            # fluid part: no boxes / no slash
            for box in p["boxes"]:
                self.lines.append(
                    f"{int(box[0]):14d}"
                    + "".join(f"{int(v):10d}" for v in box[1:6]))
            self.lines.append("   /")
        self.lines.append("/")

    def _regions(self):
        self.lines.append("REGION")
        for p in self.parts:
            self.lines += [
                f"   {p['name']}   ! {p['name']}",
                "   V_PRT",
                f"{_i(p['id'], 15)}",
                "   /",
            ]
        ar = self.m.analysis_region()
        from cabxml import _children, _first
        if ar is not None:
            face_index = {}
            for region in _children(ar, "region"):
                face = _first(region, "face")
                if face is None or face.text is None:
                    continue
                idx = face.text.split(",")[-1].strip()
                try:
                    face_index[_child_text(region, "name")] = int(idx)
                except ValueError:
                    continue
            elem = self.m.elements()
            face_lists: dict[int, list[int]] = {}
            if elem is not None:
                analysis = _first(elem, "analysis")
                if analysis is not None:
                    for f in _children(analysis, "face"):
                        lst = _first(f, "list")
                        if lst is None or not lst.text:
                            continue
                        try:
                            no = int(f.attrib.get("no", "0"))
                            face_lists[no] = [int(x) for x in lst.text.split(",")]
                        except ValueError:
                            continue
            for region in _children(ar, "region"):
                name = _child_text(region, "name")
                no = face_index.get(name)
                box = face_lists.get(no or 0)
                if box is None:
                    continue
                v = box[0]
                code = - (1 if v > 0 else -1) * ((abs(v) + 1) // 2)
                self.lines += [
                    f"   {name}   ! {name}",
                    "   A_MDR",
                    f"{code:11d}"
                    + "".join(f"{int(x):10d}" for x in box[1:7]),
                    "   /",
                ]
        self.lines.append("/")

    def _init_region(self):
        self.lines += ["INIT_REGION", "TEMP"]
        init_temp = "20"
        for c in self.m.conditions():
            has_analysis = any(ch.tag == "analysis" for ch in c)
            if not has_analysis:
                continue
            from cabxml import _first
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None:
                continue
            vtype = val.attrib.get("type", "")
            if vtype == "initial":
                param = _first(val, "param")
                init_temp = param.text.strip() if param is not None else "20"
                break
        self.lines.append(_f(float(init_temp), 29))
        ar = self.m.analysis_region()
        self.lines.append("   " + _child_text(ar, "name", "Domain"))
        self.lines.append("   /")
        solid_temp = _child_text(self.m.project, "solid_init_temperature", "20")
        self.lines.append("TEMP")
        self.lines.append(_f(float(solid_temp), 29))
        for p in self.parts[1:]:
            self.lines.append("      " + p["name"])
        self.lines += ["   /", "/"]

    def _flux_region(self):
        self.lines.append("FLUX_REGION")
        kinds = {"total_pres": "total-pres", "out": "natural-out"}
        for name, val, region in sorted(self._bound_values("flux"),
                                        key=lambda x: _name_key(x[0])):
            kind = kinds.get(_child_text(val, "kind"), "total-pres")
            prefix = {"total-pres": "total-pres    0",
                      "natural-out": "natural-out    0"}.get(kind,
                                                             "total-pres    0")
            self.lines.append(f"{prefix}   ! {name}")
            if kind == "total-pres":
                pres = float(_child_text(val, "pressure", "0"))
                temp = float(_child_text(val, "temperature", "20"))
                self.lines.append(f"{_f(pres, 29)}{_f(temp)}")
            self.lines.append("      0  0  0  0")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _amom_region(self):
        self.lines.append("AMOM_REGION")
        kinds = {"free_slip": "freeslip", "no_slip": "noslip"}
        groups: dict[str, tuple[str, list[str]]] = {}
        for name, val, region in sorted(self._bound_values("wall"),
                                        key=lambda x: _name_key(x[0])):
            kind = kinds.get(_child_text(val, "kind"), "noslip")
            if kind not in groups:
                groups[kind] = (name, [])
            groups[kind][1].append(region)
        for kind, (first_name, regions) in groups.items():
            prefix = {"freeslip": "freeslip  static    0",
                      "noslip": "noslip  static    0"}.get(
                          kind, "noslip  static    0")
            self.lines.append(f"{prefix}   ! {first_name}")
            for r in regions:
                self.lines.append("   " + r)
            self.lines.append("   /")
        # undefined-faces wall condition
        undef_name = self._undefined_value("wall")
        if undef_name:
            undef = self.m.find_value(undef_name)
            kind = kinds.get(_child_text(undef, "kind"), "noslip") \
                if undef is not None else "noslip"
            prefix = {"freeslip": "freeslip  static    0",
                      "noslip": "noslip  static    0"}.get(
                          kind, "noslip  static    0")
            self.lines.append(f"{prefix}   ! "
                              f"{undef_name}")
            self.lines.append("   @UNDEFINEDMOM")
            self.lines.append("   /")
        self.lines.append("/")

    def _aent_region(self):
        self.lines.append("AENT_REGION")
        # sample-driven default conduction block (mapping TBD, P5)
        self.lines += [
            "conduction    0",
            _f(0.0, 29),
            "   @UNDEFINEDENTX",
            "   /",
        ]
        # undefined heat conditions (value-only, bound implicitly)
        markers = {
            "domain_boundary": "@UNDEFINEDENTB",
            "between_fluids_solids": "@UNDEFINEDENTF",
            "nbetween_solids": "@UNDEFINEDENTS",
        }
        for undef, vname in self._undefined_conditions():
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != "heat_transfer":
                continue
            key = next((m for k, m in markers.items() if k in vname),
                       "@UNDEFINEDENTS")
            kind = _child_text(val, "kind", "adiabatic")
            kw = "adiabatic" if kind == "adiabatic" else "conduction"
            prefix = {"adiabatic": "adiabatic    0",
                      "conduction": "conduction    0"}.get(
                          kw, "conduction    0")
            self.lines.append(f"{prefix}   ! {vname}")
            if kw == "conduction":
                temp = float(_child_text(val, "temperature", "0"))
                self.lines.append(_f(temp, 29))
            self.lines.append("   " + key)
            self.lines.append("   /")
        for name, val, region in sorted(self._bound_values("heat_transfer"),
                                        key=lambda x: _name_key(x[0])):
            kind = _child_text(val, "kind", "adiabatic")
            kw = "adiabatic" if kind == "adiabatic" else "conduction"
            prefix = {"adiabatic": "adiabatic    0",
                      "conduction": "conduction    0"}.get(
                          kw, "conduction    0")
            self.lines.append(f"{prefix}   ! {name}")
            if kw == "conduction":
                temp = float(_child_text(val, "temperature", "0"))
                self.lines.append(_f(temp, 29))
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _vent_region(self):
        self.lines.append("VENT_REGION")
        entries = list(self._bound_parts_values("heat_source"))
        entries += list(self._bound_analysis_values("heat_source"))
        for name, val, region in sorted(
                entries, key=lambda x: _name_key(x[0])):
            src = float(_child_text(val, "source", "0"))
            self.lines.append(f"source    0   ! {name}")
            self.lines.append(f"{_f(src, 29)}   2")
            self.lines.append("   " + region)
            self.lines.append("   /")
        self.lines.append("/")

    def _vfwl_region(self):
        self.lines.append("VFWL_REGION")
        rad = self.m.find_value("_rad_condition(undefined_faces)")
        if rad is not None:
            temp = float(_child_text(rad, "temperature", "20"))
            factor = float(_child_text(rad, "factor", "0.9"))
            self.lines += [
                "detailFAC    0   1   0   ! _rad_condition(undefined_faces)",
                _f(temp, 29),
                "              6           0   1.00    0.00",
                f"{_f(factor)}{_f(1.0 - factor)}{_f(0.0)}",
                "   @UNDEFINEDVFWL",
                "   /",
            ]
        for p in self.parts[1:]:
            self.lines += [
                f"detailBDY   0   1   0   ! {p['name']}",
                "         0   0    1.00    0.00",
                f"{_f(0.9)}{_f(0.1)}{_f(0.0)}{_f(0.0)}",
                f"   {p['name']}",
                "   /",
            ]
        self.lines.append("/")

    def _vfem_vfde(self):
        self.lines += [
            "VFEM",
            f"{_i(1, 15)}{_f(-1.0, 26)}",
            "/",
            "VFDE",
        ]
        aset = self.m.root.find("analysis_set")
        rad = aset.find("radiation") if aset is not None else None
        self.lines.append(f"   MPCL{_i(int(_child_text(rad, 'max_particle', '20000')), 12)}")
        self.lines.append(f"   LEAP{_i(1, 9)}")
        self.lines.append(f"   IXYZ{_i(int(_child_text(rad, 'space_cycle', '0')), 9)}")
        self.lines.append(f"   MREF{_i(100, 9)}")
        self.lines.append(f"   EM1{0.99:>9}")
        self.lines.append(f"   MAXM{_i(int(_child_text(rad, 'max_group_num', '4000')), 9)}")
        pgn = _child_text(rad, "parts_group_num", "6,-1").split(",")[0]
        self.lines.append(f"   MGMI{_i(int(pgn), 9)}")
        self.lines.append("/")

    def _autofixp(self):
        aset = self.m.root.find("analysis_set")
        vals = [int(x) for x in
                _child_text(aset, "auto_fixp", "1,1").split(",")[:2]]
        self.lines += ["AUTOFIXP", f"{_i(vals[0])}{_i(vals[1])}"]

    def _fout(self):
        out = self.m.root.find("output")
        from cabxml import _children
        self.lines.append("FOUT")
        if out is not None:
            for f in _children(out, "fout"):
                self.lines.append(f"    {f.attrib.get('type', '')}")
        self.lines.append("/")

    def _meix_var(self):
        out = self.m.root.find("output")
        cycle = _child_text(out, "minmax_cycle", "1")
        kind = _child_text(out, "minmax_kind", "1,1,2").split(",")
        kind += ["0"] * (3 - len(kind))
        self.lines.append("MEIX_VAR")
        self.lines.append(f"{_i(int(cycle))}{_i(int(kind[0]))}"
                          f"{_i(int(kind[1]))}{_i(int(kind[2]))}")
        from cabxml import _children
        if out is not None:
            for v in _children(out, "minmax_var"):
                if (v.text or "").strip() == "T":
                    vtype = v.attrib.get("type", "")
                    aset = self.m.root.find("analysis_set")
                    turb = _child_text(aset, "turbulence", "0")
                    if vtype in ("TURK", "TEPS") and turb == "0":
                        continue
                    self.lines.append(f"    {vtype}")
        self.lines.append("/")

    def _balances(self):
        out = self.m.root.find("output")
        c1 = _child_text(out, "hbal_output_cycle1", "0").split(":")[0]
        c2 = _child_text(out, "hbal_output_cycle2", "0").split(":")[0]
        self.lines += [
            "HBAL_PARTS",
            f"{_i(int(c1), 5)}:L{_i(0, 12)}",
            "HBAL_BTW_PARTS",
            f"{_i(int(c2), 5)}:L{_i(0, 12)}",
            "FBAL",
            f"{_i(1, 5)}:L",
        ]

    def _tprt(self):
        self.lines += ["TPRT_OUTPUT", f"{_i(len(self.parts), 15)}"]
        ids = [p["id"] for p in self.parts]
        for i in range(0, len(ids), 5):
            row = ids[i:i + 5]
            self.lines.append(f"{row[0]:15d}"
                              + "".join(f"{x:11d}" for x in row[1:]))

    # -- helpers ----------------------------------------------------------

    def _bound_values(self, vtype: str):
        """Yield (value_name, value_elem, region_or_parts_target) for
        conditions whose value element has the requested type."""
        from cabxml import _first
        for c in self.m.conditions():
            target = None
            for child in c:
                if child.tag in ("region", "parts"):
                    target = (child.tag, child.text.strip() if child.text else "")
            if target is None:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            region = target[1]
            if target[0] == "parts":
                continue
            if re.fullmatch(r"undefine\d+", region):
                continue
            yield vname, val, region

    def _bound_parts_values(self, vtype: str):
        """Conditions bound to parts (used by VENT_REGION)."""
        from cabxml import _first
        for c in self.m.conditions():
            parts_name = None
            for child in c:
                if child.tag == "parts":
                    parts_name = child.text.strip() if child.text else ""
            if parts_name is None:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            yield vname, val, parts_name

    def _bound_analysis_values(self, vtype: str):
        """Conditions bound to the analysis/domain region (volumetric
        sources etc.)."""
        dom = self.m.domain_name() or "Domain(cuboid)"
        for c in self.m.conditions():
            region = None
            for child in c:
                if child.tag in ("analysis", "region"):
                    region = child.text.strip() if child.text else ""
            if region is None or region != dom:
                continue
            vname = _child_text(c, "value")
            val = self.m.find_value(vname)
            if val is None or val.attrib.get("type", "") != vtype:
                continue
            yield vname, val, region

    def _undefined_conditions(self):
        """(undefine_region_name, value_name) for `undefineN` bindings."""
        for c in self.m.conditions():
            region = None
            vname = None
            for child in c:
                if child.tag == "region":
                    region = child.text.strip() if child.text else ""
                if child.tag == "value":
                    vname = child.text.strip() if child.text else ""
            if region and vname and re.fullmatch(r"undefine\d+", region):
                yield region, vname

    def _undefined_value(self, vtype: str) -> str:
        """Value name of the undefined condition with the given type."""
        for _, vname in self._undefined_conditions():
            val = self.m.find_value(vname)
            if val is not None and val.attrib.get("type", "") == vtype:
                return vname
        return ""


def build_sdat(model: StpreModel, props: PropertyModel) -> str:
    return SExport(model, props).render()


def parse_s_parts(text: str) -> list[str]:
    """Names of the part/region entries in the PARTS section of an S file.

    PARTS header lines look like ``<id><material><fraction>    <name>``
    (the fluid part first, then one entry per part).  Numeric box-list
    lines are skipped.  Used by [Mesh] - [Checking S-File].
    """
    names: list[str] = []
    in_parts = False
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s == "PARTS":
            in_parts = True
            continue
        if not in_parts:
            continue
        if s in ("/", "   /"):
            break
        parts = s.split()
        if len(parts) >= 4:
            try:
                int(parts[0])
                int(parts[1])
                float(parts[2])
            except ValueError:
                continue
            names.append(" ".join(parts[3:]).strip())
    return names
