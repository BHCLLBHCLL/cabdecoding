# P0 diagnostic round 38: find SubBlock-related exports in STpreBase
# and STpreMesh - the builder that fills nx/ny/nz dims, the SubBlock
# bbox fields (+0x10/+0x28 per axis) and the +0x44 enable flag.
import lief

BASE = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
for dll in ("STpreMesh_Bx64.dll", "STpreBase_Bx64.dll"):
    b = lief.parse(BASE + "\\" + dll)
    hits = []
    for e in b.exported_functions:
        n = e.name or ""
        if any(k in n for k in ("SubBlock", "SubGrid", "DivideBox")):
            hits.append((e.address, n))
    print(f"== {dll}: {len(hits)} ==")
    for rva, n in sorted(hits):
        print(f"  {hex(rva)}  {n}")
