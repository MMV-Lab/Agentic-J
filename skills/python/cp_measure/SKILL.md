---
name: cp_measure
description: >-
  cp_measure extracts the full CellProfiler feature battery (271 features) from a label image
  plus an intensity image, as a dict of numpy arrays — no CellProfiler install, no pipeline XML,
  no second JVM. In the MAIN env; `from cp_measure.bulk import get_core_measurements`. Use it
  for rich morphology/intensity/texture phenotyping beyond skimage regionprops_table: Zernike
  moments, Haralick texture, granularity, radial distribution, Feret diameters. CRITICAL
  PITFALLS: a FLOAT intensity image must be scaled into [0,1] or texture raises "Images of type
  float must be between -1 and 1" (uint8/uint16 are fine as-is); a BOOLEAN mask is silently ONE
  object, so always pass an integer LABEL image; keep the default sanitize=True or gapped label
  ids crash. Also provides get_core_measurements_3d, get_correlation_measurements (pearson,
  costes, manders_fold, rwc), get_multimask_measurements (neighbors, overlap).
---

# cp_measure — Documentation Index

`cp_measure` gives you **CellProfiler's measurement engine as a Python function**.
You hand it a label image and an intensity image; it hands back a dict of
`{feature_name: np.ndarray}` with one value per object. No pipeline file, no
CellProfiler install, no second JVM.

Installed in the main env (`local_imagent_J`) — no env switch needed.

**When to use this vs. alternatives**
- **cp_measure (this skill)** — you want the deep feature battery: Haralick texture,
  Zernike moments, granularity, radial distribution. Phenotyping, clustering,
  classification.
- **skimage `regionprops_table`** — you want a handful of interpretable columns
  (area, perimeter, eccentricity, mean intensity). Faster and simpler.

## The one pattern you need

```python
import numpy as np
import pandas as pd
from cp_measure.bulk import get_core_measurements

# labels: integer LABEL image (0 = background). pixels: matching intensity image.
measurements = get_core_measurements()      # keep sanitize=True (the default)

results = {}
for name, fn in measurements.items():
    results.update(fn(labels, pixels))

df = pd.DataFrame(results)
df.insert(0, "label", np.unique(labels[labels > 0]))
df.to_csv("Measurements.csv", index=False)
```

Every function has the same signature: `fn(masks, pixels) -> dict[str, np.ndarray]`.
Arrays are ordered by ascending label id, so `df` rows align with
`np.unique(labels[labels > 0])`.

## The three pitfalls, in the order they bite

### 1. Float intensity images MUST be scaled to [0,1]

`texture` calls `skimage.util.img_as_ubyte`, which rejects floats outside `[-1, 1]`:

```
ValueError: Images of type float must be between -1 and 1.
```

This is exactly what you get after `img.astype(np.float64)` on a 16-bit image.

| Input | Works? |
|---|---|
| `uint8` / `uint16` raw | ✅ yes — pass it unchanged |
| `float` in `[0, 1]` | ✅ yes |
| `float` with raw 16-bit values (0…65535) | ❌ **ValueError** |

```python
if np.issubdtype(pixels.dtype, np.floating) and pixels.max() > 1.0:
    pixels = pixels / pixels.max()      # or: skimage.util.img_as_float(img_uint16)
```

Simplest safe rule: **leave integer images as integers.** Only convert to float if you
also normalise.

### 2. A boolean mask is silently ONE object

Passing `labels > 0` does not raise — it measures the entire foreground as a single
object and returns one row. The bug shows up as "why do I have 1 cell instead of 300?"

```python
assert labels.dtype != bool, "pass an integer LABEL image, not a boolean mask"
```
Get labels from `skimage.measure.label(binary)` or a segmentation model.

### 3. Keep `sanitize=True` (the default)

With `sanitize=False`, gapped label ids (e.g. `[1, 3, 7]` after
`remove_small_objects`) crash with `TypeError: 'NoneType' object is not subscriptable`.
The default `sanitize=True` handles gaps for you — **do not turn it off.**
If you must, relabel first:
```python
from skimage.segmentation import relabel_sequential
labels, _, _ = relabel_sequential(labels)
```

## What you get — 271 features in 8 groups

| Group | N | Needs intensity? |
|---|---|---|
| `sizeshape` | 78 | no |
| `radial_zernikes` | 60 | yes |
| `texture` | 52 | yes |
| `zernike` | 30 | no |
| `intensity` | 21 | yes |
| `granularity` | 16 | yes |
| `radial_distribution` | 12 | yes |
| `feret` | 2 | no |

`fn(labels, None)` works for the shape-only groups — `sizeshape` alone returns 78
features with no intensity image.

To compute a subset, just pick keys:
```python
m = get_core_measurements()
shape_only = {k: m[k] for k in ("sizeshape", "zernike", "feret")}
```

## Other entry points

```python
from cp_measure.bulk import (
    get_core_measurements,        # 1 label image + 1 intensity image
    get_core_measurements_3d,     # same, for (Z, Y, X) volumes
    get_correlation_measurements, # 2 intensity channels, same labels
    get_multimask_measurements,   # 2 label images
)
```

- **Colocalisation** — `get_correlation_measurements()` → `pearson`, `costes`,
  `manders_fold`, `rwc`. Signature: **`fn(pixels_1, pixels_2, masks)`** — labels come
  **LAST** here, the opposite of the core measurements. Passing `fn(labels, ch1, ch2)`
  does not raise; it silently returns numbers computed from the wrong arrays.
  `costes` is the slowest call in the library — skip it unless asked.
- **Object relationships** — `get_multimask_measurements()` → `neighbors`, `overlap`.
  Signature: `fn(masks1, masks2)`. `overlap` returns **image-level scalars**
  (RandIndex, Precision, Recall …) for comparing a segmentation against ground truth;
  `neighbors` returns per-object features.

## Units

Features are in **pixels** (`Area` is px²). Convert with the pixel size from PROJECT
STATE, exactly as for `regionprops` — see the `scikit_image` skill.

## Handing off

cp_measure output is a per-object feature table: the natural input to the
`scikit_learn` skill (scale it, then cluster/classify) and then the `statistics` and
`plotting` skills. Write it to CSV; do not carry it in memory across scripts.

## Files

| File | What it covers |
|---|---|
| `SCRIPT_API.md` | Every function, default and feature name — introspected from the installed build. All 271 core features enumerated, the 3D subset, correlation and multimask, argument-order trap, measured timings |
| `WORKFLOW_MEASURE_LABELS.py` | Label + intensity image → 271-feature CSV. Enforces the bool-mask and float-range contracts, converts px→μm, verifies invariants |
| `WORKFLOW_COLOCALIZATION.py` | Two channels + labels → per-object Pearson/Manders/RWC CSV. Demonstrates the reversed argument order |

Both workflows run untouched on synthetic data, so you can see the output shape before
pointing them at real files.
