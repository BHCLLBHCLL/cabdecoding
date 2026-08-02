"""P3: EMT (.xemt) exporter.

``.xemt`` is the material/part mapping file that scSTREAM Pre writes
automatically together with the S file (see CAB_FORMAT_SPEC.md §7). All data
comes from the cab's two XML members.
"""

from __future__ import annotations

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
