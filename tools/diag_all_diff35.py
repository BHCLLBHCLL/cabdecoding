# P0 diagnostic round 35: disassemble the local thunks the collector
# calls (0x7c3xx region) to find their real targets.
import struct
import lief
import capstone

MDLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
THUNKS = [0x7cad0, 0x7cae8, 0x7cac0, 0x7c490, 0x7c390, 0x7c470,
          0x7c480, 0x7c478, 0x7cbb8, 0x7c358, 0x7c360]

def main():
    b = lief.parse(MDLL)
    ib = b.imagebase
    iat = {}
    for lib in b.imports:
        for e in lib.entries:
            if e.name:
                va = e.iat_value if e.iat_value >= ib else e.iat_value + ib
                iat[va] = f"{lib.name.split('.')[0]}!{e.name}"
    exports = {e.address + ib: e.name for e in b.exported_functions if e.name}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for t in THUNKS:
        data = bytes(b.get_content_from_virtual_address(t, 24))
        ins = next(md.disasm(data, ib + t), None)
        if ins is None:
            print(f"{hex(t)}: <bad>")
            continue
        desc = f"{ins.mnemonic} {ins.op_str}"
        # rip-relative jmp/call through IAT?
        if "[" in ins.op_str and "rip" in ins.op_str:
            # parse disp from op_str
            try:
                disp = int(ins.op_str.split("rip + ")[1].rstrip("]"), 16) \
                    if "rip + " in ins.op_str else \
                    int(ins.op_str.split("rip - ")[1].rstrip("]"), 16) * -1
            except Exception:
                disp = 0
            tgt = ins.address + ins.size + disp
            name = iat.get(tgt) or exports.get(tgt) or hex(tgt)
            desc += f"   ; -> {name}"
        else:
            name = exports.get(ib + t, "")
            if name:
                desc += f"   ; export {name}"
        print(f"{hex(t)}: {desc}")

if __name__ == "__main__":
    main()
