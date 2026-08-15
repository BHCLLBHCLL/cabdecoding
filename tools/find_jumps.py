"""Find jumps to a target inside a pskernel function range."""
import sys, lief, capstone
DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\pskernel.dll"
def main():
    rva = int(sys.argv[1], 16)
    size = int(sys.argv[2], 16)
    tgt = int(sys.argv[3], 16)
    b = lief.parse(DLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = bytes(b.get_content_from_virtual_address(rva, size))
    for ins in md.disasm(data, ib + rva):
        if ins.mnemonic.startswith("j") and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            if ins.operands[0].imm - ib == tgt:
                print(f"{ins.address-ib:08x}:  {ins.mnemonic} {ins.op_str}")
if __name__ == "__main__":
    main()
