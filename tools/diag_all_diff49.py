# P0 diagnostic round 49: find callers of PreFace::PushLine /
# PreFace::GetVertex inside STpreMesh_Bx64.dll.  Resolve IAT slots for
# STpreBase imports, then scan .text for `call [rip+disp]` hits.
import sys
import lief
import capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"

def main():
    targets = sys.argv[1:] or ["PushLine", "GetVertex"]
    b = lief.parse(DLL)
    ib = b.imagebase
    iat = {}
    for lib in b.imports:
        for e in lib.entries:
            if e.name:
                va = e.iat_value if e.iat_value >= ib else e.iat_value + ib
                iat.setdefault(va, lib.name.split('.')[0] + "!" + e.name)
    slots = {va: nm for va, nm in iat.items()
             if any(t in nm for t in targets)}
    print(f"IAT slots for {targets}: {len(slots)}")
    for va, nm in sorted(slots.items()):
        print(f"  {hex(va)}  {nm}")

    text = next(s for s in b.sections if s.name == ".text")
    data = bytes(text.content)
    base = ib + text.virtual_address
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits = {}
    for ins in md.disasm(data, base):
        if ins.mnemonic not in ("call", "jmp"):
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in slots:
                    hits.setdefault(tgt, []).append(
                        (ins.address - ib, ins.mnemonic))
    for va in sorted(hits):
        print(f"== {slots[va]} callers:")
        for rva, m in hits[va]:
            print(f"   {hex(rva)} {m}")

if __name__ == "__main__":
    main()
