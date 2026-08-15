# Map IAT VAs of STpreMesh_Bx64.dll to import names.
import sys, struct
from pathlib import Path

dll = Path(r'C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll')
data = dll.read_bytes()
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt = e_lfanew + 24
image_base = struct.unpack_from('<Q', data, opt + 24)[0]
sections = []
off = opt + struct.unpack_from('<H', data, e_lfanew + 20)[0]
for _ in range(nsec):
    name = data[off:off + 8].rstrip(b'\x00').decode('ascii', 'replace')
    vsize = struct.unpack_from('<I', data, off + 8)[0]
    va = struct.unpack_from('<I', data, off + 12)[0]
    raw_size = struct.unpack_from('<I', data, off + 16)[0]
    raw = struct.unpack_from('<I', data, off + 20)[0]
    sections.append((name, va, vsize, raw, raw_size))
    off += 40

def va_to_off(va):
    for name, sva, vsize, raw, raw_size in sections:
        if sva <= va < sva + max(vsize, raw_size):
            return raw + (va - sva)
    return None

def off_to_va(foff):
    for name, sva, vsize, raw, raw_size in sections:
        if raw <= foff < raw + raw_size:
            return sva + (foff - raw)
    return None

dd = opt + 112
imp_rva, imp_size = struct.unpack_from('<II', data, dd + 8)
off = va_to_off(imp_rva)
by_va = {}
while off is not None:
    oft = struct.unpack_from('<I', data, off)[0]
    name_rva = struct.unpack_from('<I', data, off + 12)[0]
    first_thunk = struct.unpack_from('<I', data, off + 16)[0]
    if name_rva == 0:
        break
    noff = va_to_off(name_rva)
    dll_name = data[noff:noff + 80].split(b'\x00')[0].decode()
    oft_off = va_to_off(oft) if oft else va_to_off(first_thunk)
    ft_off = va_to_off(first_thunk)
    i = 0
    while True:
        hint = struct.unpack_from('<Q', data, oft_off + i * 8)[0]
        thunk = struct.unpack_from('<Q', data, ft_off + i * 8)[0]
        if hint == 0 and thunk == 0:
            break
        if hint & 0x8000000000000000:
            name = '#%d' % (hint & 0xFFFF)
        else:
            n = va_to_off(hint)
            name = (data[n + 2:n + 80].split(b'\x00')[0].decode()
                    if n is not None else '?')
        va = off_to_va(ft_off + i * 8)
        if va is not None:
            by_va[va] = (dll_name, name)
        i += 1
    off += 20

for va in (0x7c330, 0x7c358, 0x7c3f0, 0x7c490, 0x7c4a0, 0x7c4d0, 0x7c4d8,
           0x7c558, 0x7c560, 0x7c568, 0x7c9c0, 0x7c9d0, 0x7cac0, 0x7cad0,
           0x7cae8, 0x7cbb8, 0x7cc68):
    print(hex(va), '->', by_va.get(va))
