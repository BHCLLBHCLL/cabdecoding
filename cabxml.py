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
        if c is not None:
            set_text(c, material)
        return True

    def set_part_color(self, name: str, rgba: tuple[int, int, int, int]) -> bool:
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "color")
        if c is not None:
            set_text(c, ",".join(str(v) for v in rgba))
        return True

    # -- regions / values / conditions ------------------------------------

    def regions(self) -> list[ET.Element]:
        return _children(self.root, "region")

    def analysis_region(self) -> Optional[ET.Element]:
        return _first(self.root, "analysis_region")

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
