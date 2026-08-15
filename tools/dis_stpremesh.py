"""Disassemble STpreMesh_Bx64.dll gridding functions."""
import sys
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"

def main():
    rva = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    b = lief.parse(DLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = bytes(b.get_content_from_virtual_address(rva, count * 20))
    for ins in md.disasm(data, ib + rva, count=count):
        tgt = ""
        if ins.mnemonic in ("call", "jmp") and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm - ib
            # resolve imported name if possible
            tgt = f"  ; -> {hex(t)}"
            for e in b.exported_functions:
                if e.address == t and e.name:
                    tgt = f"  ; -> {e.name}"
                    break
            if not tgt.endswith(")") and "->" not in tgt:
                tgt = f"  ; -> RVA {hex(t)}"
        print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str:46s}{tgt}")

if __name__ == "__main__":
    main()
