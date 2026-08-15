"""Find call xrefs to a target RVA inside STpreBase_Bx64.dll."""
import sys, lief, capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    target_rva = int(sys.argv[1], 16)
    bin_ = lief.parse(DLL)
    ib = bin_.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits = []
    for s in bin_.sections:
        chars = getattr(s, "characteristics", 0)
        if not (chars & 0x20000000):  # IMAGE_SCN_MEM_EXECUTE
            continue
        base_va = ib + s.virtual_address
        for ins in md.disasm(bytes(s.content), base_va):
            if ins.mnemonic in ("call", "jmp") and ins.operands                     and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                t = ins.operands[0].imm - ib
                if t == target_rva:
                    hits.append(ins.address - ib)
    print(f"xrefs to {hex(target_rva)}: {len(hits)}")
    for h in sorted(set(hits)):
        print(f"  0x{h:08x}")

if __name__ == "__main__":
    main()
