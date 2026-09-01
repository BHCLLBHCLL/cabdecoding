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


# Official STpre ``parts@type`` → in-tree kind (2023.2 ST Example).
# XML type is preserved on disk; PartInfo.kind is the canonical name.
PART_KIND_ALIASES = {
    "air_outlet": "diffuser",
    "axial_fan_model": "axial_fan",
    "spin_rectangle": "revolved",
    "case_cube": "enclosure",
    "hexa": "hexahedron",
}

NETWORK_PACKAGE_KIND = {
    "TWO_RESIST": "two_resistor",
    "TWO_RESISTOR": "two_resistor",
    "MULTI_RESIST": "multi_resistor",
    "MULTI_RESISTOR": "multi_resistor",
    "DELPHI": "delphi",
}


def canonical_part_kind(kind: str, elem: Optional[ET.Element] = None) -> str:
    """Map an official STpre part type onto the in-tree kind name.

    ``type="network"`` uses ``<package>`` (exA22-1 ``TWO_RESIST`` →
    two_resistor). Unknown network packages default to two_resistor —
    the only package observed in the 2023.2 ST Example set.
    """
    k = (kind or "").strip()
    if k == "network":
        pkg = ""
        if elem is not None:
            c = _first(elem, "package")
            if c is not None and c.text:
                pkg = c.text.strip().upper().replace("-", "_")
        return NETWORK_PACKAGE_KIND.get(pkg, "two_resistor")
    return PART_KIND_ALIASES.get(k, k)


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
    mesh_fine_divide: str = ""   # per-axis fine subdivision "x,y,z"
    divide: str = ""             # radial subdivision (cylinder parts)


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

    def set_unit(self, tag: str, text: str) -> bool:
        """Set ``<unit>/<tag>`` (display / geometry / ...)."""
        u = _first(self.root, "unit")
        if u is None:
            u = ET.SubElement(self.root, "unit")
            u.tail = "\n"
        el = _first(u, tag)
        if el is None:
            el = ET.SubElement(u, tag)
            el.tail = "\n      "
        set_text(el, text)
        return True

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
                    kind=canonical_part_kind(
                        el.attrib.get("type", "body"), el),
                    property=t("property"),
                    attribute=t("attribute"),
                    color=t("color"),
                    volume=t("volume"),
                    transform=t("transform"),
                    base=t("base"),
                    size=t("size"),
                    group=gname,
                    mesh_fine_divide=t("mesh_fine_divide"),
                    divide=t("divide"),
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
        # keep <condition><parts> references (body_move bindings, ...)
        # pointing at the renamed part
        for c in self.conditions():
            pe = _first(c, "parts")
            if pe is None or not pe.text:
                continue
            tokens = [t.strip() for t in pe.text.split(",")]
            if old in tokens:
                set_text(pe, ",".join(
                    new if t == old else t for t in tokens))
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
        if c is None:
            c = ET.SubElement(el, "color")
            c.tail = "\n      "
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

    def set_part_attribute(self, name: str, attribute: str) -> bool:
        """Update ``<parts>/<attribute>`` (solid / fluid / panel …)."""
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "attribute")
        if c is None:
            c = ET.SubElement(el, "attribute")
            c.tail = "\n      "
        set_text(c, attribute)
        return True

    def set_part_virtual(self, name: str, on: bool) -> bool:
        """Create/update ``<parts>/<virtual>`` (T/F)."""
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "virtual")
        if c is None:
            c = ET.SubElement(el, "virtual")
            c.tail = "\n      "
        set_text(c, "T" if on else "F")
        return True

    # -- part motion (moving object, COM-probed 2026-08-16) ----------------
    #
    # ``Model.SetMoveBodyControl(key, params)`` on STpre 2025.2 saves:
    #
    #     <value type="body_move">
    #        <name> MoveBody1 </name>
    #        <kind> translate|rotate|translate+rotate|coordinate </kind>
    #        <velocity_x unit="m/s"> .. </velocity_x> (y/z)     # translate
    #        <omega> .. </omega>                                # rotate
    #        <center unit="default"> x,y,z </center>
    #        <normal> x,y,z </normal>                           # rotate
    #        <coordinate_x unit="mm"> .. </coordinate_x> (y/z)  # coordinate
    #     </value>
    #     <condition>
    #        <parts> part </parts>
    #        <value> MoveBody1 </value>
    #     </condition>
    #
    # Kind switch clears the other kind's fields (probe movebody_X diff).

    _MOTION_FIELDS = {
        "translate": ("velocity_x", "velocity_y", "velocity_z"),
        "rotate": ("omega", "center", "normal"),
        "translate+rotate": ("velocity_x", "velocity_y", "velocity_z",
                             "omega", "center", "normal"),
        "coordinate": ("coordinate_x", "coordinate_y", "coordinate_z"),
    }

    def part_motion(self, name: str) -> Optional[dict]:
        """The ``body_move`` motion definition bound to part ``name``.

        Returns ``{kind, velocity, omega, center, normal, coordinate,
        value_name}`` (absent fields ``None``) or ``None`` when the part
        has no motion condition.
        """
        for c in self.conditions():
            p = _first(c, "parts")
            v = _first(c, "value")
            if p is None or v is None or (p.text or "").strip() != name:
                continue
            val = self.find_value((v.text or "").strip())
            if val is None or val.attrib.get("type") != "body_move":
                continue

            def f1(tag):
                el = _first(val, tag)
                try:
                    return float(el.text) if el is not None and el.text \
                        else None
                except ValueError:
                    return None

            def f3(tag):
                el = _first(val, tag)
                if el is None or not el.text:
                    return None
                try:
                    parts = tuple(float(x) for x in el.text.split(",")[:3])
                except ValueError:
                    return None
                return parts if len(parts) == 3 else None

            vel = [f1(f"velocity_{ax}") for ax in "xyz"]
            coord = [f1(f"coordinate_{ax}") for ax in "xyz"]
            kind_el = _first(val, "kind")
            return {
                "kind": (kind_el.text or "").strip()
                        if kind_el is not None else "",
                "velocity": vel if any(x is not None for x in vel) else None,
                "omega": f1("omega"),
                "center": f3("center"),
                "normal": f3("normal"),
                "coordinate": coord
                              if any(x is not None for x in coord) else None,
                "value_name": (v.text or "").strip(),
            }
        return None

    def set_part_motion(self, name: str, motion: Optional[dict]) -> bool:
        """Create/update (dict) or remove (``None``) a part's motion.

        ``motion`` keys (all optional except ``kind``): ``velocity``
        (3-tuple, m/s), ``omega`` (rad/s), ``center``/``normal``
        (3-tuples), ``coordinate`` (3-tuple).  Removing passes ``None``.
        """
        if self.find_part(name) is None:
            return False
        cur = self.part_motion(name)
        if motion is None:
            if cur is None:
                return False
            return self.delete_value(cur["value_name"])
        kind = (motion.get("kind") or "").strip()
        if kind not in self._MOTION_FIELDS:
            return False

        # reuse (or create) the part's body_move value
        if cur is not None:
            vname = cur["value_name"]
            val = self.find_value(vname)
        else:
            vname = self._next_motion_name()
            val = ET.Element("value")
            val.attrib["type"] = "body_move"
            val.tail = "\n   "
            n = ET.SubElement(val, "name")
            n.tail = "\n      "
            set_text(n, vname)
            last = self.values()[-1] if self.values() else None
            if last is not None:
                self.root.insert(list(self.root).index(last) + 1, val)
            else:
                self.root.append(val)
            cond = ET.Element("condition")
            cond.tail = "\n   "
            pe = ET.SubElement(cond, "parts")
            pe.tail = "\n      "
            set_text(pe, name)
            ve = ET.SubElement(cond, "value")
            ve.tail = "\n      "
            set_text(ve, vname)
            conds = self.conditions()
            if conds:
                self.root.insert(list(self.root).index(conds[-1]) + 1, cond)
            else:
                self.root.append(cond)

        kind_el = _first(val, "kind")
        if kind_el is None:
            kind_el = ET.SubElement(val, "kind")
            kind_el.tail = "\n      "
        set_text(kind_el, kind)

        # clear stale fields from a previous kind (STpre behaviour)
        stale = {"velocity_x", "velocity_y", "velocity_z", "omega",
                 "center", "normal", "coordinate_x", "coordinate_y",
                 "coordinate_z"} - set(self._MOTION_FIELDS[kind])
        for tag in stale:
            el = _first(val, tag)
            if el is not None:
                val.remove(el)

        def set_field(tag: str, text: str, unit: Optional[str] = None):
            el = _first(val, tag)
            if el is None:
                el = ET.SubElement(val, tag)
                el.tail = "\n      "
            set_text(el, text)
            if unit is not None:
                el.attrib["unit"] = unit
            else:
                el.attrib.pop("unit", None)

        vel = motion.get("velocity")
        if vel is not None and len(vel) == 3:
            for ax, v in zip("xyz", vel):
                set_field(f"velocity_{ax}", f"{float(v):.17g}", "m/s")
        if motion.get("omega") is not None:
            set_field("omega", f"{float(motion['omega']):.17g}")
        for tag in ("center", "normal"):
            vec = motion.get(tag)
            if vec is not None and len(vec) == 3:
                set_field(
                    tag, ",".join(f"{float(v):.17g}" for v in vec),
                    "default" if tag == "center" else None)
        coord = motion.get("coordinate")
        if coord is not None and len(coord) == 3:
            for ax, v in zip("xyz", coord):
                set_field(f"coordinate_{ax}", f"{float(v):.17g}", "mm")
        return True

    def _next_motion_name(self) -> str:
        used = set()
        for v in self.values():
            if v.attrib.get("type") != "body_move":
                continue
            n = _first(v, "name")
            if n is not None and n.text:
                used.add((n.text or "").strip())
        idx = 1
        while f"MoveBody{idx}" in used:
            idx += 1
        return f"MoveBody{idx}"

    # -- special part parameters (R7, COM-probed 2026-08-16) ------------------
    #
    # tools/probe_special_parts.py 实证（结果存 probe_work/
    # special_parts_probe.json），STpre 2025.2 各专用件的落盘格式：
    #
    # peltier    CreatePeltierModel → ``<parts type="peltier">`` 子元素：
    #     <thick unit="mm">tc,th
    #     <paramV unit="default">Vdrv,V1,V2,V3
    #     <paramA unit="default">Imax,I1,I2,I3,Th1
    #     <paramQ unit="default">Qmax,Q1,Q2,Q3,Th2
    #     <paramT>DTmax,DT1
    #     <def_axis>+Z
    # card_guide CreateCardGuideModel → ``<parts type="card_guide">`` 子元素：
    #     <fin unit="mm">f1 <space unit="mm">h1,h2 <depth unit="mm">d1,d2
    #     <nfin>8 <row_axis>+X <def_plane>+Z
    # diffuser  CreateLinerDiffuserModel → ``<parts type="air_outlet">``
    #     子元素 <angle>（度）+ 绑定 <value type="flux">（<kind>outlet、
    #     <flow_rate unit="m3/s">、<temperature unit="C">、<aircon_type>S）
    #     经 <condition><parts> 挂到部件（value 名 _outletN_flux）。
    # heat_pipe  Model.SetHeatPipeCondition(cool, hot, r, qmax) 落盘为
    #     顶层 <thermal_resist_model> 网络 + region pair（kind=heatpipe），
    #     其 <heatpipe unit="K/W,W"> 存 "r,qmax"；本 API 以部件子元素
    #     简化存储（字段一一对应 cool/hot/r/qmax）。
    # ac_unit    CreateAirconModel 在 2025.2 返回 None（部件级未实证，
    #     按手册降级）；条件模型容器已实证（AirconModel.SetParam）：
    #     <analysis_air_etc><aircon> 下的 <name>/<kind>/<model>cooling|
    #     heating/<flow_type>area/<power_type type="power"><power unit="W">/
    #     <temperature_limit>none|minmax/<tmin>/<tmax>/<humidity_limit>/
    #     <qvn unit="m3/s">，本 API 以同名部件子元素镜像存储。

    #: 专用件参数字段表：tag -> (unit 属性, 长度；1 为标量，
    #: "int" 为整数, "str" 为字符串)
    _SPECIAL_PARAM_FIELDS = {
        "peltier": {
            "thick": ("mm", 2), "paramV": ("default", 4),
            "paramA": ("default", 5), "paramQ": ("default", 5),
            "paramT": (None, 2), "def_axis": (None, "str"),
        },
        "card_guide": {
            "fin": ("mm", 1), "space": ("mm", 2), "depth": ("mm", 2),
            "nfin": (None, "int"), "row_axis": (None, "str"),
            "def_plane": (None, "str"),
        },
        "ac_unit": {
            "ac_model": (None, "str"), "ac_kind": (None, "int"),
            "operation_type": (None, "str"), "flow_type": (None, "str"),
            "capability": ("W", 1), "flow_rate": ("m3/s", 1),
            "t_limit_type": (None, "str"), "tmin": (None, 1),
            "tmax": (None, 1), "h_limit_type": (None, "str"),
        },
        "diffuser": {
            # <angle> 为实证部件子元素；后两项镜像到绑定的
            # value type="flux"（kind=outlet，实证 _outlet1_flux）
            "supply_air_angle": (None, 1),
            "supply_flow_rate": ("m3/s", 1),
            "inflow_temperature": ("C", 1),
        },
        "heat_pipe": {
            "cooling_part": (None, "str"), "heat_release_part": (None, "str"),
            "thermal_resistance": ("K/W", 1), "max_heat_transport": ("W", 1),
        },
        # R3.5a fan family: field names from STpreBase string evidence
        # (Create*Model params r1/r2/tk/t1/t2/axis/type/kind); the Create*
        # COM full-signature storage is not yet terminal-proven (minimal-arg
        # probe returned no part diff), so these fields use our own part
        # children like the other special parts.
        "fan": {
            "r1": ("mm", 1), "r2": ("mm", 1), "thickness": ("mm", 1),
            "axis": (None, "str"), "type": (None, "str"),
        },
        "axial_fan": {
            "r1": ("mm", 1), "r2": ("mm", 1), "t1": ("mm", 1),
            "t2": ("mm", 1), "axis": (None, "str"), "kind": (None, "str"),
        },
        "blower_fan": {
            "r1": ("mm", 1), "r2": ("mm", 1), "thickness": ("mm", 1),
            "axis": (None, "str"),
        },
        # R3.5b/c: field names from STpreBase string evidence
        # (CreatePinFinModel f1/h1/f2/h2/n1/n2 + axis; CreateSlitPunchingModel
        # plane/flag/thick/count; CreateAnemoModel mode/type).
        "pin_fin": {
            "f1": ("mm", 1), "f2": ("mm", 1), "h1": ("mm", 1),
            "h2": ("mm", 1), "n1": (None, "int"), "n2": (None, "int"),
            "axis": (None, "str"),
        },
        "slit_punching": {
            "plane": (None, "str"), "thick": ("mm", 1),
            "count": (None, "int"),
        },
        "anemostat": {
            "mode": (None, "str"), "type": (None, "str"),
        },
        # W2: compact thermal models. two_resistor / multi_resistor store
        # JEDEC Rjc/Rjb/power as part children (same tags as cab_parts
        # _write_part_condition_xml). Delphi node network is
        # ``<thermal_node no>`` / name / resistance (unit C/W).
        "two_resistor": {
            "rjc": ("K/W", 1), "rjb": ("K/W", 1),
            "package_power": ("W", 1),
        },
        "multi_resistor": {
            "rjc": ("K/W", 1), "rjb": ("K/W", 1),
            "package_power": ("W", 1), "n_resistors": (None, "int"),
        },
        "delphi": {},
    }

    def _special_kind(self, name: str) -> Optional[str]:
        """部件名 → 专用件 kind（非专用件返回 None）。"""
        el = self.find_part(name)
        if el is None:
            return None
        kind = canonical_part_kind(el.attrib.get("type", ""), el)
        return kind if kind in self._SPECIAL_PARAM_FIELDS else None

    def part_params(self, name: str) -> Optional[dict]:
        """读取专用件参数（未存储的字段不出现）。

        返回 ``{tag: float | [float,...] | int | str}``；非专用件或
        部件不存在返回 ``None``。diffuser 的风量/温度从绑定的
        flux 值合并读取（实证存储位置）。
        """
        kind = self._special_kind(name)
        if kind is None:
            return None
        el = self.find_part(name)
        out: dict = {}
        for tag, (_unit, fmt) in self._SPECIAL_PARAM_FIELDS[kind].items():
            c = _first(el, tag)
            if c is None or not c.text:
                continue
            text = c.text.strip()
            if fmt == "str":
                out[tag] = text
            elif fmt == "int":
                try:
                    out[tag] = int(float(text.split(",")[0]))
                except ValueError:
                    continue
            else:
                try:
                    vals = [float(v) for v in text.split(",")
                            if v.strip()]
                except ValueError:
                    continue
                if not vals:
                    continue
                out[tag] = vals[0] if fmt == 1 else vals
        if kind == "delphi":
            nodes = []
            for n in el.findall("thermal_node"):
                nm = _first(n, "name")
                res = _first(n, "resistance")
                name_s = (nm.text or "").strip() if nm is not None else ""
                try:
                    r = float((res.text or "0").strip()) if res is not None else 0.0
                except ValueError:
                    r = 0.0
                if name_s:
                    nodes.append((name_s, r))
            if nodes:
                out["nodes"] = nodes
        if kind == "diffuser":
            # 风量/温度优先取绑定的 flux 值（实证存储位置）
            val = self._part_flux_value(name)
            if val is not None:
                for tag, vtag in (("supply_flow_rate", "flow_rate"),
                                  ("inflow_temperature", "temperature")):
                    c = _first(val, vtag)
                    if c is not None and c.text:
                        try:
                            out[tag] = float(c.text)
                        except ValueError:
                            pass
        return out

    def _part_flux_value(self, name: str) -> Optional[ET.Element]:
        """绑定到部件的 outlet 类 flux 值（无则 None）。"""
        vname = self.condition_value("parts", name)
        if not vname:
            return None
        val = self.find_value(vname)
        if val is None or val.attrib.get("type") != "flux":
            return None
        k = _first(val, "kind")
        if k is None or (k.text or "").strip() != "outlet":
            return None
        return val

    def _next_flux_name(self) -> str:
        """下一个 ``_outletN_flux`` 值名（实证命名）。"""
        used = set()
        for v in self.values():
            if v.attrib.get("type") != "flux":
                continue
            n = _first(v, "name")
            if n is not None and n.text \
                    and (n.text or "").strip().startswith("_outlet"):
                used.add((n.text or "").strip())
        idx = 1
        while f"_outlet{idx}_flux" in used:
            idx += 1
        return f"_outlet{idx}_flux"

    def set_part_params(self, name: str, params: dict) -> bool:
        """写入专用件参数（部分写入，未知字段拒绝）。

        数值字段接受标量或定长列表；diffuser 的风量/温度同步
        镜像到绑定的 ``value type="flux"``（kind=outlet）。
        """
        kind = self._special_kind(name)
        if kind is None:
            return False
        spec = self._SPECIAL_PARAM_FIELDS[kind]
        extra = set()
        if kind == "delphi":
            extra.add("nodes")
        for key in params:
            if key not in spec and key not in extra:
                return False
        el = self.find_part(name)

        def set_field(tag: str, text: str, unit):
            c = _first(el, tag)
            if c is None:
                c = ET.SubElement(el, tag)
                c.tail = "\n         "
            set_text(c, text)
            if unit is not None:
                c.attrib["unit"] = unit
            else:
                c.attrib.pop("unit", None)

        for tag, value in params.items():
            if value is None or tag in extra:
                continue
            unit, fmt = spec[tag]
            if fmt == "str":
                set_field(tag, str(value), unit)
            elif fmt == "int":
                set_field(tag, str(int(value)), unit)
            else:
                if isinstance(value, (int, float)):
                    vals = [float(value)]
                else:
                    vals = [float(v) for v in value]
                if fmt != 1 and len(vals) != fmt:
                    return False
                set_field(tag, ",".join(f"{v:.12g}" for v in vals), unit)

        # diffuser：风量/温度镜像到绑定的 flux 值（实证格式）
        if kind == "diffuser" and ("supply_flow_rate" in params
                                   or "inflow_temperature" in params):
            val = self._part_flux_value(name)
            vname = (_first(val, "name").text or "").strip() \
                if val is not None and _first(val, "name") is not None \
                else self._next_flux_name()
            children = [("kind", "outlet", None)]
            if params.get("supply_flow_rate") is not None:
                children.append(("flow_rate",
                                 f"{float(params['supply_flow_rate']):.12g}",
                                 "m3/s"))
            if params.get("inflow_temperature") is not None:
                children.append((
                    "temperature",
                    f"{float(params['inflow_temperature']):.12g}", "C"))
            children.append(("aircon_type", "S", None))
            if not self.upsert_value("flux", vname, children):
                return False
            if not self.bind_condition("parts", name, vname):
                return False
        if kind == "delphi" and "nodes" in params:
            for child in list(el.findall("thermal_node")):
                el.remove(child)
            for i, item in enumerate(params["nodes"] or [], start=1):
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    nm, r = item[0], item[1]
                else:
                    continue
                n = ET.SubElement(el, "thermal_node")
                n.attrib["no"] = str(i)
                n.tail = "\n         "
                name_el = ET.SubElement(n, "name")
                name_el.text = f" {nm} "
                name_el.tail = "\n            "
                res_el = ET.SubElement(n, "resistance")
                res_el.text = f" {float(r):.12g} "
                res_el.attrib["unit"] = "C/W"
                res_el.tail = "\n         "
        return True

    def reorder_parts(self, names: list[str], anchor: str, *,
                      before: bool = True) -> list[str]:
        """Move ``names`` immediately before/after ``anchor`` (same parent)."""
        anchor_el = self.find_part(anchor)
        if anchor_el is None:
            return []
        parent = self.root
        for grp in self.groups():
            if anchor_el in list(grp):
                parent = grp
                break
        els: list[ET.Element] = []
        for n in names:
            if n == anchor:
                continue
            el = self.find_part(n)
            if el is None:
                continue
            els.append(el)
        if not els:
            return []
        for el in els:
            for grp in self.groups():
                if el in list(grp):
                    grp.remove(el)
                    break
            else:
                if el in list(self.root):
                    self.root.remove(el)
        kids = list(parent)
        try:
            idx = kids.index(anchor_el)
        except ValueError:
            return []
        insert_at = idx if before else idx + 1
        moved: list[str] = []
        for j, el in enumerate(els):
            parent.insert(insert_at + j, el)
            n = _first(el, "name")
            if n is not None and n.text:
                moved.append(n.text.strip())
        return moved

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

    def coordinate_systems(self) -> list[dict]:
        """Named reference CS stored under ``<coordinate_systems>/<cs>``."""
        root = _first(self.root, "coordinate_systems")
        if root is None:
            return []
        out: list[dict] = []
        for cs in _children(root, "cs"):
            name = (cs.attrib.get("name") or "").strip()
            if not name:
                n = _first(cs, "name")
                name = (n.text or "").strip() if n is not None and n.text else ""
            if not name:
                continue

            def vec(tag, default):
                el = _first(cs, tag)
                parsed = self._parse_vec3(el)
                return parsed if parsed is not None else default

            out.append({
                "name": name,
                "origin": vec("origin", (0.0, 0.0, 0.0)),
                "axis_x": vec("axis_x", (1.0, 0.0, 0.0)),
                "axis_y": vec("axis_y", (0.0, 1.0, 0.0)),
                "axis_z": vec("axis_z", (0.0, 0.0, 1.0)),
            })
        return out

    def get_coordinate_system(self, name: str) -> Optional[dict]:
        for cs in self.coordinate_systems():
            if cs["name"] == name:
                return cs
        return None

    def upsert_coordinate_system(
            self, name: str,
            origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
            axis_x: tuple[float, float, float] = (1.0, 0.0, 0.0),
            axis_y: tuple[float, float, float] = (0.0, 1.0, 0.0),
            axis_z: tuple[float, float, float] = (0.0, 0.0, 1.0),
            ) -> bool:
        """Create or replace a named reference coordinate system."""
        name = (name or "").strip()
        if not name:
            return False
        root = _first(self.root, "coordinate_systems")
        if root is None:
            root = ET.SubElement(self.root, "coordinate_systems")
            root.tail = "\n"
        el = None
        for cs in _children(root, "cs"):
            if (cs.attrib.get("name") or "").strip() == name:
                el = cs
                break
        if el is None:
            el = ET.SubElement(root, "cs")
            el.tail = "\n   "
        el.attrib["name"] = name
        for tag, vals, unit in (
                ("origin", origin, "mm"),
                ("axis_x", axis_x, None),
                ("axis_y", axis_y, None),
                ("axis_z", axis_z, None)):
            c = _first(el, tag)
            if c is None:
                c = ET.SubElement(el, tag)
                c.tail = "\n      "
            set_text(c, ",".join(f"{float(v):.12g}" for v in vals))
            if unit:
                c.attrib["unit"] = unit
            else:
                c.attrib.pop("unit", None)
        return True

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

    # ---- <analysis_etc> (STpre advanced-analysis storage) -------------
    # STpre keeps several CW analysis types outside <analysis_set>:
    #   <analysis_etc><plant_resistance> 1 </plant_resistance></analysis_etc>
    #   <analysis_etc><marangoni><temp_coeff> 0 </temp_coeff></marangoni>
    #   <analysis_etc><topology_optimize> ... </topology_optimize>
    #   <analysis_etc><phase_change_material/>  (pcm)
    #   <analysis_etc><partcile_echarge> 1|2 </partcile_echarge> (es field)
    # Verified against STpre 2025.2 COM SetAnalysisType save round-trips.

    def ensure_analysis_etc(self) -> ET.Element:
        """Create <analysis_etc> (inserted after <analysis_set>)."""
        aet = _first(self.root, "analysis_etc")
        if aet is not None:
            return aet
        aet = ET.Element("analysis_etc")
        aet.text = "\n   "
        aet.tail = "\n"
        aset = _first(self.root, "analysis_set")
        if aset is not None:
            children = list(self.root)
            self.root.insert(children.index(aset) + 1, aet)
        else:
            self.root.append(aet)
        return aet

    def analysis_etc_value(self, tag: str, default: str = "") -> str:
        aet = _first(self.root, "analysis_etc")
        el = _first(aet, tag) if aet is not None else None
        return (el.text or "").strip() if el is not None and el.text \
            else default

    def set_analysis_etc_value(self, tag: str, text: str) -> bool:
        aet = self.ensure_analysis_etc()
        el = _first(aet, tag)
        if el is None:
            el = ET.SubElement(aet, tag)
            el.tail = "\n   "
        set_text(el, text)
        return True

    def analysis_etc_section(self, tag: str):
        """Return the named child element of <analysis_etc> or None."""
        aet = _first(self.root, "analysis_etc")
        return _first(aet, tag) if aet is not None else None

    def ensure_analysis_etc_section(self, tag: str) -> ET.Element:
        aet = self.ensure_analysis_etc()
        sec = _first(aet, tag)
        if sec is None:
            sec = ET.SubElement(aet, tag)
            sec.tail = "\n   "
        return sec

    def remove_analysis_etc_section(self, tag: str) -> bool:
        aet = _first(self.root, "analysis_etc")
        if aet is None:
            return False
        sec = _first(aet, tag)
        if sec is None:
            return False
        aet.remove(sec)
        return True

    def analysis_etc_child(self, section: str, tag: str,
                           default: str = "") -> str:
        sec = self.analysis_etc_section(section)
        el = _first(sec, tag) if sec is not None else None
        return (el.text or "").strip() if el is not None and el.text \
            else default

    def set_analysis_etc_child(self, section: str, tag: str, text: str,
                               unit=None) -> bool:
        sec = self.ensure_analysis_etc_section(section)
        el = _first(sec, tag)
        if el is None:
            el = ET.SubElement(sec, tag)
            el.tail = "\n         "
        set_text(el, text)
        if unit is not None:
            el.attrib["unit"] = unit
        return True

    # ---- R8-A CW 深字段存储辅助 -----------------------------------------
    # <analysis_set>/<radiation> 以子元素携带求解器深参数（STpre 2025.2 COM
    # 保存实证：method/calc_cycle/solver_eps/space_cycle/em0_kind/part_em_kind/
    # output_group/output_factor/max_particle/max_group_num/parts_group_num）；
    # @type 为 'vf'/'flux'/'mc'（CW Analysis Types 页写入）。

    def radiation_element(self) -> Optional[ET.Element]:
        """返回 ``<analysis_set>/<radiation>``（可能为 None）。"""
        aset = _first(self.root, "analysis_set")
        return _first(aset, "radiation") if aset is not None else None

    def radiation_type(self) -> str:
        """辐射方法 @type（'vf'/'flux'/'mc'，缺省 ''）。"""
        el = self.radiation_element()
        return el.attrib.get("type", "") if el is not None else ""

    def set_radiation_type(self, type_: str) -> bool:
        """确保 <radiation> 存在并更新 @type（不覆盖已有子元素）。"""
        aset = self.ensure_analysis_set()
        el = _first(aset, "radiation")
        if el is None:
            el = ET.SubElement(aset, "radiation")
            el.tail = "\n   "
        el.attrib["type"] = type_
        return True

    def radiation_param(self, tag: str, default: str = "") -> str:
        """读取 <radiation> 子元素文本（MC 光线数/分组上限等深参数）。"""
        el = self.radiation_element()
        c = _first(el, tag) if el is not None else None
        return (c.text or "").strip() if c is not None and c.text \
            else default

    def set_radiation_param(self, tag: str, text: str) -> bool:
        """写入 <radiation> 子元素（不存在时先建 <radiation type='vf'>）。"""
        aset = self.ensure_analysis_set()
        el = _first(aset, "radiation")
        if el is None:
            el = ET.SubElement(aset, "radiation")
            el.tail = "\n   "
            el.attrib["type"] = "vf"
        c = _first(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n     "
        set_text(c, text)
        return True

    # <analysis_etc>/<free_surf type='mars'|'vof'> 以 XML 属性携带自由面
    # 深参数（STpre 2025.2 COM SetAnalysisType('mars'/'vof','T') 保存实证，
    # 见 tools/probe_work/cwtypes2_mars.cab / cwtypes2_vof.cab：MARS 侧
    # fluid_no/contact/fractional_step/cutoff/vof_list_cycle/diffusion_phase/
    # diffusion_fluid/cutoff_save/viscosity_average/viscosity_on_surf/
    # conservation_term/one_fluid_model/mars_marangoni/mars_pcle_*；
    # VOF 侧 fluid_no/contact/fractional_step/surface_set/flow_list/
    # hydro_pres/v_correction/interpolation）。

    def free_surf_element(self) -> Optional[ET.Element]:
        """返回 ``<analysis_etc>/<free_surf>``（可能为 None）。"""
        aet = _first(self.root, "analysis_etc")
        return _first(aet, "free_surf") if aet is not None else None

    def free_surf_type(self) -> str:
        """自由面方法 @type（'mars'/'vof'，缺省 ''）。"""
        el = self.free_surf_element()
        return el.attrib.get("type", "") if el is not None else ""

    def free_surf_attr(self, name: str, default: str = "") -> str:
        """读取 <free_surf> 属性（MARS/VOF 深参数统一属性存储）。"""
        el = self.free_surf_element()
        return el.attrib.get(name, default) if el is not None else default

    def set_free_surf_attr(self, name: str, value: str,
                           type_: Optional[str] = None) -> bool:
        """写入 <free_surf> 属性；元素缺失时按 ``type_``（缺省 'mars'）新建。"""
        sec = self.ensure_analysis_etc_section("free_surf")
        if "type" not in sec.attrib and type_ is None:
            sec.attrib["type"] = "mars"
        elif type_ is not None:
            sec.attrib["type"] = type_
        sec.attrib[name] = value
        return True

    def value_fields(self, value_type: str, name: str) -> dict[str, str]:
        """按 type+name 读取 ``<value>`` 的子元素文本字典（未命中返回 {}）。

        供 CW 深字段（粒子模型扩展/多步反应速率等）复用通用 kv 存储。
        """
        for v in self.values():
            if v.attrib.get("type") != value_type:
                continue
            n = _first(v, "name")
            if n is not None and (n.text or "").strip() == name:
                return {c.tag: (c.text or "").strip()
                        for c in v if c.tag != "name"}
        return {}

    def values_of_type(self, value_type: str) -> list[ET.Element]:
        """返回所有 ``<value type=...>`` 元素（多步反应表等按序读取）。"""
        return [v for v in self.values()
                if v.attrib.get("type") == value_type]

    def ensure_analysis_file(self) -> ET.Element:
        """``<analysis_set>/<file>`` block for Field/Restart/TM names."""
        aset = self.ensure_analysis_set()
        f = _first(aset, "file")
        if f is not None:
            return f
        f = ET.SubElement(aset, "file")
        f.text = "\n         "
        f.tail = "\n   "
        return f

    def file_value(self, tag: str, default: str = "") -> str:
        aset = _first(self.root, "analysis_set")
        f = _first(aset, "file") if aset is not None else None
        el = _first(f, tag) if f is not None else None
        return (el.text or "").strip() if el is not None and el.text \
            else default

    def set_file_value(self, tag: str, text: str) -> bool:
        f = self.ensure_analysis_file()
        el = _first(f, tag)
        if el is None:
            el = ET.SubElement(f, tag)
            el.tail = "\n         "
        set_text(el, text)
        return True

    def ensure_output(self) -> ET.Element:
        out = _first(self.root, "output")
        if out is not None:
            return out
        out = ET.Element("output")
        out.tail = "\n"
        self.root.append(out)
        return out

    def output_value(self, tag: str, default: str = "", *,
                     type_: Optional[str] = None) -> str:
        out = _first(self.root, "output")
        if out is None:
            return default
        for el in out:
            if el.tag != tag:
                continue
            if type_ is not None and el.attrib.get("type") != type_:
                continue
            if type_ is None and "type" in el.attrib and tag in (
                    "restart", "fout", "post", "minmax_var"):
                continue
            return (el.text or "").strip() if el.text else default
        return default

    def set_output_value(self, tag: str, text: str, *,
                         type_: Optional[str] = None,
                         type_extra: Optional[str] = None) -> bool:
        """Set ``<output>/<tag>``; optional ``type`` attribute for typed tags."""
        out = self.ensure_output()
        el = None
        for c in out:
            if c.tag != tag:
                continue
            if type_ is not None and c.attrib.get("type") != type_:
                continue
            if type_ is None and "type" in c.attrib and tag in (
                    "restart", "fout", "post", "minmax_var"):
                continue
            el = c
            break
        if el is None:
            el = ET.SubElement(out, tag)
            el.tail = "\n      "
            if type_ is not None:
                el.attrib["type"] = type_
            if type_extra is not None:
                # e.g. time_series_cycle type="cycle:L"
                el.attrib["type"] = type_extra
        elif type_ is not None:
            el.attrib["type"] = type_
        elif type_extra is not None:
            el.attrib["type"] = type_extra
        set_text(el, text)
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

    def upsert_express(self, name: str, kind: str, text: str) -> bool:
        """Create/update an <express> computing function (STpre format).

        COM-probed 2026-08-15: CreateExpression(name, 'script') + SetText
        + value.SetExpression(key, name) saves as:

            <express>
               <name> E1 </name>
               <kind> VENT_source </kind>
               <text line="1"> "1000*sin(2*pi*t)" </text>
            </express>

        with the value referencing it via <source type="express"> E1
        </source>.  One <express> per function (siblings).
        """
        if not name or not text:
            return False
        el = None
        for e in self.root.findall('express'):
            n = _first(e, 'name')
            if n is not None and (n.text or '').strip() == name:
                el = e
                break
        if el is None:
            el = ET.Element('express')
            el.tail = '\n   '
            aset = _first(self.root, 'analysis_set')
            if aset is not None:
                children = list(self.root)
                self.root.insert(children.index(aset), el)
            else:
                self.root.append(el)
        for tag, value in (('name', name), ('kind', kind)):
            c = _first(el, tag)
            if c is None:
                c = ET.SubElement(el, tag)
                c.tail = '\n      '
            set_text(c, value)
        t = _first(el, 'text')
        if t is None:
            t = ET.SubElement(el, 'text')
            t.tail = '\n   '
        t.attrib['line'] = '1'
        set_text(t, ' "' + text + '" ')
        return True

    def express_list(self) -> list[tuple[str, str, str]]:
        """All <express> functions as (name, kind, formula)."""
        out = []
        for e in self.root.findall('express'):
            n = _first(e, 'name')
            k = _first(e, 'kind')
            t = _first(e, 'text')
            name = (n.text or '').strip() if n is not None else ''
            kind = (k.text or '').strip() if k is not None else ''
            formula = (t.text or '').strip().strip('"') \
                if t is not None else ''
            if name:
                out.append((name, kind, formula))
        return out

    def express_referenced_by(self, name: str) -> list[str]:
        """Value names whose ``<source type="express">`` is ``name``."""
        out: list[str] = []
        for v in self.root.iter('value'):
            src = _first(v, 'source')
            if src is None or src.attrib.get('type') != 'express':
                continue
            if (src.text or '').strip() != name:
                continue
            n = _first(v, 'name')
            if n is not None and (n.text or '').strip():
                out.append((n.text or '').strip())
        return out

    def delete_value(self, name: str) -> bool:
        """Remove a ``<value>`` and every ``<condition>`` referencing it."""
        el = self.find_value(name)
        if el is None:
            return False
        for c in list(self.conditions()):
            v = _first(c, 'value')
            if v is not None and (v.text or '').strip() == name:
                self.root.remove(c)
        self.root.remove(el)
        return True

    def delete_express(self, name: str, *, cascade: bool = False) -> bool:
        """Delete an ``<express>`` computing function.

        Refuses (returns ``False``) while values still reference it through
        ``<source type="express">`` unless ``cascade=True``, which removes
        the referencing values (and their conditions) as well.
        """
        el = None
        for e in self.root.findall('express'):
            n = _first(e, 'name')
            if n is not None and (n.text or '').strip() == name:
                el = e
                break
        if el is None:
            return False
        refs = self.express_referenced_by(name)
        if refs and not cascade:
            return False
        for r in refs:
            self.delete_value(r)
        self.root.remove(el)
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

    def ensure_polygon_body_files(self) -> int:
        """AM-3: register polygon (STL) parts in ``<body_files>`` so the
        STpre relay mesher receives them (STpre's own STL part cab layout
        carries body_files entries; our import layout omitted them).
        Returns the number of entries added."""
        added = 0
        for p in self.parts():
            if (p.kind or "").lower() != "polygon":
                continue
            f_el = _first(p.elem, "file")
            ref = (f_el.text or "").strip() if f_el is not None else ""
            if not ref or not ref.lower().endswith(".stl"):
                continue
            if self.add_body_file(ref, file_type="stl"):
                added += 1
        return added

    # -- region pairs (Thermal Boundary Between Parts) --------------------

    def region_pairs(self) -> list[tuple[str, str, str]]:
        """``(pair_name, part1, part2)`` for ``<region type="PartPair">``."""
        out: list[tuple[str, str, str]] = []
        for reg in self.root.iter("region"):
            if reg.attrib.get("type") != "PartPair":
                continue
            n = _first(reg, "name")
            p1 = _first(reg, "part1")
            p2 = _first(reg, "part2")
            name = (n.text or "").strip() if n is not None and n.text else ""
            if not name:
                continue
            out.append((
                name,
                (p1.text or "").strip() if p1 is not None and p1.text else "",
                (p2.text or "").strip() if p2 is not None and p2.text else "",
            ))
        return out

    def find_region_pair(self, name: str) -> Optional[ET.Element]:
        for reg in self.root.iter("region"):
            if reg.attrib.get("type") != "PartPair":
                continue
            n = _first(reg, "name")
            if n is not None and (n.text or "").strip() == name:
                return reg
        return None

    def upsert_region_pair(self, name: str, part1: str, part2: str) -> bool:
        """Create or update a PartPair region used by between-parts BCs."""
        if not name or not part1 or not part2:
            return False
        reg = self.find_region_pair(name)
        if reg is None:
            reg = ET.Element("region")
            reg.attrib["type"] = "PartPair"
            reg.tail = "\n   "
            self.root.append(reg)
        for tag, text in (("name", name), ("part1", part1), ("part2", part2)):
            c = _first(reg, tag)
            if c is None:
                c = ET.SubElement(reg, tag)
                c.tail = "\n      "
            set_text(c, text)
        return True

    def remove_region_pair(self, name: str) -> bool:
        for parent in self.root.iter():
            for child in list(parent):
                if child.tag != "region" \
                        or child.attrib.get("type") != "PartPair":
                    continue
                n = _first(child, "name")
                if n is not None and (n.text or "").strip() == name:
                    parent.remove(child)
                    return True
        return False

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
                        if self.mesh_coordinate() == "cylindrical":
                            import math
                            return (a[0], math.degrees(a[1]), a[2],
                                    b[0], math.degrees(b[1]), b[2])
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

    def root_block_extend(
            self
    ) -> Optional[tuple[tuple[float, float, float],
                        tuple[float, float, float]]]:
        """RootBlock ``extend_min`` / ``extend_max`` (mm) when present.

        STpre keeps the RootBlock cuboid glued to the computational domain;
        when a domain edit moves/sizes the cuboid, these per-axis extension
        values are preserved instead of being reset to zero.
        """
        mb = self.mesh_block()
        if mb is None:
            return None
        out = []
        for tag in ("extend_min", "extend_max"):
            el = _first(mb, tag)
            if el is None or not el.text:
                return None
            try:
                vals = tuple(float(x.strip()) for x in el.text.split(",")[:3])
            except ValueError:
                return None
            if len(vals) != 3:
                return None
            out.append(vals)
        return (out[0], out[1])

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
            coordinate: Optional[str] = None,
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
        mb0 = self.mesh_block()
        lim_el = _first(blk0, "limit") if blk0 is not None else None
        if lim_el is None and mb0 is not None:
            lim_el = _first(mb0, "limit")
        thr = threshold or self._parse_vec3(lim_el) or (0.1, 0.1, 0.1)
        # Internal geometric ratio lives in mesh_block/divide_ratio1;
        # mesh_control/divide_ratio2 is the *external* ratio and must not
        # be written into the internal field (was clobbered to 1.1 when
        # Domain/RootBlock was edited after gridding).
        rat = ratio or self._parse_vec3(
            _first(mb0, "divide_ratio1") if mb0 is not None else None
        ) or (1.0, 1.0, 1.0)
        rat_ext = self._parse_vec3(
            _first(mc0, "divide_ratio2") if mc0 is not None else None)
        std_len = self._parse_vec3(
            _first(mb0, "divide_length") if mb0 is not None else None)

        self.set_mesh(
            axes, unit=unit, domain_min=mn, domain_max=mx,
            threshold=thr, ratio=rat,
            standard_length=std_len or (0.5, 0.5, 0.5),
            ratio_external=rat_ext,
            coordinate=coordinate or self.mesh_coordinate())
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

    def mesh_coordinate(self) -> str:
        """'cylindrical' when the mesh_block uses r/t/z tables.

        STpre marks cylindrical blocks with <r>/<t>/<z> axes and
        <system> 1 </system> (theta stored in radians).
        """
        mb = self.mesh_block()
        if mb is None:
            return "cartesian"
        sys_el = _first(mb, "system")
        if _first(mb, "r") is not None or (
                sys_el is not None and (sys_el.text or "").strip() == "1"):
            return "cylindrical"
        return "cartesian"

    def mesh_axes(self) -> dict[str, list[float]]:
        """Coordinates per axis from ``mesh_block``.

        Cylindrical blocks store r (mm) / t (radian) / z (mm); those are
        mapped back to x/y/z with theta converted to degrees so all
        downstream consumers keep the internal degrees convention.
        """
        mb = self.mesh_block()
        if mb is None:
            return {}
        cyl = self.mesh_coordinate() == "cylindrical"
        tags = ("r", "t", "z") if cyl else ("x", "y", "z")
        out: dict[str, list[float]] = {}
        for axis, tag in zip("xyz", tags):
            el = _first(mb, tag)
            if el is None:
                continue
            vals: list[float] = []
            for g in _children(el, "g"):
                text = (g.text or "").split(",")[0].strip()
                try:
                    v = float(text)
                except ValueError:
                    continue
                if cyl and axis == "y":
                    import math
                    v = math.degrees(v)
                vals.append(v)
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
        """``(coordinate, mark)`` pairs of one mesh_block axis.

        For cylindrical blocks the theta values are converted from
        radians (storage) to degrees (internal convention).
        """
        mb = self.mesh_block()
        if mb is None or axis not in "xyz":
            return []
        cyl = self.mesh_coordinate() == "cylindrical"
        tag = {"x": "r", "y": "t", "z": "z"}[axis] if cyl else axis
        el = _first(mb, tag)
        out: list[tuple[float, str]] = []
        if el is None:
            return out
        for g in _children(el, "g"):
            parts = (g.text or "").split(",")
            try:
                val = float(parts[0].strip())
            except (ValueError, IndexError):
                continue
            if cyl and axis == "y":
                import math
                val = math.degrees(val)
            mark = parts[1].strip().upper() if len(parts) > 1 else "N"
            out.append((val, mark or "N"))
        return out

    def set_mesh_axis(self, axis: str, entries: list[tuple[float, str]],
                      unit: str = "mm") -> bool:
        """Rewrite one mesh_block axis from ``(coordinate, mark)`` pairs.

        Cylindrical blocks store r (mm) / t (radian) / z (mm): the theta
        values are converted degrees -> radians on write.
        """
        mb = self.mesh_block()
        if mb is None or axis not in ("x", "y", "z"):
            return False
        cyl = self.mesh_coordinate() == "cylindrical"
        tag = {"x": "r", "y": "t", "z": "z"}[axis] if cyl else axis
        el = _first(mb, tag)
        if el is None:
            el = ET.SubElement(mb, tag)
            el.tail = "\n   "
        el.attrib["num"] = str(len(entries))
        el.attrib["unit"] = "radian" if cyl and axis == "y" else unit
        for child in list(el):
            el.remove(child)
        for i, (val, mark) in enumerate(entries, start=1):
            if cyl and axis == "y":
                import math
                val = math.radians(val)
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

    def mesh_control(self) -> Optional[ET.Element]:
        return _first(self.root, "mesh_control")

    @staticmethod
    def _parse_vec3(el: Optional[ET.Element]
                    ) -> Optional[tuple[float, float, float]]:
        if el is None or not el.text:
            return None
        try:
            vals = [float(x) for x in el.text.split(",")[:3]]
        except ValueError:
            return None
        return tuple(vals) if len(vals) == 3 else None

    def _block_element(self, name: str) -> Optional[ET.Element]:
        """Nested ``mesh_control/block`` element by name (STpre multiblock)."""
        mc = self.mesh_control()
        root = _first(mc, "block") if mc is not None else None

        def find(el: ET.Element) -> Optional[ET.Element]:
            if (el.attrib.get("name") or "").strip() == name:
                return el
            for c in _children(el, "block"):
                r = find(c)
                if r is not None:
                    return r
            return None

        return find(root) if root is not None else None

    def mesh_blocks(self, parent: Optional[str] = None) -> list[dict]:
        """Multiblock tree from ``mesh_control`` (RootBlock + children)."""
        mc = self.mesh_control()
        root = _first(mc, "block") if mc is not None else None
        if root is None:
            return []

        def parse(el: ET.Element) -> dict:
            def txt(tag: str) -> str:
                e = _first(el, tag)
                return (e.text or "").strip() if e is not None and e.text \
                    else ""
            sub = _first(el, "subblock")
            return {
                "name": (el.attrib.get("name") or "").strip(),
                "kind": txt("kind") or "any",
                "min": self._parse_vec3(_first(el, "min")),
                "max": self._parse_vec3(_first(el, "max")),
                "limit": self._parse_vec3(_first(el, "limit")),
                "grid": txt("grid"),
                "divide": ((sub.attrib.get("divide") or "")
                           if sub is not None else "") or "1,1,1",
                "ratio": (sub.attrib.get("ratio") or "")
                if sub is not None else "",
                "children": [parse(c) for c in _children(el, "block")],
            }

        tree = parse(root)
        if parent is None:
            return [tree]

        def find(d: dict) -> Optional[dict]:
            if d["name"] == parent:
                return d
            for c in d["children"]:
                r = find(c)
                if r is not None:
                    return r
            return None

        found = find(tree)
        return [found] if found is not None else []

    def add_child_block(self, name: str, parent: str = "RootBlock",
                        xyz_min=None, xyz_max=None, *,
                        length=(0.5, 0.5, 0.5),
                        ratio=(1.0, 1.0, 1.0),
                        limit=(0.1, 0.1, 0.1)) -> bool:
        """Append a nested child ``<block>`` (STpre multiblock layout)."""
        parent_el = self._block_element(parent)
        if parent_el is None or self._block_element(name) is not None:
            return False
        if xyz_min is None or xyz_max is None:
            pmin = self._parse_vec3(_first(parent_el, "min"))
            pmax = self._parse_vec3(_first(parent_el, "max"))
            if pmin is None or pmax is None:
                return False
            xyz_min = tuple(a + 0.25 * (b - a) for a, b in zip(pmin, pmax))
            xyz_max = tuple(a + 0.75 * (b - a) for a, b in zip(pmin, pmax))
        child = ET.SubElement(parent_el, "block")
        child.attrib["name"] = name
        child.tail = "\n      "
        for tag, text, attrs in (
                ("kind", "any", {}),
                ("min", self._vec_text(tuple(xyz_min)), {"unit": "mm"}),
                ("max", self._vec_text(tuple(xyz_max)), {"unit": "mm"}),
                ("limit", self._vec_text(tuple(limit)), {"unit": "mm"}),
                ("grid", "2,2,2", {}),
        ):
            e = ET.SubElement(child, tag)
            e.text = f" {text} "
            e.tail = "\n        "
        sub = ET.SubElement(child, "subblock")
        sub.attrib["divide"] = self._vec_text(tuple(length))
        sub.tail = "\n        "
        area = ET.SubElement(sub, "area")
        area.attrib["no"] = "0"
        area.tail = "\n          "
        for tag in ("valid", "min", "max"):
            e = ET.SubElement(area, tag)
            e.text = " "
            e.tail = "\n            "
        set_text(_first(area, "valid"), "T")
        set_text(_first(area, "min"), self._vec_text(tuple(xyz_min)))
        set_text(_first(area, "max"), self._vec_text(tuple(xyz_max)))
        # ratio is stored on the subblock for finer control (cab extension
        # keeps STpre's divide attribute as the standard length).
        if ratio != (1.0, 1.0, 1.0):
            sub.attrib["ratio"] = self._vec_text(tuple(ratio))
        return True

    def update_child_block_grid(self, name: str, counts) -> bool:
        el = self._block_element(name)
        if el is None:
            return False
        self._mesh_child(el, "grid", ",".join(str(int(c)) for c in counts))
        return True

    def block_param(self, name: str, tag: str, default: str = "") -> str:
        el = self._block_element(name)
        e = _first(el, tag) if el is not None else None
        return (e.text or "").strip() if e is not None and e.text else default

    def set_block_param(self, name: str, tag: str, text: str,
                        unit: Optional[str] = None) -> bool:
        el = self._block_element(name)
        if el is None:
            return False
        e = _first(el, tag)
        if e is None:
            e = ET.SubElement(el, tag)
            e.tail = "\n      "
        set_text(e, text)
        if unit:
            e.attrib["unit"] = unit
        return True

    def mesh_control_value(self, tag: str) -> Optional[str]:
        mc = _first(self.root, "mesh_control")
        el = _first(mc, tag) if mc is not None else None
        return (el.text or "").strip() if el is not None and el.text else None

    def set_mesh_control_value(self, tag: str, text: str) -> bool:
        mc = _first(self.root, "mesh_control")
        if mc is None:
            # Lightweight stub so flags (e.g. domain_coordinate) can be
            # persisted before a full Gridding run creates the block tree.
            mc = ET.Element("mesh_control")
            mc.tail = "\n"
            self.root.append(mc)
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

    def set_part_mesh_fine_divide(self, name: str, value: str) -> bool:
        """Per-part fine subdivision ``<mesh_fine_divide>x,y,z</...>``.

        Official samples: exA02-2b fan ``2,0,0`` / exA05-2 fan ``0,5,0``.
        Empty value removes the element (STpre default = no fine mesh).
        """
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "mesh_fine_divide")
        if not value.strip():
            if c is not None:
                el.remove(c)
            return True
        if c is None:
            c = ET.SubElement(el, "mesh_fine_divide")
            c.tail = "\n         "
        set_text(c, value.strip())
        return True

    def set_part_divide(self, name: str, value: str) -> bool:
        """Radial subdivision ``<divide>N</...>`` (cylinder parts, 32/48)."""
        el = self.find_part(name)
        if el is None:
            return False
        c = _first(el, "divide")
        if not value.strip():
            if c is not None:
                el.remove(c)
            return True
        if c is None:
            c = ET.SubElement(el, "divide")
            c.tail = "\n         "
        set_text(c, value.strip())
        return True

    def elements(self) -> Optional[ET.Element]:
        return _first(self.root, "element")

    def part_boxes(self, part_name: str) -> list[list[int]]:
        """i/j/k index boxes (6-int) of a part from the ``element`` section.

        Official stores 9-tuples ``i1,i2,j1,j2,k1,k2,0,1,1``; the trailing
        subdivision counts are exposed via :meth:`part_element_lists`.
        """
        return [b[:6] for b in self.part_element_lists(part_name)
                if len(b) >= 6]

    def part_element_lists(self, part_name: str) -> list[list[int]]:
        """Raw 9-int body lists of a part (full fidelity roundtrip)."""
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
            out: list[list[int]] = []
            for lst in _children(body, "list"):
                out.append([int(x) for x in lst.text.split(",")])
            return out
        return []

    def part_face_boxes(self, part_name: str) -> list[list[int]]:
        """Raw 9-int face lists of a part.

        Format (exA01-1 human-proofed): ``code,i1,i2,j1,j2,k1,k2,s1,s2``
        where code = ±(2·axis+1) face id (−1= x-min, +1= x-max, −3/ +3= y,
        −5/+5= z) and s1/s2 are the face-local subdivision counts.
        """
        el = self.elements()
        if el is None:
            return []
        for parts in _children(el, "parts"):
            if parts.attrib.get("name", "") != part_name:
                continue
            out: list[list[int]] = []
            for face in _children(parts, "face"):
                for lst in _children(face, "list"):
                    out.append([int(x) for x in lst.text.split(",")])
            return out
        return []

    # -- FEM 单元数据（R9-A, COM-probed 2026-08-16）------------------------
    #
    # tools/probe_fem.py 实证（结果存 tools/probe_work/fem_probe.json），
    # STpre 2025.2 的 Edit→FEM Conversion（Model.CreateFEM(length, scale,
    # edge)，length=单元尺寸 mm、scale/edge="T"/"F"）落盘格式：
    #
    # 1) 主 XML 新增 FEM 部件（原实体件保留不删）：
    #     <parts type="mesh_body">
    #        <name> fem_<原名> </name>
    #        <attribute> fe-model </attribute>
    #        <color> 191,191,191,255 </color>
    #        <mode> global </mode> ... <layer> 1 </layer>
    #        <rad_group_num> 0 </rad_group_num>
    #        <mesh_divide> none </mesh_divide>
    #        <heat_balance> F,F </heat_balance>
    #        <VF_balance> F </VF_balance>
    #        <file> xfem </file>
    #     </parts>
    # 2) <body_files unit="m"> 追加 <file type="fem"> _<工程>_all.xfem
    #    </file>，cab 包内新增同名成员（全部 FEM 部件的单元数据）。
    # 3) .xfem 成员为 XML（UTF-8 BOM + CRLF）：
    #     <femodel>
    #        <version> 14 </version>
    #        <unit> m,C </unit>
    #        <model name="fem_<原名>" temp_type="0">
    #           <node num="N">
    #              <n no="1" org="1"> x,y,z,flag </n> ...
    #           </node>
    #           <element num="M">
    #              <e no="1" kind="4"> n1,n2,n3,n4 </e> ...
    #           </element>
    #        </model>
    #     </femodel>
    #    节点坐标为米（unit=m）；kind="4" = 4 节点四面体（solid）。
    #    壳/六面体 kind：F6 活体探针（tools/probe_fem_kinds.py，
    #    见 docs/fem_kind_probe.md）证实 —— CreateFEM 对实体件（立方体
    #    length=2.0/1.0、圆柱）只写 kind="4"；Panel 件不产生 .xfem（无
    #    壳单元输出）；CreateHexaModel 的 COM 参数表未解析成功。据此按
    #    §22.0 B 级定档：STpre 无壳/六面体 FEM 输出路径，本仓只写 tet4
    #    与官方行为一致（非能力缺口）。
    # 4) .s 文件无 FEM 段（单元数据只在 .xfem；.s 的 VFEM 是求解器
    #    开关，与 pre 数据无关）。

    _FEM_PART_TYPE = "mesh_body"

    def fem_parts(self) -> list[str]:
        """All FEM parts (``type="mesh_body"``) in document order."""
        out: list[str] = []

        def collect(parent: ET.Element) -> None:
            for el in _children(parent, "parts"):
                if el.attrib.get("type") != self._FEM_PART_TYPE:
                    continue
                n = _first(el, "name")
                if n is not None and n.text:
                    out.append(n.text.strip())

        collect(self.root)
        for grp in self.groups():
            collect(grp)
        return out

    def part_fem(self, name: str,
                 xfem_data: Optional[bytes] = None) -> Optional[dict]:
        """Read the FEM element data of part ``name`` (R9-A).

        Returns ``None`` when the part is missing or is not a
        ``type="mesh_body"`` FEM part.  Otherwise a dict with the part
        metadata (``name``/``file``) and, when the cab's ``.xfem`` member
        bytes are supplied via ``xfem_data``, the node coordinates
        (metres, list index 0 == ``<n no="1">``) and the elements
        (``(kind, n1, ..., nk)`` 1-based node numbers); without
        ``xfem_data`` those two keys are ``None`` (unit data lives in a
        separate cab member, not the main XML).
        """
        el = self.find_part(name)
        if el is None or el.attrib.get("type") != self._FEM_PART_TYPE:
            return None
        f = _first(el, "file")
        out = {
            "name": name,
            "type": self._FEM_PART_TYPE,
            "file": (f.text or "").strip() if f is not None and f.text
                    else "",
            "nodes": None,
            "elements": None,
            "element_kinds": None,
        }
        if xfem_data is None:
            return out
        for mdl in parse_femodel(xfem_data):
            if mdl["name"] != name:
                continue
            out["nodes"] = mdl["nodes"]
            out["elements"] = mdl["elements"]
            out["element_kinds"] = mdl["element_kinds"]
            break
        return out

    def set_part_fem(self, name: str, fem: Optional[dict],
                     xfem_member: Optional[str] = None) -> bool:
        """Create/update (dict) or remove (``None``) a FEM part entry.

        ``fem`` may carry ``nodes``/``elements`` (see :func:`femodel_bytes`
        for the unit format); only the main-XML side is written here —
        the ``.xfem`` member itself must be packed into the cab archive
        by the caller (实证存储位置).  ``xfem_member`` defaults to
        ``_<project>_all.xfem`` and is registered under
        ``<body_files><file type="fem">``.
        """
        if fem is None:
            return name in self.fem_parts() and self.delete_part(name)
        if self.find_part(name) is not None:
            return False
        parts = ET.Element("parts")
        parts.attrib["type"] = self._FEM_PART_TYPE
        fields = [
            ("name", name),
            ("attribute", "fe-model"),
            ("color", "191,191,191,255"),
            ("mode", "global"),
            ("visible_count", "1"),
            ("tree_expand", "F"),
            ("layer", "1"),
            ("rad_group_num", "0"),
            ("mesh_divide", "none"),
            ("heat_balance", "F,F"),
            ("VF_balance", "F"),
            ("file", "xfem"),
        ]
        for tag, value in fields:
            e = ET.SubElement(parts, tag)
            e.text = f" {value} "
            e.tail = "\n         "
        parts.tail = "\n      "
        self.root.append(parts)
        # 注册 .xfem 数据成员引用（body_files type="fem"）
        member = xfem_member or f"_{self.project_name or 'project'}_all.xfem"
        bf = _first(self.root, "body_files")
        if bf is None:
            bf = ET.Element("body_files")
            bf.attrib["unit"] = "m"
            bf.text = "\n      "
            bf.tail = "\n"
            self.root.append(bf)
        listed = any(c.attrib.get("type") == "fem"
                     and (c.text or "").strip() == member
                     for c in _children(bf, "file"))
        if not listed:
            e = ET.SubElement(bf, "file")
            e.attrib["type"] = "fem"
            e.text = f" {member} "
            e.tail = "\n   "
        return True

    def analysis_names(self) -> list[str]:
        """Names of ``element/analysis`` blocks (computational domains)."""
        el = self.elements()
        if el is None:
            return []
        return [a.attrib.get("name", "") for a in _children(el, "analysis")
                if a.attrib.get("name")]

    def analysis_boxes(self, name: Optional[str] = None) -> list[list[int]]:
        """Body index boxes (6-int) from ``element/analysis`` (Domain occupancy).

        Official stores 9-tuples ``i1,i2,j1,j2,k1,k2,0,1,1``; the trailing
        subdivision counts are constant across samples and truncated here
        (same contract as :meth:`part_boxes`).
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
                vals = [int(x) for x in lst.text.split(",")]
                boxes.append(vals[:6])
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

    def add_body_file(self, name: str, unit: str = 'm',
                      file_type: str = 'xt') -> bool:
        # Register an additional body member; no-op when already listed.
        bf = _first(self.root, 'body_files')
        if bf is None:
            bf = ET.Element('body_files')
            bf.attrib['unit'] = unit
            bf.text = '\n   '
            bf.tail = '\n'
            self.root.append(bf)
        for c in _children(bf, 'file'):
            if c.attrib.get('type', 'xt') == file_type \
                    and (c.text or '').strip() == name:
                return False
        e = ET.SubElement(bf, 'file')
        e.attrib['type'] = file_type
        e.text = f' {name} '
        e.tail = '\n   '
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
                 ratio: tuple[float, float, float] = (1.0, 1.0, 1.0),
                 standard_length: tuple[float, float, float] = (
                     0.5, 0.5, 0.5),
                 ratio_external: Optional[tuple[float, float, float]] = None,
                 detection: int = 1,
                 method: int = 1,
                 element_max: int = 100_000_000,
                 part_min: Optional[tuple[float, float, float]] = None,
                 part_max: Optional[tuple[float, float, float]] = None,
                 coordinate: str = "cartesian",
                 ) -> None:
        """Write ``<mesh_control>`` + ``<mesh_block>`` from generated axes.

        ``coordinate="cylindrical"`` writes the STpre cylindrical block
        form (COM probe 2026-08-15): ``<system> 1 </system>``, min/max
        ``r1,0,z1`` / ``r2,t2_rad,z2`` and ``<r>/<t unit=radian>/<z>``
        axis tables; the passed axes keep theta in degrees internally.
        """
        cyl = coordinate == "cylindrical"
        import math
        dmin = (float(domain_min[0]), float(domain_min[1]),
                float(domain_min[2]))
        dmax = (float(domain_max[0]), float(domain_max[1]),
                float(domain_max[2]))
        if cyl:
            dmin = (dmin[0], math.radians(dmin[1]), dmin[2])
            dmax = (dmax[0], math.radians(dmax[1]), dmax[2])
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
                    ("divide_ratio2", self._vec_text(
                        ratio_external if ratio_external is not None
                        else ratio)),
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
        self._mesh_child(block, "min", self._vec_text(dmin),
                         {"unit": unit})
        self._mesh_child(block, "max", self._vec_text(dmax),
                         {"unit": unit})
        self._mesh_child(block, "limit", self._vec_text(threshold),
                         {"unit": unit})
        self._mesh_child(block, "grid", grid_text)
        self._mesh_child(mc, "select_vertex", str(detection))
        self._mesh_child(mc, "divide_method", str(method))
        self._mesh_child(
            mc, "divide_ratio2",
            self._vec_text(ratio_external if ratio_external is not None
                           else ratio))
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
                ("system", "1" if cyl else "0", {}),
                ("visible", "T", {}),
                ("tree_expand", "T", {}),
                ("min", self._vec_text(dmin), {"unit": unit}),
                ("max", self._vec_text(dmax), {"unit": unit}),
                ("extend_min", "0,0,0", {"unit": unit}),
                ("extend_max", "0,0,0", {"unit": unit}),
                ("limit", self._vec_text(threshold), {"unit": unit}),
                ("divide_length", self._vec_text(standard_length),
                 {"unit": unit}),
                ("divide_ratio1", self._vec_text(ratio), {}),
        ):
            self._mesh_child(mb, tag, text, attrs)
        axis_tags = ("r", "t", "z") if cyl else ("x", "y", "z")
        stale = ("x", "y", "z") if cyl else ("r", "t", "z")
        for stale_tag in stale:
            stale_el = _first(mb, stale_tag)
            if stale_el is not None:
                mb.remove(stale_el)
        for axis, tag in zip("xyz", axis_tags):
            el = _first(mb, tag)
            if el is None:
                el = ET.SubElement(mb, tag)
                el.tail = "\n   "
            el.attrib["num"] = str(len(axes.get(axis, [])))
            el.attrib["unit"] = ("radian" if cyl and axis == "y"
                                  else unit)
            for child in list(el):
                el.remove(child)
            vals = axes.get(axis, [])
            for i, v in enumerate(vals, start=1):
                if cyl and axis == "y":
                    v = math.radians(v)
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


# --------------------------------------------------------------------------
# FEM 单元模型（R9-A）— .xfem 成员解析 / 生成 / 离线六面体网格
# 存储格式见 StpreModel.part_fem 上方的实证注释（2026-08-16 COM 探针）。
# --------------------------------------------------------------------------

#: kind="4" = 4 节点四面体（solid，COM 探针实证的唯一 kind）
FEM_KIND_TET4 = 4


def parse_femodel(data: bytes) -> list[dict]:
    """解析 .xfem 成员 → 每个 ``<model>`` 一个 dict。

    返回 ``[{name, temp_type, nodes, elements, element_kinds}]``：
    * ``nodes``: ``[(x, y, z), ...]`` 米制坐标，索引 0 对应
      ``<n no="1">``（1-based 节点号 = 索引 + 1）；
    * ``elements``: ``[(kind, n1, ..., nk), ...]``，节点号为 1-based；
    * ``element_kinds``: 出现过的 kind 集合（int 列表）。
    """
    root = ET.fromstring(data.decode("utf-8"))
    out: list[dict] = []
    for mdl in root.iter("model"):
        nodes: list[tuple[float, float, float]] = []
        node_el = _first(mdl, "node")
        if node_el is not None:
            for n in _children(node_el, "n"):
                if not n.text:
                    continue
                try:
                    xyz = tuple(float(v) for v in
                                n.text.split(",")[:3])
                except ValueError:
                    continue
                if len(xyz) == 3:
                    nodes.append(xyz)  # type: ignore[arg-type]
        elements: list[tuple[int, ...]] = []
        kinds: set[int] = set()
        el_el = _first(mdl, "element")
        if el_el is not None:
            for e in _children(el_el, "e"):
                if not e.text:
                    continue
                try:
                    ids = [int(v) for v in e.text.split(",")
                           if v.strip()]
                except ValueError:
                    continue
                if not ids:
                    continue
                try:
                    kind = int(e.attrib.get("kind", FEM_KIND_TET4))
                except ValueError:
                    kind = FEM_KIND_TET4
                kinds.add(kind)
                elements.append((kind, *ids))
        out.append({
            "name": mdl.attrib.get("name", ""),
            "temp_type": mdl.attrib.get("temp_type", "0"),
            "nodes": nodes,
            "elements": elements,
            "element_kinds": sorted(kinds),
        })
    return out


def femodel_bytes(name: str, fem: dict, *, temp_type: str = "0") -> bytes:
    """按实证格式生成一个 ``<model>`` 的 .xfem 成员字节串。

    ``fem`` 取 ``{"nodes": [(x,y,z),...], "elements": [(kind,
    n1,...,nk),...]}``（坐标米制、节点号 1-based，与
    :func:`parse_femodel` 输出同构）。UTF-8 BOM + CRLF，与 STpre
    输出一致（version=14、unit=m,C）。
    """
    nodes = fem.get("nodes") or []
    elements = fem.get("elements") or []
    lines = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<femodel>',
        '   <version> 14 </version>',
        '   <unit> m,C </unit>',
        f'   <model name="{name}" temp_type="{temp_type}">',
        f'      <node num="{len(nodes)}">',
    ]
    for i, (x, y, z) in enumerate(nodes, start=1):
        lines.append(f'         <n no="{i}" org="{i}"> '
                     f'{float(x):.15g},{float(y):.15g},'
                     f'{float(z):.15g},0 </n>')
    lines.append('      </node>')
    lines.append(f'      <element num="{len(elements)}">')
    for i, el in enumerate(elements, start=1):
        kind = el[0]
        ids = ",".join(str(v) for v in el[1:])
        lines.append(f'         <e no="{i}" kind="{kind}"> {ids} </e>')
    lines.append('      </element>')
    lines.append('   </model>')
    lines.append('</femodel>')
    return b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8") + b"\r\n"


def build_fem_delaunay(points_m, *, min_nodes: int = 4):
    # Offline tetrahedral FEM mesh from an arbitrary point cloud (metres):
    # scipy Delaunay over the part tessellation points.  For a surface
    # tessellation the tetrahedralization fills the convex volume;
    # degenerate inputs return None (caller falls back to build_fem_hexa).
    import numpy as np
    from scipy.spatial import Delaunay
    pts = np.asarray(points_m, dtype=float).reshape(-1, 3)
    if len(pts) < 4:
        return None
    uniq = np.unique(np.round(pts, 9), axis=0)
    if len(uniq) < 4:
        return None
    span = uniq.max(0) - uniq.min(0)
    if min(span) <= 1e-12:
        return None
    tri = Delaunay(uniq)
    nodes = [tuple(float(v) for v in u) for u in uniq]
    elements = [(FEM_KIND_TET4,) + tuple(int(i) + 1 for i in s)
                for s in tri.simplices]
    return {'nodes': nodes, 'elements': elements}

def build_fem_hexa(base, size, divide=(1, 1, 1)) -> dict:
    """离线生成：长方体 → 结构六面体网格 → Kuhn 6 四面体剖分。

    ``base``/``size`` 为 mm（与部件 ``<base>``/``<size>`` 同单位），
    ``divide`` 为每轴分割数。节点坐标转米输出（实证 unit=m），
    单元全部为实证的 kind=4 四面体（六面体的 kind 值未实证，故以
    四面体剖分对齐 STpre 输出结构）。返回与 :func:`parse_femodel`
    单 model 同构的 dict。
    """
    nx, ny, nz = (max(1, int(v)) for v in divide)
    bx, by, bz = (float(v) for v in base)
    sx, sy, sz = (float(v) for v in size)
    # 结构网格节点（相邻六面体共享节点，与 STpre 输出一致）
    nodes: list[tuple[float, float, float]] = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append((
                    (bx + sx * i / nx) / 1000.0,
                    (by + sy * j / ny) / 1000.0,
                    (bz + sz * k / nz) / 1000.0,
                ))

    def vid(i, j, k) -> int:
        return k * (ny + 1) * (nx + 1) + j * (nx + 1) + i + 1  # 1-based

    # 一个六面体的 Kuhn 剖分：沿体对角线 v0-v6 切 6 个四面体
    _TETS = ((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6),
             (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6))
    _HEX_V = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
              (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
    elements: list[tuple[int, ...]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                corner = [vid(i + dv[0], j + dv[1], k + dv[2])
                          for dv in _HEX_V]
                for t in _TETS:
                    elements.append(
                        (FEM_KIND_TET4, *(corner[v] for v in t)))
    return {"nodes": nodes, "elements": elements}
