"""Locate InnerRegionGrid/OuterRegionGrid/ExecDivide RVAs in STpreMesh_Bx64.dll."""
import lief, capstone, struct

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"

b = lief.parse(DLL)
ib = b.imagebase
print("imagebase", hex(ib), "sections:")
for s in b.sections:
    print(f"  {s.name:12s} VA {hex(s.virtual_address):>9s} size {hex(s.size):>8s} chars {hex(int(s.characteristics))}")

# exports
print("exports:")
for e in sorted(b.exported_functions, key=lambda e: e.name or "")[:60]:
    if e.name:
        print(f"  {e.name} RVA {hex(e.address - ib)}")
