"""M2: computational domain editing (Edit -> Reset Computational Domain).

The domain is stored in ``<analysis_region type="cube">`` with ``<base>`` /
``<size>`` in mm (matching the cab XML).  This module:

- reads the current domain into a :class:`DomainSpec`;
- writes a :class:`DomainSpec` back (keeping the six face_list regions);
- creates a cube domain when the project has none (e.g. tr03);
- computes the world-space part bounds used by "CAD Data Size".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

import cab_vtk
from cabxml import StpreModel


@dataclass
class DomainSpec:
    """Computational domain parameters (coordinates in ``unit``)."""

    coordinate: str = "cartesian"   # cartesian | cylindrical | axial
    unit: str = "mm"
    xyz_min: tuple[float, float, float] = (-100.0, -100.0, -100.0)
    xyz_max: tuple[float, float, float] = (150.0, 300.0, 315.0)
    material: str = ""
    extend: tuple[float, float, float] = (0.0, 0.0, 0.0)  # legacy uniform
    extend_min: tuple[float, float, float] = (0.0, 0.0, 0.0)  # per-axis min
    extend_max: tuple[float, float, float] = (0.0, 0.0, 0.0)  # per-axis max
    auto_y_for_axial: bool = False
    name: str = "Domain(cuboid)"
    color: tuple[int, int, int, int] = (0, 255, 255, 255)  # RGBA 0-255
    monitor: bool = True                # Output temperature to Monitor
    initial_temperature: Optional[float] = None  # degC; None = keep as-is


def domain_from_xml(model: StpreModel) -> Optional[DomainSpec]:
    """Read the current domain; ``None`` when no ``<analysis_region>``."""
    ar = model.analysis_region()
    if ar is None:
        return None
    base = model.domain_base() or (0.0, 0.0, 0.0)
    size = model.domain_size() or (1.0, 1.0, 1.0)
    return DomainSpec(
        coordinate=ar.attrib.get("type", "cube") if ar.attrib.get("type")
        in ("cube", "cylinder") else "cartesian",
        unit=model.domain_unit(),
        xyz_min=base,
        xyz_max=(base[0] + size[0], base[1] + size[1], base[2] + size[2]),
        material=model.domain_material(),
        name=model.domain_name() or "Domain(cuboid)",
        color=model.domain_color() or (0, 255, 255, 255),
        monitor=model.domain_monitor(),
        initial_temperature=model.ambient_temperature(),
    )


def apply_domain(model: StpreModel, spec: DomainSpec,
                 *, name: str | None = None) -> bool:
    """Write a domain back to the XML; creates it when missing."""
    base = spec.xyz_min
    size = (spec.xyz_max[0] - base[0],
            spec.xyz_max[1] - base[1],
            spec.xyz_max[2] - base[2])
    model.ensure_domain(
        name=name or spec.name or "Domain(cuboid)", base=base, size=size,
        unit=spec.unit, material=spec.material)
    if spec.coordinate != "cartesian":
        ar = model.analysis_region()
        if ar is not None:
            ar.attrib["type"] = "cylinder" if spec.coordinate == "cylindrical" \
                else "cube"
    if name is None and spec.name:
        model.set_domain_name(spec.name)
    model.set_domain_color(spec.color)
    model.set_domain_monitor(spec.monitor)
    if spec.initial_temperature is not None:
        model.set_ambient_temperature(spec.initial_temperature)
    # STpre behaviour: the Layout -> RootBlock wireframe follows the
    # Domain(cuboid) position and size.  Keep mesh_block/mesh_control
    # RootBlock AABB identical to the domain (internal grid lines are
    # preserved by set_root_block_range; per-axis extensions too).
    extend = model.root_block_extend()
    try:
        model.set_root_block_range(
            base,
            (base[0] + size[0], base[1] + size[1], base[2] + size[2]),
            unit="mm",
            extend_min=extend[0] if extend is not None else (0.0, 0.0, 0.0),
            extend_max=extend[1] if extend is not None else (0.0, 0.0, 0.0),
        )
    except Exception:
        pass
    return True


def part_bounds(model: StpreModel, tess) -> tuple[np.ndarray, np.ndarray]:
    """World-space min/max over every tessellated part (XML transform
    applied).  Returns two (3,) arrays; both are inf when no geometry."""
    transforms = {p.name: p.transform for p in model.parts()}
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    if not tess:
        return lo, hi
    for part in tess:
        pts = np.asarray(part.points, dtype=np.float64)
        if len(pts) == 0:
            continue
        pts = cab_vtk._apply_transform(
            pts, transforms.get(part.name, ""))
        lo = np.minimum(lo, pts.min(0))
        hi = np.maximum(hi, pts.max(0))
    return lo, hi
