"""End-to-end cylindrical: axes + occupancy for a cylinder centred on the axis."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, cab_mesh
from cab_parts import PrimitivePart

# domain R=0..50 mm, theta 0..360, Z=0..100
spec = cab_grid.GridSpec(
    unit="mm", domain_min=(0.0, 0.0, 0.0), domain_max=(50.0, 360.0, 100.0),
    domain_coordinate="cylindrical", vertex_detection="minmax",
    method="rough_and_detail", standard_length=5.0, threshold_length=0.1,
    geometric_ratio=1.0, geometric_ratio_external=1.2)

# cylinder r=10, z=20..80 (tessellated), centred on axis
nlon, nlat = 32, 6
th = np.linspace(0, 2*np.pi, nlon, endpoint=False)
zc = np.array([20.0, 80.0])
pts, tris = [], []
# side wall points (mm)
for z in zc:
    for t in th:
        pts.append([10*np.cos(t), 10*np.sin(t), z])
base = len(pts)
tris = []
for i in range(nlon):
    j = (i+1) % nlon
    # side quad -> 2 tris
    tris.append([i, j, nlon+i]); tris.append([j, nlon+j, nlon+i])
tess = PrimitivePart("cyl", np.array(pts, float)/1000.0, np.array(tris, int))
tess.name = "cyl"

rough, axes = cab_grid.build_axes({"cyl": np.array(pts, float)}, spec)
print("R axis:", np.round(axes["x"],3).tolist())
print("theta points:", len(axes["y"]))
print("Z axis:", np.round(axes["z"],3).tolist())
analysis, boxes = cab_mesh.classify_cells(
    axes, [tess], coordinate="cylindrical")
print("analysis box:", analysis)
print("cyl boxes (first 3):", boxes.get("cyl", [])[:3])
print("cyl box count:", len(boxes.get("cyl", [])))
if boxes.get("cyl"):
    b = boxes["cyl"][0]
    print(f"  box i={b[0]}..{b[1]} j={b[2]}..{b[3]} k={b[4]}..{b[5]}")
