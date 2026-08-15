"""Extract all MeshBlock method mangled names from the DLL."""
import re, lief
DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"
bin_ = lief.parse(DLL)
# read all sections' raw bytes and search
names = set()
for s in bin_.sections:
    data = bytes(s.content)
    for m in re.finditer(rb"\?[A-Za-z0-9_~]+@MeshBlock@@[A-Za-z0-9_@$]*@Z", data):
        names.add(m.group().decode("ascii", "replace"))
for n in sorted(names):
    print(n)
