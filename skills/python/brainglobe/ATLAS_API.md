# BrainGlobe — Atlas API

Verified against **brainglobe-atlasapi 2.3.1** in the isolated env
`/opt/conda/envs/brainglobe`. Atlas facts below were read from a downloaded
`allen_mouse_100um`.

> **Every script using this API must begin with `# imagentj-env: brainglobe`.**
> There is no pandas/seaborn/scipy in that env and no pre-imported preamble.

## What is installed

`brainglobe-atlasapi`, `brainglobe-space`, `brainglobe-utils`, `brainreg`.

**Not installed** (headless build): `napari`, `brainrender`, `cellfinder`,
`brainglobe-segmentation`. Do not import them.

## Listing atlases

```python
from brainglobe_atlasapi.list_atlases import (
    get_all_atlases_lastversions,   # dict[name -> version]; 205 atlases
    get_downloaded_atlases,         # list[str] already on disk
)
```

205 atlases are available. Counted by keyword:

| Species | N | Examples |
|---|---|---|
| mouse | 188 | `allen_mouse_10um`, `allen_mouse_25um`, `allen_mouse_50um`, `allen_mouse_100um`, `kim_mouse_*`, `admba_3d_*` |
| rat | 4 | `whs_sd_rat_39um`, `swc_female_rat_50um`, `african_molerat_20um` |
| fish | 4 | `mpin_zfish_1um`, `azba_zfish_4um`, `sju_cavefish_2um`, `columbia_cuttlefish_50um` |
| human | 1 | `allen_human_500um` |
| other | — | `drosophila_wingdisc_instar3_2um`, … |

There is **no** macaque or *Drosophila* brain atlas in this set.

## Downloads

The first `BrainGlobeAtlas("allen_mouse_25um")` downloads the atlas to `~/.brainglobe`
(persisted across container restarts) and **requires network access**. Sizes:
`allen_mouse_100um` is 61 MB; `25um` is ~60× more voxels.

**Prefer the coarsest resolution that answers the question.** If you are assigning cells
to named regions, `100um` or `50um` is almost always enough.

> **Never develop against `example_mouse_100um`.** It is a toy atlas that keeps full
> Allen ids in `annotation` but defines only **3** structures, so `atlas.structures[sid]`
> raises `KeyError` for nearly every voxel. On the real `allen_mouse_100um` all **669**
> ids present in `annotation` resolve.

## `BrainGlobeAtlas` attributes

```python
from brainglobe_atlasapi import BrainGlobeAtlas
atlas = BrainGlobeAtlas("allen_mouse_100um")
```

| Attribute | Verified value / type |
|---|---|
| `atlas.shape` | `(132, 80, 114)` — `(Z, Y, X)` voxels |
| `atlas.resolution` | `(100.0, 100.0, 100.0)` — microns per voxel |
| `atlas.orientation` | `'asr'` — a 3-letter origin code |
| `atlas.annotation` | `uint32 (Z, Y, X)`; structure id per voxel, `0` = unannotated |
| `atlas.reference` | the template anatomy volume, same shape |
| `atlas.hemispheres` | hemisphere id per voxel, same shape |
| `atlas.structures` | dict-like, keyed by **integer id AND acronym** |
| `atlas.lookup_df` | DataFrame, columns `['acronym', 'id', 'name']`, 840 rows |
| `atlas.mesh_from_structure("VISp")` | a `Mesh` object |

**`atlas.structures.keys()` does not enumerate the regions** — it returns a short
internal list. Use `atlas.lookup_df` to list regions.

## Structure records and hierarchy

```python
s = atlas.structures["VISp"]          # by acronym, or by integer id
s["id"]                                # 385
s["acronym"], s["name"]
s["structure_id_path"]                 # [997, 8, 567, 688, 695, 315, 669, 385]
```

`structure_id_path` is the **root→leaf id list**. Testing membership in it is the
correct way to ask "is this region inside that one", and it is how you roll leaf counts
up to a coarser level:

