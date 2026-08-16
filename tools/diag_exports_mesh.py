# List exported symbols of STpreMesh/STpreBase matching keywords.
import sys
import lief

for dll in (r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll",
            r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"):
    b = lief.parse(dll)
    names = sorted((e.address, e.name) for e in b.exported_functions if e.name)
    kws = sys.argv[1:] or ["Mesh", "Divide", "Line", "Vertex", "Grid"]
    print(f"== {dll.split(chr(92))[-1]}: {len(names)} exports")
    for addr, nm in names:
        if any(k.lower() in nm.lower() for k in kws):
            print(f"  {hex(addr)}  {nm[:110]}")
