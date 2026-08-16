# P0 diagnostic round 32: cross-DLL xref hunt.
# A) STpreBase: find export RVA of PreFace::PushLine, scan .text for
#    direct `call rel32` references to it.
# B) STpreMesh: brute-force any rip-relative reference (call/jmp/mov)
#    to the get_vertex@PreBody IAT slot.
import struct
import lief
import capstone

BASE = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
MDLL = BASE + r"\STpreMesh_Bx64.dll"
BDLL = BASE + r"\STpreBase_Bx64.dll"

def text_section(b):
    for s in b.sections:
        if s.name == ".text":
            return s
    return None

def find_export(b, substr):
    for e in b.exported_functions:
        if substr in (e.name or ""):
            return e.address, e.name   # RVA
    return None, None

def scan_rel32_calls(b, target_rva):
    """All E8 call sites in .text whose destination == target_rva."""
    s = text_section(b)
    base_rva = s.virtual_address
    content = bytes(s.content)
    hits = []
    for i in range(len(content) - 5):
        if content[i] == 0xE8:
            disp = struct.unpack_from("<i", content, i + 1)[0]
            tgt = base_rva + i + 5 + disp
            if tgt == target_rva:
                hits.append(base_rva + i)
    return hits

def scan_slot_refs(b, slot_va):
    """Brute-force rip-relative refs: any 6-byte window ending in disp32."""
    s = text_section(b)
    base_rva = s.virtual_address
    ib = b.imagebase
    content = bytes(s.content)
    hits = []
    for i in range(len(content) - 6):
        disp = struct.unpack_from("<i", content, i + 2)[0]
        tgt = ib + base_rva + i + 6 + disp
        if tgt == slot_va:
            hits.append(base_rva + i)
    return hits

print("== A) STpreBase: PushLine export xrefs ==")
bb = lief.parse(BDLL)
plib_rva, plname = find_export(bb, "PushLine@PreFace")
if plib_rva:
    print(f"export {plname} rva={hex(plib_rva)}")
    for rva in scan_rel32_calls(bb, plib_rva):
        print(f"  direct call at rva={hex(rva)}")
else:
    print("PushLine not exported by STpreBase")
gv_rva, gvname = find_export(bb, "get_vertex@PreBody")
if gv_rva:
    print(f"export {gvname} rva={hex(gv_rva)}")
    for rva in scan_rel32_calls(bb, gv_rva):
        print(f"  direct call at rva={hex(rva)}")

print("\n== B) STpreMesh: any refs to get_vertex IAT slot ==")
bm = lief.parse(MDLL)
ibm = bm.imagebase
slot = None
for lib in bm.imports:
    for e in lib.entries:
        if e.name and "get_vertex@PreBody" in e.name:
            slot = e.iat_value if e.iat_value >= ibm else e.iat_value + ibm
            print(f"slot va={hex(slot)}")
if slot:
    for rva in scan_slot_refs(bm, slot):
        print(f"  ref at rva={hex(rva)} (bytes before decide call/jmp/mov)")
