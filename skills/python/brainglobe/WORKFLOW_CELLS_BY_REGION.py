# imagentj-env: brainglobe
"""
WORKFLOW: cell coordinates -> named brain region per cell -> CSV.

RUNS IN THE brainglobe ENV. The magic comment on line 1 is REQUIRED — it selects
/opt/conda/envs/brainglobe. Consequences:
  - NO pre-imported pd/np/plt/sns/stats. Import everything you use.
  - pandas, seaborn and scipy are NOT INSTALLED here. This script uses csv + numpy only.
  - NEVER plot here. Write CSV; a separate main-env script does stats and figures.

THE TWO WAYS COORDINATES GO WRONG (both silent):
  1. VOXELS vs MICRONS. atlas.annotation is indexed in VOXELS. Divide micron
     coordinates by atlas.resolution first.
  2. ORIENTATION. Atlas arrays are (Z, Y, X) and each atlas declares a 3-letter origin
     code (allen_mouse_* is 'asr'). If your coordinates come from a differently
     oriented stack, map them with brainglobe_space — never transpose by hand.
  Every cell landing in 'root', or an IndexError, is almost always one of these two.

Verified end-to-end against allen_mouse_100um.
"""
import csv
import os

import numpy as np
from brainglobe_atlasapi import BrainGlobeAtlas
from brainglobe_space import AnatomicalSpace

# ─────────────────────────── CONFIG ───────────────────────────
ATLAS_NAME = "allen_mouse_100um"   # coarsest that answers the question; 100um = 61 MB
CELLS_NPY = "/app/data/cell_coords.npy"   # (N, 3) array
OUTPUT_CSV = "Cells_By_Region.csv"
COUNTS_CSV = "Region_Counts.csv"

# Units of CELLS_NPY: "voxels" (already atlas voxels) or "microns".
COORD_UNITS = "voxels"
# Orientation of the coordinate frame the cells came from. None = already in atlas
# orientation. Otherwise a 3-letter origin code, e.g. "ial", "psl".
SOURCE_ORIENTATION = None
# Shape of the source stack (Z, Y, X). Required when SOURCE_ORIENTATION is set,
# so axis flips can be resolved.
SOURCE_SHAPE = None
# ──────────────────────────────────────────────────────────────


def load_cells(atlas):
    if os.path.exists(CELLS_NPY):
        cells = np.load(CELLS_NPY)
        if cells.ndim != 2 or cells.shape[1] != 3:
            raise ValueError(f"VERIFICATION FAILED: expected (N,3), got {cells.shape}")
        return cells.astype(float), False

    print("WARNING: configured input not found — sampling synthetic cells inside the brain.")
    rng = np.random.default_rng(0)
    inside = np.argwhere(atlas.annotation > 0)
    picked = inside[rng.choice(len(inside), 300, replace=False)]
    return picked.astype(float), True


def to_atlas_voxels(cells, atlas):
    """Apply the orientation map, then the micron->voxel conversion."""
    if SOURCE_ORIENTATION is not None:
        if SOURCE_SHAPE is None:
            raise ValueError(
                "VERIFICATION FAILED: SOURCE_SHAPE is required when SOURCE_ORIENTATION is set."
            )
        source = AnatomicalSpace(SOURCE_ORIENTATION, shape=SOURCE_SHAPE)
        print(f"mapping points {SOURCE_ORIENTATION} -> {atlas.orientation}")
        cells = source.map_points_to(atlas.orientation, cells)

    if COORD_UNITS == "microns":
        cells = cells / np.array(atlas.resolution)
        print(f"converted microns -> voxels using resolution {atlas.resolution}")
    elif COORD_UNITS != "voxels":
        raise ValueError(f"VERIFICATION FAILED: COORD_UNITS must be 'voxels' or 'microns'")

    return np.rint(cells).astype(int)


def main():
    atlas = BrainGlobeAtlas(ATLAS_NAME)     # downloads on first use; needs network
    print(f"atlas {ATLAS_NAME}")
    print(f"  shape (Z, Y, X): {atlas.shape}")
    print(f"  resolution (um): {atlas.resolution}")
    print(f"  orientation    : {atlas.orientation}")

    cells, synthetic = load_cells(atlas)
    n_cells = len(cells)
    print(f"cells: {n_cells}")
    if n_cells == 0:
        raise ValueError("VERIFICATION FAILED: no cells to assign.")

    vox = to_atlas_voxels(cells, atlas)

    # Out-of-bounds means the orientation or the unit conversion is wrong. Fail on it
    # rather than silently clipping cells onto the brain surface.
    shape = np.array(atlas.shape)
    oob = ((vox < 0) | (vox >= shape)).any(axis=1)
    if oob.any():
        bad = vox[oob][:3]
        raise ValueError(
            f"VERIFICATION FAILED: {oob.sum()}/{n_cells} coordinates fall outside the "
            f"atlas {tuple(atlas.shape)}. First offenders: {bad.tolist()}. "
            f"Check COORD_UNITS ({COORD_UNITS}) and SOURCE_ORIENTATION "
            f"({SOURCE_ORIENTATION}) against the atlas orientation '{atlas.orientation}'."
        )

    rows = []
    for z, y, x in vox:
        sid = int(atlas.annotation[z, y, x])
        if sid == 0:
            acronym, name = "root", "outside_brain_or_unannotated"
        else:
            struct = atlas.structures[sid]
            acronym, name = struct["acronym"], struct["name"]
        rows.append({"z": int(z), "y": int(y), "x": int(x),
                     "structure_id": sid, "acronym": acronym, "name": name})

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # per-region counts, the table the plotting stage actually wants
    counts = {}
    for r in rows:
        key = (r["acronym"], r["name"])
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    with open(COUNTS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["acronym", "name", "n_cells", "fraction"])
        for (acr, nm), n in ordered:
            writer.writerow([acr, nm, n, n / n_cells])

    print(f"\ntop regions:")
    for (acr, nm), n in ordered[:5]:
        print(f"  {acr:10s} {n:4d}  {nm[:44]}")

    # ── verification: invariants that are ALWAYS true for a correct run ──
    if len(rows) != n_cells:
        raise ValueError(f"VERIFICATION FAILED: {len(rows)} rows for {n_cells} cells")
    if sum(counts.values()) != n_cells:
        raise ValueError("VERIFICATION FAILED: region counts do not sum to N")
    for path in (OUTPUT_CSV, COUNTS_CSV):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    # Unassigned cells can be genuine (debris, sectioning artefacts) — but a high
    # fraction is the classic symptom of an orientation bug. Report, never assert.
    frac_root = sum(1 for r in rows if r["acronym"] == "root") / n_cells
    print(f"\nunassigned ('root') fraction: {frac_root:.3f}")
    if frac_root > 0.5:
        print("WARNING: most cells are unassigned. Verify SOURCE_ORIENTATION and "
              "COORD_UNITS before trusting this — an orientation bug looks exactly "
              "like this.")

    print(f"wrote {OUTPUT_CSV} and {COUNTS_CSV}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))
    print("Next: a MAIN-env script reads Region_Counts.csv for statistics and plotting.")


if __name__ == "__main__":
    main()
