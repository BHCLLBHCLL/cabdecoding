# P0 diagnostic round 21 (lief): disassemble the STpreMesh collector with
# IAT annotation; locate PushLine/GetVertex/IsFacePlane call sites.
import sys
from pathlib import Path
import lief
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import capstone
X86_OP_MEM = capstone.x86.X86_OP_MEM
X86_OP_IMM = capstone.x86.X86_OP_IMM
X86_REG_RIP = capstone.x86.X86_REG_RIP

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
b = lief.parse(DLL)
ib = b.imagebase

iat = {}
for e in b.imports:
    ft = e.import_address_table_rva
    for i, f in enumerate(e.entries):
        if f.iat_value:
            nm = f.name if f.name else f"ord{f.ordinal}"
            iat[ft + i*8] = nm
print(f"IAT entries: {len(iat)}")

exp = {}
for f in b.exported_functions:
    if f.name:
        exp[f.address] = f.name

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

def read(rva, n):
    return bytes(b.get_content_from_virtual_address(ib + rva, n))

def annotate(ins):
    note = ""
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            if tgt in iat:
                note = f"  ; [{iat[tgt]}]"
            else:
                note = f"  ; ds:{tgt:x}"
    if ins.mnemonic in ("call", "jmp") and ins.operands \
            and ins.operands[0].type == X86_OP_IMM:
        t = ins.operands[0].imm
        if t in iat:
            note = f"  ; {iat[t]}"
        elif t in exp:
            note = f"  ; {exp[t]}"
    return note

def dis_range(start, end):
    code = read(start, end - start)
    for ins in md.disasm(code, start):
        print(f"{ins.address:08x}: {ins.mnemonic:7s} {ins.op_str:44s}{annotate(ins)}")

COLLECT_START, COLLECT_END = 0x1ab90, 0x1cba0
KEYS = ("PushLine", "GetVertex", "IsFacePlane", "OrientationMinMax",
        "ThinOutPolyLine", "GetEdge@", "MakeFacet", "SurfParam",
        "NormalType", "FineCoord", "SelectCoord", "FacetAxisPlane")
code = read(COLLECT_START, COLLECT_END - COLLECT_START)
hits = []
for ins in md.disasm(code, COLLECT_START):
    nm = None
    if ins.mnemonic in ("call", "jmp") and ins.operands \
            and ins.operands[0].type == X86_OP_IMM:
        t = ins.operands[0].imm
        if t in iat:
            nm = iat[t]
    else:
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in iat:
                    nm = iat[tgt]
    if nm and any(k in nm for k in KEYS):
        hits.append((ins.address, ins.mnemonic, nm))
print("\ncall/ref sites of interest:")
for a, m, nm in hits:
    print(f"  {a:08x} {m:6s} {nm}")

if len(sys.argv) > 2:
    s = int(sys.argv[1], 16)
    e = int(sys.argv[2], 16)
    print(f"\n--- disasm {s:x}..{e:x} ---")
    dis_range(s, e)
