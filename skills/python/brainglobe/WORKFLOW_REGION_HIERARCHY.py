# imagentj-env: brainglobe
"""
WORKFLOW: roll fine-grained region counts up to a coarser anatomical level.

RUNS IN THE brainglobe ENV (magic comment on line 1). No pandas/seaborn/scipy here.

WHY THIS EXISTS: a per-cell region assignment lands in LEAF regions ("VISp2/3",
"VISp5", ...). Nobody wants a bar chart with 400 bars. The correct way to aggregate is
`structure_id_path` — the root->leaf id list — NOT string matching on acronyms.

    atlas.structures["VISp"]["structure_id_path"]
    -> [997, 8, 567, 688, 695, 315, 669, 385]
         root                          ^ Isocortex   ^ VISp

A region R is inside region P iff P's id appears in R's structure_id_path.

Verified end-to-end against allen_mouse_100um.
"""
import csv
import os

import numpy as np
from brainglobe_atlasapi import BrainGlobeAtlas

# ─────────────────────────── CONFIG ───────────────────────────
ATLAS_NAME = "allen_mouse_100um"
INPUT_CSV = "Cells_By_Region.csv"     # produced by WORKFLOW_CELLS_BY_REGION.py
OUTPUT_CSV = "Region_Counts_Rolled_Up.csv"

# The coarse regions to aggregate into, by acronym. Every cell is attributed to the
# FIRST of these that appears in its structure_id_path. Anything matching none of them
# is bucketed as "other".
TARGET_REGIONS = ["Isocortex", "HPF", "STR", "TH", "HY", "MB", "CB", "MY", "P"]
# ──────────────────────────────────────────────────────────────


def load_assignments(atlas):
    """Read structure ids from the per-cell CSV, or synthesise a set."""
    if os.path.exists(INPUT_CSV):
        ids = []
        with open(INPUT_CSV, newline="") as f:
            for row in csv.DictReader(f):
                ids.append(int(row["structure_id"]))
        return ids, False

    print(f"WARNING: {INPUT_CSV} not found — sampling synthetic cells from the atlas.")
    rng = np.random.default_rng(0)
    inside = np.argwhere(atlas.annotation > 0)
    picked = inside[rng.choice(len(inside), 300, replace=False)]
    return [int(atlas.annotation[tuple(p)]) for p in picked], True


def main():
    atlas = BrainGlobeAtlas(ATLAS_NAME)
    print(f"atlas {ATLAS_NAME}, {len(atlas.lookup_df)} structures defined")

    ids, synthetic = load_assignments(atlas)
    n_cells = len(ids)
    print(f"cells: {n_cells}")
    if n_cells == 0:
        raise ValueError("VERIFICATION FAILED: no cell assignments to roll up.")

    # Resolve the target acronyms to ids once.
    target_ids = {}
    for acr in TARGET_REGIONS:
        try:
            target_ids[acr] = atlas.structures[acr]["id"]
        except KeyError:
            print(f"WARNING: '{acr}' is not a region of {ATLAS_NAME} — skipping.")
    if not target_ids:
        raise ValueError(
            f"VERIFICATION FAILED: none of {TARGET_REGIONS} exist in {ATLAS_NAME}."
        )
    print(f"targets: {list(target_ids)}")

    counts = {acr: 0 for acr in target_ids}
    counts["other"] = 0
    counts["unassigned"] = 0

    for sid in ids:
        if sid == 0:
            counts["unassigned"] += 1
            continue
        try:
            path = atlas.structures[sid]["structure_id_path"]
        except KeyError:
            # Real atlases resolve every annotation id. The toy example_mouse_100um
            # does not — which is why you must not develop against it.
            counts["unassigned"] += 1
            continue
        for acr, tid in target_ids.items():
            if tid in path:                 # membership in the root->leaf path
                counts[acr] += 1
                break
        else:
            counts["other"] += 1

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["region", "region_name", "n_cells", "fraction"])
        for acr in list(target_ids) + ["other", "unassigned"]:
            name = (atlas.structures[acr]["name"] if acr in target_ids else acr)
            writer.writerow([acr, name, counts[acr], counts[acr] / n_cells])

    print("\nrolled-up counts:")
    for acr, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n:
            print(f"  {acr:12s} {n:4d}  ({n / n_cells:.1%})")

    # Demonstrate the hierarchy test the aggregation relies on.
    if "VISp" in atlas.structures and "Isocortex" in target_ids:
        visp = atlas.structures["VISp"]
        print(f"\nsanity: VISp path = {visp['structure_id_path']}")
        print(f"        Isocortex id {target_ids['Isocortex']} in path -> "
              f"{target_ids['Isocortex'] in visp['structure_id_path']}")
        # expand_tree returns a GENERATOR — list() before len()
        n_desc = len(list(atlas.structures.tree.expand_tree(visp["id"])))
        print(f"        VISp descendants: {n_desc}")

    # ── verification: invariants ──
    total = sum(counts.values())
    if total != n_cells:
        raise ValueError(f"VERIFICATION FAILED: counts sum to {total}, expected {n_cells}")
    if any(v < 0 for v in counts.values()):
        raise ValueError("VERIFICATION FAILED: negative count")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")

    frac_other = (counts["other"] + counts["unassigned"]) / n_cells
    if frac_other > 0.5:
        print(f"WARNING: {frac_other:.1%} of cells fall outside every target region. "
              f"Widen TARGET_REGIONS, or check the upstream assignment.")

    print(f"\nwrote {OUTPUT_CSV}" + (" [SYNTHETIC DATA]" if synthetic else ""))
    print("Next: a MAIN-env script reads it for statistics and plotting.")


if __name__ == "__main__":
    main()
