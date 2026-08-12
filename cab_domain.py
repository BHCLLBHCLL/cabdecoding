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


def _coordinate_from_model(model: StpreModel, ar) -> str:
    """Map XML domain type → DomainSpec.coordinate.

    Prefer explicit ``mesh_control/domain_coordinate`` (stores axial);
    else ``analysis_region@type``: cylinder→cylindrical, cube→cartesian.
    """
    stored = (model.mesh_control_value("domain_coordinate") or "").strip().lower()
    if stored in ("cartesian", "cylindrical", "axial"):
        return stored
    xml_type = (ar.attrib.get("type") or "cube").strip().lower()
    if xml_type == "cylinder":
        return "cylindrical"
    return "cartesian"


def domain_from_xml(model: StpreModel) -> Optional[DomainSpec]:
    """Read the current domain; ``None`` when no ``<analysis_region>``."""
    ar = model.analysis_region()
    if ar is None:
        return None
    base = model.domain_base() or (0.0, 0.0, 0.0)
    size = model.domain_size() or (1.0, 1.0, 1.0)
    return DomainSpec(
        coordinate=_coordinate_from_model(model, ar),
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
    ar = model.analysis_region()
    if ar is not None:
        # Honesty: cylindrical/axial flags are stored; native grid generation
        # still uses cartesian AABB axes (see cab_grid / GriddingDialog).
        if spec.coordinate == "cylindrical":
            ar.attrib["type"] = "cylinder"
        else:
            ar.attrib["type"] = "cube"  # cartesian and axial
    try:
        model.set_mesh_control_value(
            "domain_coordinate",
            spec.coordinate if spec.coordinate in (
                "cartesian", "cylindrical", "axial") else "cartesian")
    except Exception:
        pass
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
        if part is None:
            continue
        pts = np.asarray(part.points, dtype=np.float64)
        if len(pts) == 0:
            continue
        pts = cab_vtk._apply_transform(
            pts, transforms.get(part.name, ""))
        lo = np.minimum(lo, pts.min(0))
        hi = np.maximum(hi, pts.max(0))
    return lo, hi


_UNIT_TO_MM = {"mm": 1.0, "m": 1000.0, "cm": 10.0}


def fit_domain_to_parts(
    model: StpreModel,
    tess,
    *,
    margin_frac: float = 0.0,
    margin_abs: float = 0.0,
) -> Optional[tuple[tuple[float, float, float],
                    tuple[float, float, float]]]:
    """Resize Domain(cuboid) + RootBlock to the world AABB of ``tess``.

    Matches STpre **CAD Data Size** / post-Import behaviour: domain min/max
    follow the imported geometry bounding box.  ``part_bounds`` is metres;
    values are written in the current domain unit (default mm).

    Returns ``(xyz_min, xyz_max)`` in domain unit, or ``None`` if empty.
    """
    lo_m, hi_m = part_bounds(model, tess)
    if not np.isfinite(lo_m).all() or not np.isfinite(hi_m).all():
        return None
    unit = "mm"
    if model.analysis_region() is not None:
        unit = model.domain_unit() or "mm"
    if unit not in _UNIT_TO_MM:
        unit = "mm"
    # metres → domain unit
    scale = 1000.0 / _UNIT_TO_MM[unit]
    lo = np.asarray(lo_m, dtype=np.float64) * scale
    hi = np.asarray(hi_m, dtype=np.float64) * scale
    span = hi - lo
    # Degenerate axes (flat sheet / single plane): give a minimal thickness
    min_span = 1.0 if unit == "mm" else (0.1 if unit == "cm" else 0.001)
    for i in range(3):
        if span[i] < min_span * 1e-6:
            mid = 0.5 * (lo[i] + hi[i])
            lo[i] = mid - 0.5 * min_span
            hi[i] = mid + 0.5 * min_span
            span[i] = hi[i] - lo[i]
    if margin_frac > 0.0 or margin_abs > 0.0:
        pad = np.maximum(span * float(margin_frac), float(margin_abs))
        lo = lo - pad
        hi = hi + pad
    spec = domain_from_xml(model) or DomainSpec(unit=unit)
    spec.unit = unit
    spec.xyz_min = (float(lo[0]), float(lo[1]), float(lo[2]))
    spec.xyz_max = (float(hi[0]), float(hi[1]), float(hi[2]))
    if not (spec.material or "").strip():
        spec.material = "air(incompressible/20C)"
    apply_domain(model, spec)
    return spec.xyz_min, spec.xyz_max
