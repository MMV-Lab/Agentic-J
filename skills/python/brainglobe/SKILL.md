---
name: brainglobe
description: >-
  BrainGlobe gives programmatic access to 205 versioned neuroanatomical atlases (allen_mouse_10/
  25/50/100um, allen_human_500um, kim_mouse, whs_sd_rat_39um, mpin_zfish_1um) and registers
  whole-brain volumes to them with brainreg. Use it to look up which brain region a coordinate or
  segmented cell falls in, get region names/acronyms/hierarchy from structure ids, roll leaf
  counts up to coarser regions via structure_id_path, fetch annotation and reference volumes and
  3D meshes, and convert anatomical orientations with brainglobe_space. CRITICAL: brainglobe
  lives in its OWN conda env — a script MUST start with the magic comment
  `# imagentj-env: brainglobe`, and that env has NO pandas/seaborn/scipy and no preamble, so
  import everything you use and hand results off as CSV for a separate main-env script to analyse
  and plot. Atlases download on first use (needs network). This is the headless install: NO napari
  viewer, NO brainrender, NO cellfinder. Use ONLY for atlas neuroanatomy, not general image
  processing.
---

# BrainGlobe — Documentation Index

Atlas-based neuroanatomy: map coordinates and segmented objects onto a named brain
region, and register whole-brain volumes to a reference atlas.
**brainglobe-atlasapi 2.3.1**, 205 atlases.

## ⚠️ This skill runs in a separate conda env

The full brainglobe stack conflicts with the main env (napari + PyQt6 + vtk vs the main
env's PySide6, 7.2 GB). It is installed separately, headless. **Every brainglobe script
must begin with:**

```python
# imagentj-env: brainglobe
```

Consequences you must plan for:
- **No pre-imported preamble.** There is no `pd`, `np`, `plt`, `sns`, `stats`. Import
  everything you use.
- **`pandas`, `seaborn` and `scipy` are not installed here.** Use `csv` + `numpy`.
- **Never plot here.** Write CSV, then let a normal main-env script do the statistics
  and the figures (see the `statistics` and `plotting` skills).
- Installed: `brainglobe-atlasapi`, `brainglobe-space`, `brainglobe-utils`, `brainreg`.
  **Not** installed: `napari`, `brainrender`, `cellfinder`. Do not import them.

## Atlases download on first use

The first `BrainGlobeAtlas("allen_mouse_25um")` downloads to `~/.brainglobe` (persisted
across restarts) and **requires network access**. `allen_mouse_100um` is 61 MB; `25um`
has ~60× more voxels. **Prefer the coarsest resolution that answers the question.**

Do **not** develop against `example_mouse_100um` — it keeps full Allen ids in its
`annotation` but defines only 3 structures, so `atlas.structures[sid]` raises `KeyError`
for nearly every voxel. On the real `allen_mouse_100um` all 669 annotation ids resolve.

## The pattern — coordinate → brain region

```python
# imagentj-env: brainglobe
import csv
import numpy as np
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_100um")
print(atlas.shape, atlas.resolution, atlas.orientation)   # (132,80,114) (100,100,100) asr

for z, y, x in cells.astype(int):          # voxel coords in ATLAS space, (z, y, x)
    sid = atlas.annotation[z, y, x]        # 0 = outside / unannotated
    if sid == 0:
        acronym, name = "root", "outside_brain"
    else:
        s = atlas.structures[sid]
        acronym, name = s["acronym"], s["name"]
```

Then a **separate main-env script** reads the CSV, counts cells per region, and plots.

## Coordinates: the two things that go wrong

1. **Voxels vs microns.** `atlas.annotation` is indexed in **voxels**. Micron
   coordinates must be divided by `atlas.resolution` first.

2. **Axis order and orientation.** Atlas arrays are `(Z, Y, X)`, and each atlas declares
   a 3-letter origin code naming the anatomical direction each axis **starts from** —
   `'asr'` = anterior, superior, right. Don't transpose by hand:
   ```python
   from brainglobe_space import AnatomicalSpace
   source = AnatomicalSpace("ial", shape=my_stack.shape)
   mapped = source.map_points_to(atlas.orientation, points)   # or map_stack_to
   ```

**Both bugs are the same bug seen from different sides:** dividing when you shouldn't
collapses coordinates toward the origin, so nearly every cell reports `root`; forgetting
to divide overshoots `atlas.shape`, so you get an IndexError. Check units and orientation
before suspecting the atlas.

## Region hierarchy

`structure_id_path` is the root→leaf id list, and membership in it is the correct
"is R inside P" test — never string-match acronyms.

```python
s = atlas.structures["VISp"]
s["structure_id_path"]                       # [997, 8, 567, 688, 695, 315, 669, 385]
iso = atlas.structures["Isocortex"]["id"]
iso in s["structure_id_path"]                # True

list(atlas.structures.tree.expand_tree(s["id"]))   # expand_tree is a GENERATOR
```

`atlas.structures` is keyed by both integer id and acronym, but `.keys()` does not
enumerate them — use `atlas.lookup_df` (columns `acronym`, `id`, `name`).

## Registration

`brainreg` is a CLI. `--orientation` describes the **sample**, not the atlas, and `-v`
gives voxel size in microns in the same axis order as the orientation string.
Registration takes minutes to tens of minutes on a whole-brain volume.

```bash
brainreg sample.tif output_dir/ -v 5 2 2 --orientation asl --atlas allen_mouse_25um
```

## Files

| File | What it covers |
|---|---|
| `ATLAS_API.md` | Atlas inventory by species, the verified `BrainGlobeAtlas` attribute table, structure hierarchy, orientation codes, the two coordinate failure signatures, brainreg CLI |
| `WORKFLOW_CELLS_BY_REGION.py` | Cell coordinates → named region per cell → CSV + per-region counts. Handles units and orientation, and fails loudly on out-of-bounds |
| `WORKFLOW_REGION_HIERARCHY.py` | Roll leaf-region counts up to coarse regions (Isocortex, HPF, STR, TH, …) via `structure_id_path` |

Both workflows run untouched: they sample synthetic cells from a real downloaded atlas,
so you can see genuine anatomy in the output before supplying your own coordinates.
