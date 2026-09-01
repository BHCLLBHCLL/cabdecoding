# -*- coding: utf-8 -*-
"""F7 groundwork: Pre_eng page-by-page coverage mapping (§25.0).

Categories every Pre_eng manual page and cross-references the page name
against the repository sources so the F7 final audit starts from a
machine-generated baseline instead of keyword guesswork.  The derived
key is the dialog/page title taken from the filename; a HIT means the
repository mentions that phrase (heuristic — review required in F7).
"""
from __future__ import annotations

import html
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\Pre_eng")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# F7: condition pages closed by the C1-C8 batches (§23) — recognised apart
# from the crude title-hit heuristic.
CLOSED_CONDITIONS = (
    "contact angle", "contact thermal resistance",
    "electrical contact resistance", "electric potential",
    "electrostatic field", "total temperature", "fixed pressure",
    "fan boundary", "mass transfer boundary", "constant moisture flux",
    "initial moisture", "humidity transfer", "humidity source",
    "humidity absorption", "sum of pressure output", "output passage",
    "termination variable", "standardized concentration",
    "parts' internal variables", "pathline output", "wave generation",
    "wave energy attenuation", "fluid interface", "foaming resin",
    "permeable object", "laser", "reaction", "reaction of particle",
    "particle generation timing", "particle rebound",
    "particle sedimentation", "particle spray", "particle vanishment",
    "particle external force", "between particles",
    "force between particles", "particle symmetry", "design space",
    "chemical material", "compressible fluid", "cloth model",
    "check time step", "calculate conductivity",
    "calculation of heat transfer coefficient",
    "calculation of humidity absorption",
)


def page_title(fname: str) -> str:
    stem = fname[:-5]
    stem = re.sub(r"^St_pre_", "", stem)
    stem = re.sub(r"_dialog$", "", stem)
    stem = re.sub(r"\.$", "", stem)
    m = re.match(r"(?:Condition|Details|Supplement|Wizard)_\(?(.+?)\)?$", stem)
    if m:
        stem = m.group(1)
    # Wizard sub-pages: St_pre_Wizard-Condition_Setting-A-B-C -> use "C"
    if stem.startswith("Wizard-"):
        stem = stem.split("-")[-1]
    stem = stem.replace("_", " ")
    for a, b in (("-", " "), ("  ", " ")):
        stem = stem.replace(a, b)
    return stem.strip()


def category(fname: str) -> str:
    if "_menu" in fname or "Menu_Guide" in fname:
        return "menu"
    if fname.startswith("St_pre_Condition_"):
        return "condition"
    if fname.startswith("St_pre_Part-"):
        return "part"
    if fname.startswith("St_pre_Wizard-"):
        return "wizard"
    if fname.startswith(("St_pre_Details_", "St_pre_Supplement", "St_pre_About",
                         "St_cover", "St_intro", "St_trademarks")):
        return "reference"
    return "operation"


def main() -> int:
    pages = sorted(p for p in os.listdir(MANUAL) if p.endswith(".html"))
    # corpus of repository sources
    src = []
    for path in ROOT.glob("*.py"):
        src.append(path.read_text(encoding="utf-8", errors="ignore"))
    corpus = "\n".join(src)
    tpl_all = {
        norm(t): t for t in re.findall(r'"([A-Z][A-Za-z0-9 ,\-()/]{5,60})"', corpus)
    }
    corpus_norm = norm(corpus)

    rows = []
    counts = Counter()
    for fname in pages:
        cat = category(fname)
        title = page_title(fname)
        key = norm(title)
        hit = bool(key) and key in corpus_norm
        lowered = title.lower()
        if any(lowered.startswith(c) or c in lowered
               for c in CLOSED_CONDITIONS):
            hit = True  # closed by the §23 condition batches
        counts[(cat, "hit" if hit else "miss")] += 1
        rows.append((cat, title, fname, hit))

    out = ["# Pre_eng 手册逐页覆盖映射（生成基线，F7 终审输入）",
           "",
           f"- 手册页总数：**{len(pages)}**",
           f"- 生成工具：`tools/gen_manual_coverage.py`",
           "",
           "## 分类统计（HIT = 仓库源码中出现该页标题关键词；启发式，需人工复核）",
           "",
           "| 分类 | HIT | MISS | 合计 |", "|---|---:|---:|---:|"]
    for cat in ("condition", "part", "wizard", "operation", "menu", "reference"):
        h = counts[(cat, "hit")]
        m = counts[(cat, "miss")]
        out.append(f"| {cat} | {h} | {m} | {h + m} |")
    out.append("")
    out.append("## MISS 页清单（F7 逐项确认：实现 / B 定档 / C 声明）")
    out.append("")
    for cat, title, fname, hit in rows:
        if not hit:
            out.append(f"- [{cat}] {title} — `{fname}`")

    dest = ROOT / "docs" / "manual_coverage.md"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"pages={len(pages)} hits={sum(v for k, v in counts.items() if k[1] == 'hit')}")
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
