"""P1: byte-stable XML models for scSTREAM cab text members.

Two plaintext members carry the editable project metadata:

- ``ex4_e.xml``               -> :class:`StpreDoc` / :class:`StpreModel`
- ``_ex4_e_property.xml``     -> :class:`PropertyDoc` / :class:`PropertyModel`

The serializer is a hand-rolled ElementTree walk that re-emits the exact
text/tail whitespace captured by the parser, so unedited documents round-trip
byte-for-byte (UTF-8 BOM, XML declaration, leading comments and trailing
newline are preserved). Editing mutates element text/attributes in place.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

# STpre Layout of Parts / Conditions: DomainBoundary face order
DOMAIN_FACE_NAMES: tuple[str, ...] = (
    "Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax",
)


def _escape_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(s: str) -> str:
    return (_escape_text(s)
            .replace('"', "&quot;")
            .replace("\n", "&#10;")
            .replace("\t", "&#9;"))


def _serialize_element(el: ET.Element) -> str:
    """Reproduce an element subtree with original text/tail whitespace."""
    attrs = "".join(f' {k}="{_escape_attr(v)}"' for k, v in el.attrib.items())
    out = f"<{el.tag}{attrs}>"
    if el.text:
        out += _escape_text(el.text)
    for child in el:
        out += _serialize_element(child)
        if child.tail:
            out += _escape_text(child.tail)
    out += f"</{el.tag}>"
    return out


class _XmlDoc:
    """Shared parse/serialize plumbing for both cab XML members."""

    def __init__(self, raw: bytes):
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        body = raw[3:] if self.bom else raw
        # XML parsers normalise CRLF -> LF; remember to restore it on output.
        self.crlf = b"\r\n" in body
        # skip XML declaration / comments, then find the root element
        pos = 0
        while True:
            lt = body.find(b"<", pos)
            if lt < 0:
                raise ValueError("no root element found")
            if body[lt + 1:lt + 2] in (b"?", b"!"):
                pos = lt + 1
                continue
            break
        tag_end = body.find(b">", lt)
        self.root_tag = body[lt + 1:tag_end].split()[0].decode()
        start = body.find(f"<{self.root_tag}".encode())
        if start < 0:
            raise ValueError(f"<{self.root_tag}> not found")
        self.head = body[:start]                 # declaration + comments
        end = body.rfind(f"</{self.root_tag}>".encode())
        self.trailing = body[end + len(self.root_tag) + 3:]
        self.root = ET.fromstring(body[start:end + len(self.root_tag) + 3])

    def serialize(self) -> bytes:
        out = (b"\xef\xbb\xbf" if self.bom else b"") + self.head
        root_bytes = _serialize_element(self.root).encode("utf-8")
        if self.crlf:
            root_bytes = root_bytes.replace(b"\n", b"\r\n")
        out += root_bytes
        out += self.trailing
        return out


class StpreDoc(_XmlDoc):
    """``<stpre>`` project definition (ex4_e.xml)."""

    def __init__(self, raw: bytes):
        super().__init__(raw)


class PropertyDoc(_XmlDoc):
    """``<property>`` material database (_ex4_e_property.xml)."""

    def __init__(self, raw: bytes):
        super().__init__(raw)


def parse_stpre(data: bytes) -> StpreDoc:
    return StpreDoc(data)


def parse_property(data: bytes) -> PropertyDoc:
    return PropertyDoc(data)


def new_stpre_bytes(name: str = "Untitled") -> bytes:
    """Minimal but complete-enough empty project XML (UTF-8 BOM, CRLF)."""
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<!-- scSTREAM V2025.2 -->\r\n'
        '<!-- created by cabdecoding (new project) -->\r\n'
        '<stpre>\r\n'
        '   <version no="2025.2" />\r\n'
        '   <property_db>\r\n'
        '      <file> _new_property.xml </file>\r\n'
        '   </property_db>\r\n'
        '   <unit>\r\n'
        '      <temperature> C </temperature>\r\n'
        '   </unit>\r\n'
        '   <project>\r\n'
        f'      <project> {name} </project>\r\n'
        '      <comment> created by cabdecoding </comment>\r\n'
        '      <ambient_temperature> 20 </ambient_temperature>\r\n'
        '      <cxyz_scale> 1 </cxyz_scale>\r\n'
        '   </project>\r\n'
        '   <body_files unit="m">\r\n'
        '   </body_files>\r\n'
        '   <analysis_set>\r\n'
        '   </analysis_set>\r\n'
        '   <output>\r\n'
        '   </output>\r\n'
        '   <steady_param>\r\n'
        '   </steady_param>\r\n'
        '</stpre>\r\n'
    )
    return b"\xef\xbb\xbf" + text.encode("utf-8")


def new_property_bytes() -> bytes:
    """Full STpre standard material library (``standard_property_ENG.xml``).

    Loaded from Cradle ``Programs_x64`` or the vendored ``data/`` copy via
    :mod:`cab_materials`. Falls back to a single air entry if unavailable.
    """
    try:
        from cab_materials import load_standard_property_bytes
        return load_standard_property_bytes()
    except Exception:
        pass
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<!-- property table -->\r\n'
        '<property>\r\n'
        '   <group>\r\n'
        '      <type> fluid </type>\r\n'
        '      <name> gas(incompressible) </name>\r\n'
        '      <entry>\r\n'
        '         <name> air(incompressible/20C) </name>\r\n'
        '         <density> 1.206 </density>\r\n'
        '         <ref_density> 1.206 </ref_density>\r\n'
        '         <ref_temperature unit="C"> 20 </ref_temperature>\r\n'
        '         <viscosity> 1.83e-05 </viscosity>\r\n'
        '         <capacity> 1007 </capacity>\r\n'
        '         <conductivity> 0.0256 </conductivity>\r\n'
        '         <expansion> 0.003495 </expansion>\r\n'
        '         <radiation field="T">\r\n'
        '            <absorption> 0 </absorption>\r\n'
        '            <scattering> 0 </scattering>\r\n'
        '         </radiation>\r\n'
        '         <surf_tension> 0 </surf_tension>\r\n'
        '      </entry>\r\n'
        '   </group>\r\n'
        '</property>\r\n'
    )
    return b"\xef\xbb\xbf" + text.encode("utf-8")


# --------------------------------------------------------------------------
# Model layer (convenience accessors + edit helpers)
# --------------------------------------------------------------------------

def _children(el: ET.Element, tag: str) -> list[ET.Element]:
    return [c for c in el if c.tag == tag]


def _first(el: ET.Element, tag: str) -> Optional[ET.Element]:
    for c in el:
        if c.tag == tag:
            return c
    return None


def set_text(el: ET.Element, value: str) -> None:
    """Replace an element's text node, keeping surrounding whitespace."""
    if el.text and el.text.strip():
        pad = el.text[:len(el.text) - len(el.text.lstrip())]
        pad_end = el.text[len(el.text.rstrip()):]
        el.text = f"{pad}{value}{pad_end}"
    else:
        el.text = value


