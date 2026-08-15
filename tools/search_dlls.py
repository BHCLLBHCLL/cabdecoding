"""Search DLLs for gridding method mangled names to locate the orchestration code."""
import re, sys, lief
from pathlib import Path

D = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
names = sys.argv[1:] or ["InnerRegionGrid", "OuterRegionGrid", "ExecDivide", "CalcFineCoord", "CalcRatio1", "CalcFine"]
for dll in sorted(D.glob("*.dll")):
    try:
        b = lief.parse(str(dll))
    except Exception:
        continue
    hits = []
    for s in b.sections:
        data = bytes(s.content)
        for n in names:
            if n.encode() in data:
                hits.append(n)
    if hits:
        print(f"{dll.name}: {sorted(set(hits))}")
