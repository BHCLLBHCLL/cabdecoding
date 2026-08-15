import sys, struct
from pathlib import Path

dll = Path(sys.argv[1])
filter_str = sys.argv[2] if len(sys.argv) > 2 else ''
data = dll.read_bytes()
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt = e_lfanew + 24
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
rows = []
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
            rows.append((dll_name, name, va))
        i += 1
    off += 20

rows.sort()
for dll_name, name, va in rows:
    if filter_str.lower() in name.lower():
        print(hex(va), dll_name, name)
