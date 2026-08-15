# List STpreMesh_Bx64.dll export symbols (and count them).
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

dd = opt + 112
exp_rva, exp_size = struct.unpack_from('<II', data, dd)
off = va_to_off(exp_rva)
n_names = struct.unpack_from('<I', data, off + 24)[0]
n_funcs = struct.unpack_from('<I', data, off + 20)[0]
addr_rva = struct.unpack_from('<I', data, off + 28)[0]
nameptr_rva = struct.unpack_from('<I', data, off + 32)[0]
ord_rva = struct.unpack_from('<I', data, off + 36)[0]
addr_off = va_to_off(addr_rva)
nameptr_off = va_to_off(nameptr_rva)
ord_off = va_to_off(ord_rva)
out = []
for i in range(n_names):
    ord_ = struct.unpack_from('<H', data, ord_off + i * 2)[0]
    rva = struct.unpack_from('<I', data, addr_off + ord_ * 4)[0]
    np_rva = struct.unpack_from('<I', data, nameptr_off + i * 4)[0]
    noff = va_to_off(np_rva)
    nm = data[noff:noff + 200].split(b'\x00')[0].decode('ascii', 'replace')
    out.append((nm, rva))
print('exports:', len(out))
for nm, rva in out:
    low = nm.lower()
    if any(k in low for k in ('grid', 'divide', 'vertex', 'facet',
                              'inner', 'outer', 'fine', 'line')):
        print(f'{rva:#x}  {nm}')