@dataclass
class PartInfo:
    """A ``<parts>`` entry with the metadata the GUI edits."""

    elem: ET.Element
    name: str
    name2: str = ""
    kind: str = "body"            # body | cube | ...
    property: str = ""
    attribute: str = ""
    color: str = ""
    volume: str = ""
    transform: str = ""
    base: str = ""
    size: str = ""
    group: str = ""


class StpreModel:
    """Typed view over :class:`StpreDoc` used by GUI / exporters."""

    def __init__(self, doc: StpreDoc):
        self.doc = doc
        self.root = doc.root

    # -- project -----------------------------------------------------------

    @property
    def project(self) -> Optional[ET.Element]:
        return _first(self.root, "project")

    @property
    def project_name(self) -> str:
        p = _first(self.project, "project") if self.project is not None else None
        return p.text.strip() if p is not None and p.text else ""

    @property
    def units(self) -> dict[str, str]:
        u = _first(self.root, "unit")
        if u is None:
            return {}
        return {c.tag: (c.text or "").strip() for c in u}

    # -- parts -------------------------------------------------------------

    def groups(self) -> list[ET.Element]:
        """All ``<group>`` elements in document order, including nested ones."""
        out: list[ET.Element] = []

        def walk(parent: ET.Element) -> None:
            for grp in _children(parent, "group"):
                out.append(grp)
                walk(grp)

        walk(self.root)
        return out

    def parts(self) -> list[PartInfo]:
        out: list[PartInfo] = []

        def collect(parent: ET.Element, gname: str) -> None:
            for el in _children(parent, "parts"):
                def t(tag: str) -> str:
                    c = _first(el, tag)
                    return c.text.strip() if c is not None and c.text else ""

                out.append(PartInfo(
                    elem=el,
                    name=t("name"),
                    name2=t("name2"),
                    kind=el.attrib.get("type", "body"),
                    property=t("property"),
                    attribute=t("attribute"),
                    color=t("color"),
                    volume=t("volume"),
                    transform=t("transform"),
                    base=t("base"),
                    size=t("size"),
                    group=gname,
                ))

        # box.cab stores <parts> directly under <stpre> with no <group>.
        collect(self.root, "")
        for grp in self.groups():
            gname = (_first(grp, "name").text or "").strip() \
                if _first(grp, "name") is not None else ""
            collect(grp, gname)
        return out

    def find_part(self, name: str) -> Optional[ET.Element]:
        for p in self.parts():
            if p.name == name:
                return p.elem
        return None

    def rename_part(self, old: str, new: str) -> bool:
        el = self.find_part(old)
        if el is None:
            return False
        for tag in ("name", "name2"):
            c = _first(el, tag)
            if c is not None:
                set_text(c, new)
        return True

    def set_part_property(self, name: str, material: str) -> bool:
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "property")
        if c is None:
            c = ET.SubElement(el, "property")
            c.tail = "\n      "
        set_text(c, material)
        return True

    def set_part_monitor(self, name: str, on: bool) -> bool:
        """Create/update ``<parts>/<monitor>`` (T/F)."""
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "monitor")
        if c is None:
            c = ET.SubElement(el, "monitor")
            c.tail = "\n      "
        set_text(c, "T" if on else "F")
        return True

    def set_part_color(self, name: str, rgba: tuple[int, int, int, int]) -> bool:
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "color")
        if c is not None:
            set_text(c, ",".join(str(v) for v in rgba))
        return True

    def set_part_transform(self, name: str, matrix16: str) -> bool:
        """Update ``<parts>/<transform>`` (16 values, column-major)."""
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "transform")
        if c is None:
            c = ET.SubElement(el, "transform")
            c.tail = "\n         "
        set_text(c, matrix16)
        return True

    # -- regions / values / conditions ------------------------------------

    def regions(self) -> list[ET.Element]:
        return _children(self.root, "region")

    def analysis_region(self) -> Optional[ET.Element]:
        return _first(self.root, "analysis_region")

    def domain_faces(self) -> list[tuple[str, Optional[ET.Element]]]:
        """DomainBoundary face_list regions in STpre order (Xmin…Zmax).

        Always returns the six canonical names. The element is ``None`` when
        that face is missing from ``analysis_region``.
        """
        by_name: dict[str, ET.Element] = {}
        ar = self.analysis_region()
        if ar is not None:
            for reg in _children(ar, "region"):
                if reg.attrib.get("type") != "face_list":
                    continue
                n = _first(reg, "name")
                if n is None or not n.text:
                    continue
                by_name[n.text.strip()] = reg
        return [(name, by_name.get(name)) for name in DOMAIN_FACE_NAMES]

    def ensure_domain_faces(self) -> list[str]:
        """Ensure the six DomainBoundary faces exist under ``analysis_region``.

        Creates a default cube domain when none is present. Returns face names
        in STpre display order.
        """
        ar = self.analysis_region()
        if ar is None:
            self.ensure_domain()
            return list(DOMAIN_FACE_NAMES)
        dname = self.domain_name() or "Domain(cuboid)"
        # face numbers match ensure_domain / ex4_e conventions
        face_no = {
            "Ymin": "1", "Xmax": "2", "Ymax": "3",
            "Xmin": "4", "Zmin": "5", "Zmax": "6",
        }
        existing = {n for n, el in self.domain_faces() if el is not None}
        for fname in DOMAIN_FACE_NAMES:
            if fname in existing:
                continue
            r = ET.SubElement(ar, "region")
            r.attrib["type"] = "face_list"
            r.tail = "\n   "
            for tag, text in (
                ("name", fname),
                ("kind", "aset"),
                ("base", dname),
                ("face", f"{dname},{face_no[fname]}"),
                ("rad_group_num", "0"),
            ):
                e = ET.SubElement(r, tag)
                e.text = f" {text} "
                e.tail = "\n      "
        return list(DOMAIN_FACE_NAMES)

    # -- computational domain (M2) ----------------------------------------

    def domain_base(self) -> Optional[tuple[float, float, float]]:
        ar = self.analysis_region()
        el = _first(ar, "base") if ar is not None else None
        if el is None or not el.text:
            return None
        try:
            vals = [float(x.strip()) for x in el.text.split(",")[:3]]
        except ValueError:
            return None
        return (vals[0], vals[1], vals[2]) if len(vals) == 3 else None

    def domain_size(self) -> Optional[tuple[float, float, float]]:
        ar = self.analysis_region()
        el = _first(ar, "size") if ar is not None else None
        if el is None or not el.text:
            return None
        try:
            vals = [float(x.strip()) for x in el.text.split(",")[:3]]
        except ValueError:
            return None
        return (vals[0], vals[1], vals[2]) if len(vals) == 3 else None

    def domain_unit(self) -> str:
        ar = self.analysis_region()
        el = _first(ar, "base") if ar is not None else None
        return (el.attrib.get("unit", "mm") if el is not None else "mm")

    def domain_material(self) -> str:
        ar = self.analysis_region()
        el = _first(ar, "property") if ar is not None else None
        return (el.text or "").strip() if el is not None and el.text else ""

    def domain_name(self) -> str:
        ar = self.analysis_region()
        el = _first(ar, "name") if ar is not None else None
        return (el.text or "").strip() if el is not None and el.text else ""

    def set_domain_name(self, name: str) -> bool:
        """Rename the domain and fix the six face_list region refs."""
        ar = self.analysis_region()
        if ar is None or not name:
            return False
        old = self.domain_name()
        el = _first(ar, "name")
        if el is None:
            el = ET.SubElement(ar, "name")
        set_text(el, name)
        for reg in _children(ar, "region"):
            b = _first(reg, "base")
            if b is not None and (b.text or "").strip() == old:
                set_text(b, name)
            f = _first(reg, "face")
            if f is not None and f.text:
                parts = f.text.strip().split(",")
                if parts and parts[0].strip() == old:
                    rest = [p.strip() for p in parts[1:]]
                    set_text(f, ",".join([name] + rest))
        return True

    def domain_color(self) -> Optional[tuple[int, int, int, int]]:
        ar = self.analysis_region()
        el = _first(ar, "color") if ar is not None else None
        if el is None or not el.text:
            return None
        try:
            vals = [int(float(x.strip())) for x in el.text.split(",")[:4]]
        except ValueError:
            return None
        return tuple(vals) if len(vals) == 4 else None  # type: ignore

    def set_domain_color(self, rgba: tuple[int, int, int, int]) -> bool:
        ar = self.analysis_region()
        if ar is None:
            return False
        el = _first(ar, "color")
        if el is None:
            el = ET.SubElement(ar, "color")
            el.tail = "\n   "
        set_text(el, ",".join(str(int(v)) for v in rgba))
        return True

    def domain_monitor(self) -> bool:
        """``<monitor> T/F </monitor>`` — Output temperature to Monitor."""
        ar = self.analysis_region()
        el = _first(ar, "monitor") if ar is not None else None
        if el is None or not el.text:
            return True
        return el.text.strip().upper() != "F"

    def set_domain_monitor(self, on: bool) -> bool:
        ar = self.analysis_region()
        if ar is None:
            return False
        el = _first(ar, "monitor")
        if el is None:
            el = ET.SubElement(ar, "monitor")
            el.tail = "\n   "
        set_text(el, "T" if on else "F")
        return True

    def ambient_temperature(self) -> Optional[float]:
        """Project-level fluid initial temperature (degC)."""
        p = self.project
        el = _first(p, "ambient_temperature") if p is not None else None
        if el is None or not el.text:
            return None
        try:
            return float(el.text.strip())
        except ValueError:
            return None

    def set_ambient_temperature(self, value: float) -> bool:
        p = self.project
        if p is None:
            return False
        el = _first(p, "ambient_temperature")
        if el is None:
            el = ET.SubElement(p, "ambient_temperature")
            el.tail = "\n      "
        set_text(el, f"{value:.17g}")
        return True


    def set_domain_geometry(self, base: tuple[float, float, float],
                            size: tuple[float, float, float],
                            unit: str = "mm") -> bool:
        """Update ``<analysis_region><base>/<size>`` (values in ``unit``)."""
        ar = self.analysis_region()
        if ar is None:
            return False
        for tag, vals in (("base", base), ("size", size)):
            el = _first(ar, tag)
            if el is None:
                el = ET.SubElement(ar, tag)
                el.tail = "\n   "
            set_text(el, ",".join(f"{v:.17g}" for v in vals))
            el.attrib["unit"] = unit
        return True

    def set_domain_material(self, name: str) -> bool:
        ar = self.analysis_region()
        if ar is None:
            return False
        el = _first(ar, "property")
        if el is None:
            el = ET.SubElement(ar, "property")
            el.tail = "\n   "
        set_text(el, name)
        return True

    # -- wizard data (M6: Initial Wizard / Condition Wizard) ---------------

    def set_project_value(self, tag: str, text: str) -> bool:
        """Set ``<project>/<tag>`` (comment / ambient_temperature / ...)."""
        p = self.project
        if p is None:
            return False
        el = _first(p, tag)
        if el is None:
            el = ET.SubElement(p, tag)
            el.tail = "\n      "
        set_text(el, text)
        return True

    def project_value(self, tag: str, default: str = "") -> str:
        p = self.project
        el = _first(p, tag) if p is not None else None
        return (el.text or "").strip() if el is not None and el.text \
            else default

    def set_project_name(self, name: str) -> bool:
        return self.set_project_value("project", name)

    def ensure_analysis_set(self) -> ET.Element:
        """Create ``<analysis_set>`` with STpre defaults when missing."""
        aset = _first(self.root, "analysis_set")
        if aset is not None:
            return aset
        aset = ET.Element("analysis_set")
        aset.tail = "\n"
        defaults = (
            ("type", "incompressive"), ("fluid", "1"), ("heat", "0"),
            ("turbulence", "0"), ("turbulence_model", "0"),
            ("grav_abs", "9.8", {"unit": "m/s2"}),
            ("grav_vec", "0,0,-1"),
            ("cycle", "1,100", {"type": "incompressive"}),
            ("calculation", "steady"), ("steady_check_cycle", "50"),
            ("steady_hbal_cycle", "0"), ("steady_hbal_eps", "0"),
            ("init_time_step", "0.01"), ("courant", "0.9"),
        )
        for item in defaults:
            tag = item[0]
            text = item[1]
            attrs = item[2] if len(item) > 2 else {}
            e = ET.SubElement(aset, tag)
            e.text = f" {text} "
            e.tail = "\n   "
            for k, v in attrs.items():
                e.attrib[k] = v
        self.root.append(aset)
        return aset

    def analysis_set_value(self, tag: str, default: str = "") -> str:
        aset = _first(self.root, "analysis_set")
        el = _first(aset, tag) if aset is not None else None
        return (el.text or "").strip() if el is not None and el.text \
            else default

    def set_analysis_set_value(self, tag: str, text: str,
                               unit: Optional[str] = None) -> bool:
        aset = self.ensure_analysis_set()
        el = _first(aset, tag)
        if el is None:
            el = ET.SubElement(aset, tag)
            el.tail = "\n   "
        set_text(el, text)
        if unit is not None:
            el.attrib["unit"] = unit
        return True

    def set_gravity(self, acceleration: float, vec: tuple[float, float, float]
                    ) -> bool:
        self.set_analysis_set_value("grav_abs", f"{acceleration:.17g}",
                                    unit="m/s2")
        return self.set_analysis_set_value(
            "grav_vec", ",".join(f"{v:.17g}" for v in vec))

    def set_cycles(self, start: int, end: int, *,
                   transient: bool) -> bool:
        self.set_analysis_set_value(
            "cycle", f"{start},{end}", unit="incompressive")
        return self.set_analysis_set_value(
            "calculation", "transient" if transient else "steady")

    def upsert_value(self, value_type: str, name: str,
                     children: list[tuple[str, str, Optional[str]]],
                     ) -> bool:
        """Create or update a ``<value type=...>`` definition.

        ``children`` = list of ``(tag, text, unit_or_None)``; ``unit=None``
        leaves the existing ``unit`` attribute untouched (or absent).
        """
        if not name:
            return False
        val = self.find_value(name)
        if val is None:
            val = ET.Element("value")
            val.attrib["type"] = value_type
            val.tail = "\n   "
            self.root.append(val)
        else:
            val.attrib["type"] = value_type
        fields = list(children)
        if not any(t == "name" for t, _t, _u in fields):
            fields.insert(0, ("name", name, None))
        for tag, text, unit in fields:
            c = _first(val, tag)
            if c is None:
                c = ET.SubElement(val, tag)
                c.tail = "\n      "
            set_text(c, text)
            if unit is not None:
                c.attrib["unit"] = unit
        return True

    def bind_condition(self, target_kind: str, target: str,
                       value_name: str) -> bool:
        """Append a ``<condition>`` binding a value to a region/parts/analysis.

        A target may carry several conditions (e.g. a face_list region with
        both a wall and a heat_transfer value), so only a duplicate binding
        of the *same* value to the *same* target is replaced — re-running a
        wizard stays idempotent without dropping sibling conditions.
        """
        if not target or not value_name:
            return False
        for c in list(self.conditions()):
            t = _first(c, target_kind)
            v = _first(c, "value")
            if t is not None and (t.text or "").strip() == target \
                    and v is not None and (v.text or "").strip() == value_name:
                self.root.remove(c)
        c = ET.Element("condition")
        c.tail = "\n   "
        t = ET.SubElement(c, target_kind)
        t.text = f" {target} "
        t.tail = "\n      "
        v = ET.SubElement(c, "value")
        v.text = f" {value_name} "
        v.tail = "\n      "
        self.root.append(c)
        return True

    def condition_value(self, target_kind: str, target: str
                        ) -> Optional[str]:
        """Name of the first value bound to a target (or None)."""
        for c in self.conditions():
            t = _first(c, target_kind)
            if t is not None and (t.text or "").strip() == target:
                v = _first(c, "value")
                if v is not None and v.text:
                    return v.text.strip()
        return None

    def remove_condition(self, target_kind: str, target: str) -> bool:
        changed = False
        for c in list(self.conditions()):
            t = _first(c, target_kind)
            if t is not None and (t.text or "").strip() == target:
                self.root.remove(c)
                changed = True
        return changed

    def ensure_domain(self, *, name: str = "Domain(cuboid)",
                      base: tuple[float, float, float] = (0.0, 0.0, 0.0),
                      size: tuple[float, float, float] = (1.0, 1.0, 1.0),
                      unit: str = "mm",
                      material: str = "") -> ET.Element:
        """Create a cube ``<analysis_region>`` when none exists."""
        ar = self.analysis_region()
        if ar is not None:
            self.set_domain_geometry(base, size, unit)
            if material:
                self.set_domain_material(material)
            return ar
        ar = ET.Element("analysis_region")
        ar.attrib["type"] = "cube"
        ar.tail = "\n"
        fields = [
            ("name", name, {}),
            ("visible_count", "0", {}),
            ("base", ",".join(f"{v:.17g}" for v in base), {"unit": unit}),
            ("size", ",".join(f"{v:.17g}" for v in size), {"unit": unit}),
            ("color", "0,255,255,255", {}),
            ("property", material, {}),
            ("monitor", "T", {}),
            ("heat_balance", "F,F", {}),
        ]
        for tag, text, attrs in fields:
            e = ET.SubElement(ar, tag)
            e.text = f" {text} "
            e.tail = "\n   "
            for k, v in attrs.items():
                e.attrib[k] = v
        # six boundary face_list regions (face numbering matches ex4_e)
        faces = [("Ymin", "1"), ("Xmax", "2"), ("Ymax", "3"),
                 ("Xmin", "4"), ("Zmin", "5"), ("Zmax", "6")]
        for fname, fno in faces:
            r = ET.SubElement(ar, "region")
            r.attrib["type"] = "face_list"
            r.tail = "\n   "
            for tag, text in (("name", fname), ("kind", "aset"),
                              ("base", name), ("face", f"{name},{fno}"),
                              ("rad_group_num", "0")):
                e = ET.SubElement(r, tag)
                e.text = f" {text} "
                e.tail = "\n      "
        self.root.append(ar)
        return ar

    def values(self) -> list[ET.Element]:
        return _children(self.root, "value")

    def conditions(self) -> list[ET.Element]:
        return _children(self.root, "condition")

    def find_value(self, name: str) -> Optional[ET.Element]:
        for v in self.values():
            n = _first(v, "name")
            if n is not None and n.text.strip() == name:
                return v
        return None

    def set_value_param(self, value_name: str, tag: str, value: str) -> bool:
        """Update (or add) a parameter child of a named ``<value>``."""
        el = self.find_value(value_name)
        if el is None:
            return False
        c = _first(el, tag)
        if c is not None:
            set_text(c, value)
        else:
            child = ET.SubElement(el, tag)
            child.text = f" {value} "
        return True

    # -- mesh / elements ---------------------------------------------------

    def mesh_block(self) -> Optional[ET.Element]:
        return _first(self.root, "mesh_block")

    def root_block_bounds(self) -> Optional[tuple[float, float, float,
                                                    float, float, float]]:
        """RootBlock AABB in mm: ``(xmin, ymin, zmin, xmax, ymax, zmax)``.

        Prefers ``mesh_block`` ``<min>/<max>``, then axis extents, then the
        computational domain. Returns ``None`` when no geometry is known.
        """
        mb = self.mesh_block()
        if mb is not None:
            mn = _first(mb, "min")
            mx = _first(mb, "max")
            if (mn is not None and mx is not None
                    and mn.text and mx.text):
                try:
                    a = [float(x.strip()) for x in mn.text.split(",")[:3]]
                    b = [float(x.strip()) for x in mx.text.split(",")[:3]]
                    if len(a) == 3 and len(b) == 3:
                        return (a[0], a[1], a[2], b[0], b[1], b[2])
                except ValueError:
                    pass
            axes = self.mesh_axes()
            if all(len(axes.get(ax, [])) >= 2 for ax in "xyz"):
                return (axes["x"][0], axes["y"][0], axes["z"][0],
                        axes["x"][-1], axes["y"][-1], axes["z"][-1])
        # mesh_control/block min-max
        mc = _first(self.root, "mesh_control")
        block = _first(mc, "block") if mc is not None else None
        if block is not None:
            mn = _first(block, "min")
            mx = _first(block, "max")
            if (mn is not None and mx is not None
                    and mn.text and mx.text):
                try:
                    a = [float(x.strip()) for x in mn.text.split(",")[:3]]
                    b = [float(x.strip()) for x in mx.text.split(",")[:3]]
                    if len(a) == 3 and len(b) == 3:
                        return (a[0], a[1], a[2], b[0], b[1], b[2])
                except ValueError:
                    pass
        base = self.domain_base()
        size = self.domain_size()
        if base is not None and size is not None:
            return (base[0], base[1], base[2],
                    base[0] + size[0], base[1] + size[1], base[2] + size[2])
        return None

    def root_block_visible(self) -> bool:
        """``mesh_block/<visible>`` — Layout of Parts RootBlock checkbox."""
        mb = self.mesh_block()
        el = _first(mb, "visible") if mb is not None else None
        if el is None or not el.text:
            return True
        return el.text.strip().upper() != "F"

    def set_root_block_visible(self, on: bool) -> None:
        mb = self.mesh_block()
        if mb is None:
            return
        el = _first(mb, "visible")
        if el is None:
            el = ET.SubElement(mb, "visible")
            el.tail = "\n      "
        set_text(el, "T" if on else "F")

    def set_root_block_range(
            self,
            xyz_min: tuple[float, float, float],
            xyz_max: tuple[float, float, float],
            *,
            name: str = "RootBlock",
            unit: str = "mm",
            extend_min: tuple[float, float, float] = (0.0, 0.0, 0.0),
            extend_max: tuple[float, float, float] = (0.0, 0.0, 0.0),
            threshold: Optional[tuple[float, float, float]] = None,
            ratio: Optional[tuple[float, float, float]] = None,
    ) -> None:
        """Update RootBlock AABB (STpre ``Mesh:block`` dialog).

        Writes ``mesh_block`` + ``mesh_control/block`` min/max. When no axis
        table exists yet, creates a 2-point (B) axis on each side so the blue
        wireframe has geometry to display.
        """
        mn = (float(xyz_min[0]), float(xyz_min[1]), float(xyz_min[2]))
        mx = (float(xyz_max[0]), float(xyz_max[1]), float(xyz_max[2]))
        axes = self.mesh_axes()
        if not all(len(axes.get(a, [])) >= 2 for a in "xyz"):
            axes = {
                "x": [mn[0], mx[0]],
                "y": [mn[1], mx[1]],
                "z": [mn[2], mx[2]],
            }
        else:
            for i, a in enumerate("xyz"):
                vals = list(axes[a])
                mid = [v for v in vals[1:-1] if mn[i] < v < mx[i]]
                axes[a] = [mn[i]] + mid + [mx[i]]

        mc0 = _first(self.root, "mesh_control")
        blk0 = _first(mc0, "block") if mc0 is not None else None
        thr = threshold or self._parse_vec3(
            _first(blk0, "limit") if blk0 is not None else None
        ) or (0.1, 0.1, 0.1)
        rat = ratio or self._parse_vec3(
            _first(mc0, "divide_ratio2") if mc0 is not None else None
        ) or (1.0, 1.0, 1.0)

        self.set_mesh(
            axes, unit=unit, domain_min=mn, domain_max=mx,
            threshold=thr, ratio=rat)
        mb = self.mesh_block()
        if mb is not None:
            self._mesh_child(mb, "name", name)
            self._mesh_child(mb, "extend_min", self._vec_text(extend_min),
                             {"unit": unit})
            self._mesh_child(mb, "extend_max", self._vec_text(extend_max),
                             {"unit": unit})
            self._mesh_child(mb, "visible", "T")

    @staticmethod
    def _parse_vec3(el) -> Optional[tuple[float, float, float]]:
        if el is None or not getattr(el, "text", None):
            return None
        try:
            vals = [float(x.strip()) for x in el.text.split(",")[:3]]
        except ValueError:
            return None
        return (vals[0], vals[1], vals[2]) if len(vals) == 3 else None

    def mesh_axes(self) -> dict[str, list[float]]:
        """Coordinates per axis from ``mesh_block`` (unit mm as stored)."""
        mb = self.mesh_block()
        if mb is None:
            return {}
        out: dict[str, list[float]] = {}
        for axis in ("x", "y", "z"):
            el = _first(mb, axis)
            if el is None:
                continue
            vals: list[float] = []
            for g in _children(el, "g"):
                text = (g.text or "").split(",")[0].strip()
                try:
                    vals.append(float(text))
                except ValueError:
                    pass
            out[axis] = vals
        return out

    # -- mesh grid editing (M5: Mesh:Set division tabs) -------------------
    #
    # Grid-line type marks in ``<g> value,MARK </g>`` (observed in ex4_e):
    #   B = block boundary (domain/block min/max)
    #   N = general line (Normal)
    #   S = rough line through part vertices (Surface/vertex)
    #   F = fixed line (user-fixed; never re-divided)  [cab extension]

    def mesh_axis_entries(self, axis: str) -> list[tuple[float, str]]:
        """``(coordinate, mark)`` pairs of one mesh_block axis."""
        mb = self.mesh_block()
        el = _first(mb, axis) if mb is not None else None
        out: list[tuple[float, str]] = []
        if el is None:
            return out
        for g in _children(el, "g"):
            parts = (g.text or "").split(",")
            try:
                val = float(parts[0].strip())
            except (ValueError, IndexError):
                continue
            mark = parts[1].strip().upper() if len(parts) > 1 else "N"
            out.append((val, mark or "N"))
        return out

    def set_mesh_axis(self, axis: str, entries: list[tuple[float, str]],
                      unit: str = "mm") -> bool:
        """Rewrite one mesh_block axis from ``(coordinate, mark)`` pairs."""
        mb = self.mesh_block()
        if mb is None or axis not in ("x", "y", "z"):
            return False
        el = _first(mb, axis)
        if el is None:
            el = ET.SubElement(mb, axis)
            el.tail = "\n   "
        el.attrib["num"] = str(len(entries))
        el.attrib["unit"] = unit
        for child in list(el):
            el.remove(child)
        for i, (val, mark) in enumerate(entries, start=1):
            g = ET.SubElement(el, "g")
            g.attrib["no"] = str(i)
            g.text = f" {val:.17g},{mark or 'N'} "
            g.tail = "\n      "
        self.sync_mesh_grid_counts()
        return True

    def sync_mesh_grid_counts(self) -> None:
        """Sync ``mesh_control/block/grid`` with the mesh_block counts."""
        counts = [str(len(self.mesh_axis_entries(a))) for a in "xyz"]
        mc = _first(self.root, "mesh_control")
        block = _first(mc, "block") if mc is not None else None
        grid = _first(block, "grid") if block is not None else None
        if grid is not None:
            set_text(grid, ",".join(counts))

    def mesh_control_value(self, tag: str) -> Optional[str]:
        mc = _first(self.root, "mesh_control")
        el = _first(mc, tag) if mc is not None else None
        return (el.text or "").strip() if el is not None and el.text else None

    def set_mesh_control_value(self, tag: str, text: str) -> bool:
        mc = _first(self.root, "mesh_control")
        if mc is None:
            return False
        el = _first(mc, tag)
        if el is None:
            el = ET.SubElement(mc, tag)
            el.tail = "\n   "
        set_text(el, text)
        return True

    def part_mesh_option(self, name: str) -> Optional[str]:
        """Per-part vertex detection (``<parts>/<select_vertex>``)."""
        el = self.find_part(name)
        c = _first(el, "select_vertex") if el is not None else None
        return (c.text or "").strip() if c is not None and c.text else None

    def set_part_mesh_option(self, name: str, detection: str) -> bool:
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "select_vertex")
        if c is None:
            c = ET.SubElement(el, "select_vertex")
            c.tail = "\n         "
        set_text(c, detection)
        return True

    def elements(self) -> Optional[ET.Element]:
        return _first(self.root, "element")

    def part_boxes(self, part_name: str) -> list[list[int]]:
        """i/j/k index boxes of a part from the ``element`` section."""
        el = self.elements()
        if el is None:
            return []
        for parts in _children(el, "parts"):
            n = parts.attrib.get("name", "")
            if n != part_name:
                continue
            body = _first(parts, "body")
            if body is None:
                return []
            boxes: list[list[int]] = []
            for lst in _children(body, "list"):
                boxes.append([int(x) for x in lst.text.split(",")])
            return boxes
        return []

    def analysis_names(self) -> list[str]:
        """Names of ``element/analysis`` blocks (computational domains)."""
        el = self.elements()
        if el is None:
            return []
        return [a.attrib.get("name", "") for a in _children(el, "analysis")
                if a.attrib.get("name")]

    def analysis_boxes(self, name: Optional[str] = None) -> list[list[int]]:
        """Body index boxes from ``element/analysis`` (Domain occupancy).

        If ``name`` is None, return boxes for the first analysis block.
        """
        el = self.elements()
        if el is None:
            return []
        for an in _children(el, "analysis"):
            aname = an.attrib.get("name", "")
            if name is not None and aname != name:
                continue
            body = _first(an, "body")
            if body is None:
                continue
            boxes: list[list[int]] = []
            for lst in _children(body, "list"):
                if not lst.text:
                    continue
                boxes.append([int(x) for x in lst.text.split(",")])
            if boxes:
                return boxes
        return []

    # -- body files / import (M1) -----------------------------------------

    def body_files(self) -> list[str]:
        """Names of the ``<body_files><file type="xt">`` references."""
        bf = _first(self.root, "body_files")
        if bf is None:
            return []
        return [(c.text or "").strip() for c in _children(bf, "file")
                if c.attrib.get("type", "xt") == "xt" and c.text]

    def add_body_file(self, name: str, unit: str = "m") -> bool:
        """Register an additional ``.x_t`` member; no-op when already listed."""
        bf = _first(self.root, "body_files")
        if bf is None:
            bf = ET.Element("body_files")
            bf.attrib["unit"] = unit
            bf.text = "\n   "
            bf.tail = "\n"
            self.root.append(bf)
        for c in _children(bf, "file"):
            if c.attrib.get("type", "xt") == "xt" \
                    and (c.text or "").strip() == name:
                return False
        e = ET.SubElement(bf, "file")
        e.attrib["type"] = "xt"
        e.text = f" {name} "
        e.tail = "\n   "
        return True

    def add_part(self, *, name: str, name2: str = "", kind: str = "body",
                 property_: Optional[str] = None,
                 attribute: str = "solid", color: str = "25,25,255,255",
                 volume: str = "", transform: Optional[str] = None,
                 group: Optional[str] = None, file_ref: str = "x_t",
                 facet_kind: str = "2", layer: str = "1") -> Optional[ET.Element]:
        """Append a ``<parts>`` element (STpre part metadata layout).

        The element is inserted under ``<group name=group>`` when given,
        otherwise directly under the document root.  Text/tail whitespace is
        set to match the ex4_e serialization style so edited files stay
        human-readable and parseable by the byte-stable serializer.
        """
        if self.find_part(name) is not None:
            return None
        parent: ET.Element = self.root
        if group:
            for grp in self.groups():
                g = _first(grp, "name")
                if g is not None and (g.text or "").strip() == group:
                    parent = grp
                    break
        parts = ET.Element("parts")
        parts.attrib["type"] = kind
        identity = ("1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")
        fields = [
            ("name", name),
            ("name2", name2 or name),
            ("property", property_ if property_ is not None else ""),
            ("attribute", attribute),
            ("volume", volume),
            ("color", color),
            ("mode", "global"),
            ("visible_count", "1"),
            ("tree_expand", "F"),
            ("layer", layer),
            ("monitor", "T"),
            ("rad_group_num", "0"),
            ("heat_balance", "F,F"),
            ("VF_balance", "F"),
            ("facet_kind", facet_kind),
            ("def_axis", "+Z"),
            ("file", file_ref),
            ("transform", transform if transform is not None else identity),
        ]
        for tag, value in fields:
            e = ET.SubElement(parts, tag)
            e.text = f" {value} "
            e.tail = "\n         "
        parts.tail = "\n      "
        parent.append(parts)
        return parts

    # -- parts deletion / grouping (M7) -----------------------------------

    def delete_part(self, name: str) -> bool:
        """Remove a ``<parts>`` entry plus its ``<element>`` boxes and
        conditions that bind this part.  Returns False when not found."""
        el = self.find_part(name)
        if el is None:
            return False
        parent = self.root
        for grp in self.groups():
            if el in list(grp):
                parent = grp
                break
        parent.remove(el)
        # element occupancy of the deleted part
        elem = self.elements()
        if elem is not None:
            for parts in list(elem.findall("parts")):
                if parts.attrib.get("name") == name:
                    elem.remove(parts)
        # conditions referencing the part
        for c in list(self.conditions()):
            t = _first(c, "parts")
            if t is not None and (t.text or "").strip() == name:
                self.root.remove(c)
        return True

    def move_parts_to_group(self, names: list[str],
                            group_name: str = "") -> list[str]:
        """Move part elements into ``<group name>`` (empty = root)."""
        names = [n for n in names if self.find_part(n) is not None]
        if not names:
            return []
        target: ET.Element = self.root
        if group_name:
            for grp in self.groups():
                n = _first(grp, "name")
                if n is not None and (n.text or "").strip() == group_name:
                    target = grp
                    break
            else:
                target = ET.Element("group")
                target.tail = "\n   "
                self.root.append(target)
                name_el = ET.SubElement(target, "name")
                name_el.text = f" {group_name} "
                name_el.tail = "\n   "
        for pname in names:
            el = self.find_part(pname)
            if el is None:
                continue
            if el in list(target):
                continue
            for grp in self.groups():
                if grp is target:
                    continue
                if el in list(grp):
                    grp.remove(el)
                    break
            else:
                if el in list(self.root):
                    self.root.remove(el)
            el.tail = "\n      " if group_name else "\n   "
            target.append(el)
        return names

    # -- mesh generation output (M3) --------------------------------------

    @staticmethod
    def _vec_text(vals: tuple[float, float, float]) -> str:
        return ",".join(f"{v:.17g}" for v in vals)

    def _mesh_child(self, parent: ET.Element, tag: str, text: str,
                    attrs: Optional[dict] = None) -> ET.Element:
        e = _first(parent, tag)
        if e is None:
            e = ET.SubElement(parent, tag)
            e.tail = "\n   "
        set_text(e, text)
        if attrs:
            e.attrib.update(attrs)
        return e

    def set_mesh(self, axes: dict[str, list[float]], *,
                 unit: str = "mm",
                 domain_min: tuple[float, float, float],
                 domain_max: tuple[float, float, float],
                 threshold: tuple[float, float, float] = (0.1, 0.1, 0.1),
                 ratio: tuple[float, float, float] = (1.2, 1.2, 1.2),
                 detection: int = 3,
                 method: int = 1,
                 element_max: int = 100_000_000,
                 part_min: Optional[tuple[float, float, float]] = None,
                 part_max: Optional[tuple[float, float, float]] = None,
                 ) -> None:
        """Write ``<mesh_control>`` + ``<mesh_block>`` from generated axes."""
        counts = tuple(len(axes.get(a, [])) for a in "xyz")
        grid_text = ",".join(str(v) for v in counts)
        mc = _first(self.root, "mesh_control")
        if mc is None:
            mc = ET.Element("mesh_control")
            mc.tail = "\n"
            self.root.append(mc)
            ET.SubElement(mc, "system")
            block = ET.SubElement(mc, "block")
            block.attrib["name"] = "RootBlock"
            block.tail = "\n   "
            for tag, text in (("kind", "domain"), ("min", ""), ("max", ""),
                              ("limit", ""), ("grid", "")):
                e = ET.SubElement(block, tag)
                e.text = f" {text} "
                e.tail = "\n      "
            sub = ET.SubElement(block, "subblock")
            sub.attrib["divide"] = "1,1,1"
            sub.tail = "\n      "
            area = ET.SubElement(sub, "area")
            area.attrib["no"] = "0"
            area.tail = "\n         "
            for tag in ("valid", "min", "max"):
                e = ET.SubElement(area, tag)
                e.text = "  "
                e.tail = "\n            "
            for tag, text in (
                    ("element_max", str(element_max)),
                    ("domain_kind", "1"),
                    ("select_vertex", str(detection)),
                    ("divide_method", str(method)),
                    ("divide_scale", "2"),
                    ("divide_ratio2", self._vec_text(ratio)),
                    ("default_extend", "0,0,0"),
                    ("outer_flag", "T,T,T,T,T,T"),
                    ("outer_range", "0,0,0,0,0,0"),
                    ("grid_outer_check", "0"),
                    ("edge_eps", "0.0001"),
                    ("element_threshold", "0.5"),
                    ("edge_contact", "0"),
                    ("grid_generate_type", "0"),
                    ("grid_generate_gerber", "0"),
                    ("grid_move_option", "0"),
                    ("block_boundary", "0"),
                    ("panel_block_face", "1"),
                    ("solid_scheme", "1"),
                    ("panel_scheme", "0"),
                    ("check_scheme", "1"),
            ):
                e = ET.SubElement(mc, tag)
                e.text = f" {text} "
                e.tail = "\n   "
        block = _first(mc, "block")
        if block is None:
            block = ET.SubElement(mc, "block")
            block.attrib["name"] = "RootBlock"
            block.tail = "\n   "
        block.attrib["name"] = "RootBlock"
        self._mesh_child(block, "kind", "domain")
        self._mesh_child(block, "min", self._vec_text(domain_min),
                         {"unit": unit})
        self._mesh_child(block, "max", self._vec_text(domain_max),
                         {"unit": unit})
        self._mesh_child(block, "limit", self._vec_text(threshold),
                         {"unit": unit})
        self._mesh_child(block, "grid", grid_text)
        self._mesh_child(mc, "select_vertex", str(detection))
        self._mesh_child(mc, "divide_method", str(method))
        self._mesh_child(mc, "divide_ratio2", self._vec_text(ratio))
        self._mesh_child(mc, "element_max", str(element_max))
        if part_min is not None and part_max is not None:
            outer = ",".join(
                f"{a:.17g},{b:.17g}" for a, b in zip(part_min, part_max))
            self._mesh_child(mc, "outer_range", outer)

        mb = _first(self.root, "mesh_block")
        if mb is None:
            mb = ET.Element("mesh_block")
            mb.tail = "\n"
            self.root.append(mb)
        for tag, text, attrs in (
                ("name", "RootBlock", {}),
                ("system", "0", {}),
                ("visible", "T", {}),
                ("tree_expand", "T", {}),
                ("min", self._vec_text(domain_min), {"unit": unit}),
                ("max", self._vec_text(domain_max), {"unit": unit}),
                ("extend_min", "0,0,0", {"unit": unit}),
                ("extend_max", "0,0,0", {"unit": unit}),
        ):
            self._mesh_child(mb, tag, text, attrs)
        for axis in "xyz":
            el = _first(mb, axis)
            if el is None:
                el = ET.SubElement(mb, axis)
                el.tail = "\n   "
            el.attrib["num"] = str(len(axes.get(axis, [])))
            el.attrib["unit"] = unit
            for child in list(el):
                el.remove(child)
            vals = axes.get(axis, [])
            for i, v in enumerate(vals, start=1):
                mark = "B" if i in (1, len(vals)) else ""
                g = ET.SubElement(el, "g")
                g.attrib["no"] = str(i)
                g.text = f" {v:.17g}" + (f",{mark}" if mark else "") + " "
                g.tail = "\n      "


