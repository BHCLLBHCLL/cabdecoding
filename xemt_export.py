"""P3: EMT (.xemt) exporter.

``.xemt`` is the material/part mapping file that scSTREAM Pre writes
automatically together with the S file (see CAB_FORMAT_SPEC.md §7). All data
comes from the cab's two XML members.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from cabxml import PropertyModel, StpreModel


def build_emt(model: StpreModel, props: PropertyModel) -> str:
    """Render the EMT document (no BOM, CRLF line endings like the sample)."""
    materials = _ordered_materials(model, props)
    fluid = model.analysis_region()
    from cabxml import _first
    fluid_name = ""
    fluid_mat = 1
    if fluid is not None:
        name_el = _first(fluid, "name")
        fluid_name = name_el.text.strip() if name_el is not None else ""
        prop_el = _first(fluid, "property")
        fluid_prop = prop_el.text.strip() if prop_el is not None else ""
        fluid_mat = materials.get(fluid_prop, 1)

    lines = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        "<!-- date/time : generated from cab -->",
        "<EMT>",
        '   <Version no="2023"/>',
        "   <Material>",
    ]
    for i, (name, _) in enumerate(materials.items(), start=1):
        lines.append(f'      <mat no="{i}" name="{name}"/>')
    lines.append("   </Material>")
    lines.append("   <Parts>")
    lines.append(f'      <fluid no="1" name="{fluid_name}" mat="{fluid_mat}"/>')
    lines.append(f'      <part no="1" name="{fluid_name}" mat="{fluid_mat}"/>')
    no = 1
    for grp in model.groups():
        gname_el = _first(grp, "name")
        gname = gname_el.text.strip() if gname_el is not None else ""
        lines.append(f'      <group name="{gname}" expand="T">')
        for parts_el in grp:
            if parts_el.tag != "parts":
                continue
            no += 1
            name_el = _first(parts_el, "name")
            name = name_el.text.strip() if name_el is not None else ""
            prop_el = _first(parts_el, "property")
            mat = materials.get(prop_el.text.strip(), 1) \
                if prop_el is not None else 1
            lines.append(
                f'         <part no="{no}" name="{name}" mat="{mat}"/>')
        lines.append("      </group>")
    lines.append("   </Parts>")
    lines.append("</EMT>")
    return "\r\n".join(lines) + "\r\n"


def _ordered_materials(model: StpreModel,
                       props: PropertyModel) -> dict[str, int]:
    """Materials referenced by the project, numbered in property-XML group
    order (matches the official EMT / S-file PROPERTY numbering)."""
    used = _used_material_names(model)
    order: dict[str, int] = {}
    for grp in props.groups():
        from cabxml import _first, _children
        gtype = _first(grp, "type")
        is_fluid = gtype is not None and "fluid" in gtype.text.lower()
        for ent in _children(grp, "entry"):
            name_el = _first(ent, "name")
            name = name_el.text.strip() if name_el is not None else ""
            if name in used and name not in order:
                order[name] = len(order) + 1
    return order


def _used_material_names(model: StpreModel) -> set[str]:
    names: set[str] = set()
    for p in model.parts():
        if p.property:
            names.add(p.property)
    ar = model.analysis_region()
    if ar is not None:
        from cabxml import _first
        prop = _first(ar, "property")
        if prop is not None and prop.text:
            names.add(prop.text.strip())
    return names


# --------------------------------------------------------------------------
# FMT-2: EMT import (.xemt) — parse the manifest and apply materials


def parse_emt(raw: bytes | str) -> dict:
    """Parse an EMT (.xemt) document into a manifest dict.

    EMT carries no geometry — it is the material/part mapping companion of
    the S file.  Returns ``{"version", "materials": {no: name}, "fluid",
    "parts": [...], "groups": [...]}`` where every part entry also carries
    the resolved material *name* (``mat`` no looked up in ``Material``).
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    root = ET.fromstring(raw)
    materials: dict[int, str] = {}
    ver_el = root.find("Version")
    version = int(ver_el.get("no")) if ver_el is not None and ver_el.get("no") \
        else None
    mat_el = root.find("Material")
    if mat_el is not None:
        for mat in mat_el.findall("mat"):
            try:
                no = int(mat.get("no", "0"))
            except ValueError:
                continue
            materials[no] = mat.get("name", "")

    def _entry(el: ET.Element) -> dict:
        try:
            no = int(el.get("no", "0"))
        except ValueError:
            no = 0
        try:
            mat = int(el.get("mat", "1"))
        except ValueError:
            mat = 1
        return {"no": no, "name": el.get("name", ""), "mat": mat,
                "material": materials.get(mat, "")}

    fluid: dict = {}
    parts: list[dict] = []
    groups: list[dict] = []
    parts_el = root.find("Parts")
    if parts_el is not None:
        f_el = parts_el.find("fluid")
        if f_el is not None:
            fluid = _entry(f_el)
        for el in parts_el:
            if el.tag == "part":
                parts.append(_entry(el))
            elif el.tag == "group":
                members = [_entry(pe) for pe in el.findall("part")]
                groups.append({"name": el.get("name", ""),
                               "expand": el.get("expand", ""),
                               "parts": members})
                parts.extend(members)
    return {"version": version, "materials": materials, "fluid": fluid,
            "parts": parts, "groups": groups}


def apply_emt(model: StpreModel, props: PropertyModel, parsed: dict) -> dict:
    """Apply an EMT manifest to an open project (FMT-2).

    Materials are assigned by part-name match: each EMT part's resolved
    material *name* is written to the model part's ``<property>`` (and the
    analysis region for the fluid entry).  Names absent from the property
    library are reported, not applied — S-file PROPERTY would otherwise
    reference an undefined material.
    """
    from cabxml import _first, set_text
    known = set(props.material_names()) if props is not None else set()
    unknown: set[str] = set()
    applied = 0
    missing: list[str] = []

    def _assign(name: str, material: str) -> None:
        nonlocal applied
        if not name:
            return
        if material and material not in known:
            unknown.add(material)
            return
        if model.set_part_property(name, material):
            applied += 1
        else:
            missing.append(name)

    fluid = parsed.get("fluid") or {}
    fluid_name = fluid.get("name", "")
    ar = model.analysis_region()
    if ar is not None and fluid_name:
        material = fluid.get("material", "")
        if material and material not in known:
            unknown.add(material)
        else:
            prop_el = _first(ar, "property")
            if prop_el is None:
                from xml.etree.ElementTree import SubElement
                prop_el = SubElement(ar, "property")
            set_text(prop_el, material)
    for entry in parsed.get("parts", []):
        name = entry.get("name", "")
        if name and name == fluid_name:
            # EMT restates the region as part no=1; the fluid entry above
            # already covers it and it is not a model part.
            continue
        _assign(name, entry.get("material", ""))
    return {"applied": applied, "missing_parts": missing,
            "unknown_materials": sorted(unknown),
            "n_groups": len(parsed.get("groups", []))}
