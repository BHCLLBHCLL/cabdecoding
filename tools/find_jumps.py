import sys, struct
from pathlib import Path

dll = Path(sys.argv[1])
slots = [int(a, 16) for a in sys.argv[2:]]
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

thunks = {}
for name, va, vsize, raw, raw_size in sections:
    if '.text' not in name:
        continue
    blob = data[raw:raw + raw_size]
    base = va
    for i in range(len(blob) - 6):
        if blob[i] == 0xFF and blob[i + 1] == 0x25:
            disp = struct.unpack_from('<i', blob, i + 2)[0]
            tgt = (base + i + 6 + disp) & 0xFFFFFFFF
            if tgt in slots:
                thunks[base + i] = tgt
for t, s in sorted(thunks.items()):
    print(hex(t), '-> slot', hex(s))
