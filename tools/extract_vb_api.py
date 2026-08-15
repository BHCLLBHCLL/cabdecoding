"""Extract STpre VB/COM class method+property lists from the manual HTML."""
import re, sys, html
from pathlib import Path

D = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\VB_Interface_eng")

CLASSES = {
    "Application": "St_vb_Preprocessor_Appliation_Class.html",
    "Doc": "St_vb_Preprocessor_Doc_Class.html",
    "Sketch": "St_vb_Preprocessor_Sketch_Class.html",
    "Model": "St_vb_Preprocessor_Model_Class.html",
    "Mesher": "St_vb_Preprocessor_Mesher_Class.html",
    "MeshBlock": "St_vb_Preprocessor_MeshBlock_Class.html",
    "Table": "St_vb_Preprocessor_Table_Class.html",
    "Property": "St_vb_Preprocessor_Property_Class.html",
    "Value": "St_vb_Preprocessor_Value_Class.html",
}

def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def extract_table(text, header):
    """Extract rows of the table following 'header</th>' up to next 'Method List'/'Property List'/Contents."""
    # find the header occurrence, then parse <tr>..</tr> rows
    i = text.find(header)
    if i < 0:
        return []
    seg = text[i:i+200000]
    rows = re.findall(r"<tr>(.*?)</tr>", seg, re.S)
    out = []
    for r in rows:
        cells = re.findall(r"<td>(.*?)</td>", r, re.S)
        cells = [strip_tags(c) for c in cells]
        if cells and cells[0] and cells[0] not in ("Method", "Property"):
            out.append(cells)
    return out

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "Doc"
    kind = sys.argv[2] if len(sys.argv) > 2 else "method"
    f = D / CLASSES[which]
    raw = f.read_text(encoding="utf-8", errors="replace")
    header = "Method" if kind == "method" else "Property"
    rows = extract_table(raw, header)
    print(f"===== {which} {kind.upper()} ({len(rows)}) =====")
    for cells in rows:
        name = cells[0]
        expl = cells[2] if len(cells) > 2 else ""
        print(f"- {name}: {expl}")

if __name__ == "__main__":
    main()
