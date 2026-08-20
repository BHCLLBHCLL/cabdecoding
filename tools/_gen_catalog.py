"""One-off: replace API_CATALOG with the full manual snapshot (W5)."""
import io, json, re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root / "cab_stpre_api.py"
text = src.read_text(encoding="utf-8")

table = json.loads((root / "data" / "com_typelib_members.json").read_text(encoding="utf-8"))
members = {k: sorted(v) for k, v in table.items() if not k.startswith("_")}
assert len(members) == 11, len(members)

# keep the hand-collected MeshBlock list from the old catalog
old = text
mstart = text.index("API_CATALOG: dict[str, list[str]] = {")
mend = text.index("# Method counts observed in the VB_Interface_eng manual")
old_block = text[mstart:mend]
mb = re.search(r'"MeshBlock": \[(.*?)\]', old_block, re.S).group(1)
meshblock = re.findall(r'"([^"]+)"', mb)
assert len(meshblock) == 23, meshblock

members["MeshBlock"] = meshblock  # no manual class page — kept from audit

lines = [
    "API_CATALOG: dict[str, list[str]] = {",
    "    # Authoritative manual snapshot (W5, 2026-08-18): the heading",
    "    # anchors of all 11 VB_Interface_eng class pages, exported from",
    "    # manual_member_table() into data/com_typelib_members.json",
    "    # (_source=manual). MeshBlock has no manual class page; its list",
    "    # is the hand-collected catalog kept from earlier audits.",
]
for key in sorted(members):
    vals = members[key]
    lines.append(f'    "{key}": [')
    for i in range(0, len(vals), 4):
        chunk = ", ".join(f'"{v}"' for v in vals[i:i + 4])
        tail = "," if i + 4 < len(vals) else ""
        lines.append(f"        {chunk}{tail}")
    lines.append("    ],")
lines.append("}")
new_block = "\n".join(lines) + "\n\n\n"

text = text[:mstart] + new_block + text[mend:]
src.write_text(text, encoding="utf-8", newline="\n")
print("catalog classes:", len(members), "members:", sum(len(v) for v in members.values()))
