"""Read double constants from ParasolidGW .rdata at given RVAs."""
import lief, struct, sys
DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\ParasolidGW_Bx64.dll"
b = lief.parse(DLL)
for h in sys.argv[1:]:
    rva = int(h, 16)
    data = bytes(b.get_content_from_virtual_address(rva, 8))
    print(f"rva {h}: {struct.unpack('<d', data)[0]:.17g}")