class PropertyModel:
    """Typed view over :class:`PropertyDoc` (materials)."""

    def __init__(self, doc: PropertyDoc):
        self.doc = doc
        self.root = doc.root

    def groups(self) -> list[ET.Element]:
        return _children(self.root, "group")

    def entries(self) -> list[tuple[ET.Element, str]]:
        """All material entries as ``(entry_element, material_name)``."""
        out: list[tuple[ET.Element, str]] = []
        for grp in self.groups():
            for ent in _children(grp, "entry"):
                n = _first(ent, "name")
                name = n.text.strip() if n is not None and n.text else ""
                out.append((ent, name))
        return out

    def material_names(self) -> list[str]:
        return [name for _, name in self.entries()]

    def group_catalog(self) -> list[tuple[str, str, list[str]]]:
        """``(group_type, group_name, [entry_names…])`` in document order."""
        out: list[tuple[str, str, list[str]]] = []
        for grp in self.groups():
            t = _first(grp, "type")
            n = _first(grp, "name")
            gtype = t.text.strip() if t is not None and t.text else ""
            gname = n.text.strip() if n is not None and n.text else ""
            names: list[str] = []
            for ent in _children(grp, "entry"):
                en = _first(ent, "name")
                if en is not None and en.text and en.text.strip():
                    names.append(en.text.strip())
            out.append((gtype, gname, names))
        return out

    def find_entry(self, name: str) -> Optional[ET.Element]:
        for ent, n in self.entries():
            if n == name:
                return ent
        return None


    def set_entry_value(self, material: str, key: str, value: str) -> bool:
        ent = self.find_entry(material)
        if ent is None:
            return False
        c = _first(ent, key)
        if c is not None:
            set_text(c, value)
        else:
            child = ET.SubElement(ent, key)
            child.text = f" {value} "
        return True
