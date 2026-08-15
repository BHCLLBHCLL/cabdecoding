import collections, re
lines = [l.strip() for l in open("docs/pskernel_exports.txt", encoding="utf-8")]
pk = [l for l in lines if l.startswith("PK_")]
by = collections.defaultdict(list)
for l in pk:
    parts = l.split("_")
    by[parts[1] if len(parts) > 1 else "?"].append(l)
for k in sorted(by, key=lambda kv: -len(by[kv])):
    print(f"### {k} ({len(by[k])})")
    for f in sorted(by[k]):
        print("   ", f)
