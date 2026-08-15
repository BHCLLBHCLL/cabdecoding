"""Find functions (via .pdata) that call a target RVA via RIP-relative call/jmp/lea."""
import sys, lief, capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    targets = [int(x, 16) for x in sys.argv[1:]]
    bin_ = lief.parse(DLL)
    ib = bin_.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    # Build function list from exception directory (.pdata)
    funcs = []
    for f in bin_.functions:
        funcs.append((f.address - ib, f.size))
    print(f"total functions: {len(funcs)}")
    # also scan raw .text directly as fallback
    txt = next(s for s in bin_.sections if s.name == ".text")
    base_va = ib + txt.virtual_address
    data = bytes(txt.content)

    for tgt in targets:
        hits = []
        for ins in md.disasm(data, base_va):
            if ins.mnemonic in ("call", "jmp") and ins.operands                     and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                if ins.operands[0].imm - ib == tgt:
                    hits.append((ins.address - ib, ins.mnemonic))
            # lea reg, [rip+disp] -> resolve to target
            if ins.mnemonic == "lea" and ins.operands                     and ins.operands[1].type == capstone.x86.X86_OP_MEM                     and ins.operands[1].mem.base == capstone.x86.X86_REG_RIP:
                if ins.operands[1].mem.disp + ins.size + ins.address - ib == tgt:
                    hits.append((ins.address - ib, "lea"))
        print(f"target {hex(tgt)}: {len(hits)} refs")
        for h in sorted(set(hits)):
            print(f"   {h[0]:08x}  {h[1]}")

if __name__ == "__main__":
    main()
