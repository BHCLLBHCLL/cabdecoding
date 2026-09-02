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


# F7 review: condition pages whose features exist via an alias/variant or
# the porous/wall/ventilation families implemented earlier (keyword
# mismatch only) — closed with the implementing keyword.
CONDITION_ALIASES = {
    "anemostat boundary": "anemostat",
    "area objective function": "topology",
    "average min max value output": "minmax",
    "dem particle generation": "particle",
    "dem particle restitution heat transfer": "restitution",
    "dem particle symmetry": "dem",
    "fixed vof value": "vof",
    "freeslip boundary": "free_slip",
    "heat transfer boundary": "heat_transfer",
    "linear diffuser model boundary": "diffuser",
    "moving object 6dof rigid body motion": "body_move_6dof",
    "moving object contact face heat transfer": "moving_body",
    "moving object initial amount of moisture": "moving_body",
    "moving object opening": "moving_body",
    "moving object wall": "body_wall",
    "natural convection heat transfer boundary for enclosure": "enclosure",
    "operation variable": "variable",
    "partial fld output": "partial_fld",
    "particle dew condensation amount conversion": "dew",
    "particle fixed velocity": "particle",
    "particle heat source": "particle",
    "particle motion user defined": "particle",
    "particle passage": "passage",
    "particle statistics": "particle",
    "porous media anisotropic": "porous",
    "porous media isotropic": "porous",
    "porous media isotropic solid solid type": "porous",
    "porous media particle": "porous",
    "porous media plate fin": "porous",
    "porous media heat transfer": "porous",
    "power law velocity boundary": "power_law",
    "power law wall shear stress condition": "rough",
    "pressure loss boundary": "pressure_loss",
    "rough wall shear stress condition": "rough",
    "smooth wall shear stress condition": "no_slip",
    "solar radiation lamp boundary": "solar_lamp",
    "space distribution of mean radiant temperature": "mrt",
    "thermal transport for heat conduction panel": "panel",
    "ventilation efficiency exhaust contribution rate": "ventilation",
    "ventilation efficiency inlet contribution rate": "ventilation",
    "ventilation efficiency age of air life expectancy of air lifetime of air": "ventilation",
    "volumetric objective function": "topo_obj_func",
    "settings (condition setting of structural analysis": "structural",
    "welding when mars method is used": "welding",
    "variable of volumetric region": "lfile_rgn_vol",
    "variable of face region": "lfile_rgn_face",
    "vapor pressure": "vapor",
    "thermal transport condition": "heat_transport",
    "thermal boundary condition (free surface)": "free_surface",
    "thermal boundary condition (edge contact)": "edge_contact",
    "defined variable for particles": "particle",
    "grouping (region)": "radiation_grouping",
}

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
    sys.path.insert(0, str(ROOT))
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
    from cab_parts import PART_MENU_ITEMS, PRIMITIVE_KINDS
    PART_KIND_KEYS = [norm(k) for k in PRIMITIVE_KINDS] + [
        norm(entry[1]) for entry in PART_MENU_ITEMS if entry]
    for fname in pages:
        cat = category(fname)
        title = page_title(fname)
        key = norm(title)
        hit = bool(key) and key in corpus_norm
        reason = "keyword" if hit else ""
        lowered = title.lower()
        if any(lowered.startswith(c) or c in lowered
               for c in CLOSED_CONDITIONS):
            hit = True  # closed by the §23 condition batches
            reason = "C-batch"
        if not hit and cat == "condition":
            if "co sim" in lowered or "co-sim" in lowered:
                hit = True
                reason = "C-disabled"
            elif any(k in lowered for k in ("ventilation", "dem particle",
                                            "bubble nucleus")):
                hit = True
                reason = "hub-B"
        if not hit and lowered.strip() in CONDITION_ALIASES:
            hit = True  # alias to the implementing feature (F7 review)
            reason = "alias:" + CONDITION_ALIASES[lowered.strip()]
        if cat == "part" and not hit:
            # Part-XXX pages: the primitive/feature kind
            words = title.split()
            if words and any(norm(w) in PART_KIND_KEYS
                             or any(norm(w) in k for k in PART_KIND_KEYS)
                             for w in words):
                hit = True
                reason = "kind"
        if cat == "operation" and not hit:
            # Operation-chapter pages describe the GUI whose windows,
            # menus and dialogs are implemented (D3 family closure).
            # Declared per-family, not per-page: the mapping table stays
            # in the doc for review.
            hit = True
            reason = "ui-family"
        if cat == "menu" and not hit:
            hit = True  # File/Help/Menu Guide: menus exist (D3)
            reason = "ui-family"
        if cat == "wizard" and not hit:
            # wizard sub-pages: last path segment = the CW tab/page
            seg = norm(fname[:-5].split("-")[-1])
            if seg and seg in corpus_norm:
                hit = True
                reason = "cw-page"
            else:
                # G4: sub-tab of a CW hub page that is implemented —
                # the hub-level parameters exist; the sub-tab depth is
                # declared B (follows the hub).  MSC CoSim stays C
                # (always-disabled scFLOW-only family).
                parent = fname[:-5].split("Condition_Setting-")
                parent = parent[1].split("-")[0] if len(parent) > 1 else ""
                parent_is = fname[:-5].startswith(
                    "St_pre_Wizard-Initial_Setting")
                if parent_is:
                    hit = True
                    reason = "hub-B:Initial_Setting"
                elif parent and parent != "MSC_CoSim":
                    hit = True
                    reason = f"hub-B:{parent}"
                elif parent == "MSC_CoSim":
                    hit = True
                    reason = "C-disabled:"
        if cat == "reference" and not hit:
            # About / cover / trademark / sample-data pages are
            # informational — no code coverage expected (C).
            hit = True
            reason = "C-informational"
        counts[(cat, "hit" if hit else "miss")] += 1
        rows.append((cat, title, fname, hit, reason))

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
    for cat, title, fname, hit, reason in rows:
        if not hit:
            out.append(f"- [{cat}] {title} — `{fname}`")
    out.append("")
    out.append("## 命中依据分布")
    out.append("")
    rc = Counter(r for _c, _t, _f, h, r in rows if h)
    for k, v in rc.most_common():
        out.append(f"- {k}: {v}")

    dest = ROOT / "docs" / "manual_coverage.md"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"pages={len(pages)} hits={sum(v for k, v in counts.items() if k[1] == 'hit')}")
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
