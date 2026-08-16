# P0 diagnostic round 36: the collector's call targets are slots in a
# function-pointer table (.rdata).  Read the actual pointers and name
# them via exports / IAT.
import struct
import lief

MDLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
SLOTS = {
    0x1adc4: 0x61d06, 0x1add6: 0x61cf4, 0x1ade8: 0x61ce2,
    0x1ae4c: 0x61c96, 0x1ae5d: 0x61c5d, 0x1ae76: 0x61614,
    0x1aea9: 0x614e1, 0x1aed6: 0x614b4, 0x1aeea: 0x61580,
    0x1af29: 0x61551, 0x1af95: 0x613f5, 0x1afbe: 0x613cc,
    0x1b01e: 0x61ac4, 0x1b033: 0x61457, 0x1b067: 0x61323,
    0x1b094: 0x612f6, 0x1b0ab: 0x613c7, 0x1b0e5: 0x619e5,
    0x1b108: 0x61aaa, 0x1b135: 0x6121d, 0x1b14b: 0x6120f,
    0x1b17a: 0x61210, 0x1b1aa: 0x611e0, 0x1b238: 0x6197a,
}

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
    for site, disp in sorted(SLOTS.items()):
        slot_va = ib + site + 6 + disp
        raw = bytes(b.get_content_from_virtual_address(slot_va - ib, 8))
        ptr = struct.unpack("<Q", raw)[0]
        name = exports.get(ptr) or iat.get(ptr) or hex(ptr)
        if isinstance(name, str) and len(name) > 58:
            name = name[:58] + "..."
        print(f"call@{hex(site)} slot@{hex(slot_va-ib)} -> {hex(ptr)} {name}")

if __name__ == "__main__":
    main()