```python
iso_id = atlas.structures["Isocortex"]["id"]
inside = iso_id in atlas.structures[sid]["structure_id_path"]      # True for VISp
```

Descendants of a region:
```python
descendants = list(atlas.structures.tree.expand_tree(s["id"]))     # VISp -> 7
```
**`expand_tree` returns a generator** — wrap it in `list()` before `len()` or indexing.

## Coordinates: the two things that go wrong

### 1. Voxels vs microns

`atlas.annotation` is indexed in **voxels**. Cell coordinates in microns must be divided
by the resolution first:

```python
vox = (coords_um / np.array(atlas.resolution)).astype(int)
```

### 2. Axis order and orientation

Atlas arrays are `(Z, Y, X)`. Every atlas declares a 3-letter origin code
(`atlas.orientation`), naming the anatomical direction each axis *starts from*:
`'asr'` = **a**nterior, **s**uperior, **r**ight. `AnatomicalSpace('asr').axes_description`
returns `('ap', 'si', 'rl')`.

Do **not** transpose by hand. Use `brainglobe_space`:

```python
from brainglobe_space import AnatomicalSpace

source = AnatomicalSpace("ial", shape=my_stack.shape)   # your data's orientation
mapped_stack = source.map_stack_to(atlas.orientation, my_stack)
mapped_points = source.map_points_to(atlas.orientation, points)   # (N, 3) array
```

`AnatomicalSpace(origin, shape=None, resolution=None, offset=(0,0,0))`.
`map_points_to(target, pts, infer_source_shape=False)` — pass `shape` to the constructor
so axis flips are computed correctly; verified `(10,20,30)` `ial` → `asr` gives shape
`(20,10,30)`.

### The two failure signatures

A units/orientation bug shows up in exactly one of two ways, depending on direction —
verified by deliberately mis-setting the unit flag:

| Mistake | Symptom |
|---|---|
| dividing voxel coords by resolution (treating voxels as microns) | coords collapse toward the origin, land outside the annotation → **almost every cell is `root`** |
| forgetting to divide micron coords | coords overshoot `atlas.shape` → **IndexError / out-of-bounds** |

So: **an out-of-bounds crash and a wall of `root` are the same bug**, seen from
different sides. Neither means the atlas is broken. Check `COORD_UNITS` and the
orientation before anything else.

## Registration with `brainreg`

`brainreg` is installed and exposes a CLI. Registration of a whole-brain volume takes
minutes to tens of minutes and is memory-hungry; it is not something to run speculatively.

```bash
brainreg /path/to/sample.tif /path/to/output_dir \
    -v 5 2 2 --orientation psl --atlas allen_mouse_25um
```

- `-v` is voxel size in microns as `z y x`.
- `--orientation` describes the **sample**, not the atlas.
- The output directory receives the sample registered into atlas space plus the inverse
  transform — which is what you then use to push cell coordinates into atlas space for
  the region-lookup workflow.

There is no runnable workflow file for `brainreg` in this skill: it needs a real
whole-brain volume and a long runtime, so nothing here could be honestly verified.

## Verification

RAISE on invariants always true for a correct run: the output CSV exists and is
non-empty; every coordinate lies within `atlas.shape`; the number of output rows equals
the number of input cells.

WARN — do not raise — when many cells land in `root` / outside the brain. That can be
genuine (debris, sectioning artefacts), though it is also the classic symptom of an
orientation bug, so always print the fraction.

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | When to use brainglobe, the env rule, the coordinate traps |
| `ATLAS_API.md` | This file — atlas inventory, attribute table, hierarchy, orientation, brainreg CLI |
| `WORKFLOW_CELLS_BY_REGION.py` | Cell coordinates → named brain region per cell → CSV, plus per-region counts |
| `WORKFLOW_REGION_HIERARCHY.py` | Roll leaf-region counts up to a coarser anatomical level using `structure_id_path` |
