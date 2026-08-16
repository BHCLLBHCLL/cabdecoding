# P0 diagnostic round 33: disassemble around PreFace::PushLine call sites
# in STpreBase to reveal the condition guarding each push.
import sys
import lief
import capstone

BDLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

SITES = [0x28d796, 0x297e60, 0x298c30, 0x29c5d3, 0x29c73b, 0x29d6e5,
         0x29d7a8, 0x29defa, 0x29dfc3, 0x29e839, 0x29e981, 0x29ff9b,
         0x2a010d, 0x2a14a8, 0x2a15dc]

def main():
    which = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0
    before = int(sys.argv[2]) if len(sys.argv) > 2 else 70
    after = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    rva = SITES[which]
    b = lief.parse(BDLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    md.skipdata = True
    # back up `before` bytes (instructions may misalign; acceptable)
    start = max(0, rva - before)
    data = bytes(b.get_content_from_virtual_address(start, before + after * 8))
    exports = {e.address: e.name for e in b.exported_functions if e.name}
    for ins in md.disasm(data, ib + start):
        mark = " <== PUSHLINE" if ins.address - ib == rva else ""
        if ins.address - ib > rva + after * 4:
            break
        tgt = ""
        if ins.mnemonic in ("call", "jmp") and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm - ib
            if t in exports:
                tgt = f"  ; {exports[t].split('@')[0]}"
            else:
                tgt = f"  ; rva {hex(t)}"
        print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str:44s}{tgt}{mark}")

if __name__ == "__main__":
    main()
