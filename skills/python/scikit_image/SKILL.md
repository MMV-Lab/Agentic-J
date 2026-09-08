---
name: scikit_image
description: >-
  scikit-image (skimage) is the general-purpose Python image-processing library in the MAIN env
  (local_imagent_J) — import as `skimage`, no install needed. Use it for filtering (gaussian,
  median, sobel, frangi), thresholding (threshold_otsu, threshold_local, threshold_multiotsu),
  morphology (closing, opening, remove_small_objects, skeletonize, disk/ball footprints),
  labelling and instance measurement (measure.label, measure.regionprops_table), watershed
  splitting of touching objects, and rigid registration (phase_cross_correlation). CRITICAL:
  regionprops area/perimeter are in PIXELS — pass spacing= or multiply by the PROJECT STATE pixel
  size; regionprops RAISES on a boolean mask, so run measure.label first; filters.gaussian
  rescales to [0,1] unless preserve_range=True; and in 0.26 binary_closing/binary_opening are
  deprecated and min_size became max_size with a different boundary. Use skimage for scientific
  (float, 16-bit, 3D/ND) image data.
---

# scikit-image — Documentation Index

`skimage` is the **default** image-processing library for this agent. Installed in the
main env (`local_imagent_J`) — no env switch, no install. Version **0.26.0**.

**When to use this vs. alternatives**
- **scikit-image (this skill)** — scientific images: float or 16-bit data, 3D/ND
  stacks, quantitative measurement. The default choice.
- **cp_measure** — the full CellProfiler feature battery on a label image (271
  features), not a handful of regionprops columns.

## The pattern — segment, label, measure

```python
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage import io, filters, feature, measure, morphology, segmentation

img = io.imread('/app/data/cells.tif')          # preserves 16-bit / float dtype

# 1. Smooth, then threshold. preserve_range or intensities are destroyed.
smooth = filters.gaussian(img, sigma=1.0, preserve_range=True)
binary = smooth > filters.threshold_otsu(smooth)

# 2. Clean up. NOT binary_closing (deprecated); NOT min_size (deprecated).
binary = morphology.remove_small_objects(binary, max_size=64)
binary = morphology.closing(binary, morphology.disk(2))

# 3. Split touching objects (watershed on the distance transform)
distance = ndi.distance_transform_edt(binary)
coords = feature.peak_local_max(distance, min_distance=7, labels=binary)
markers = np.zeros(distance.shape, dtype=bool)
markers[tuple(coords.T)] = True
markers, n_seeds = ndi.label(markers)
labels = segmentation.watershed(-distance, markers, mask=binary)

# 4. Measure. spacing= converts to microns directly.
df = pd.DataFrame(measure.regionprops_table(
    labels, intensity_image=img,
    properties=('label', 'area', 'perimeter', 'eccentricity',
                'intensity_mean', 'centroid'),
    spacing=(0.325, 0.325),          # omit for pixel units
))
```

## Pitfalls that have actually bitten

1. **`regionprops` returns PIXEL units.** `area` is px², `perimeter` is px. Pass
   `spacing=(dy, dx)`, or convert: `df['area_um2'] = df['area'] * (0.325 ** 2)`.
   Never report bare `area` as μm².

2. **A boolean mask RAISES** — `TypeError: Non-integer image types are ambiguous`.
   The message suggests `.astype(np.uint8)`; **do not** — that merges every object into
   one label. Use `measure.label(binary)`. (cp_measure, by contrast, accepts a bool mask
   and silently measures ONE object without raising.)

3. **`filters.gaussian` rescales to [0,1] by default.** A constant 1000-valued image
   comes back with max `0.0153`. Pass `preserve_range=True` whenever you keep intensities.

4. **0.26 deprecations** (they fire `FutureWarning` now, break in 2.0):
   `binary_closing`→`closing`, `binary_opening`→`opening`,
   `remove_small_objects(min_size=N)`→`(max_size=N)`. The rename also moved the
   boundary: `max_size=N` removes area **≤ N**, `min_size=N` removed area **< N**.
   And `remove_small_objects` defaults to `max_size=64` — calling it with no size
   argument deletes every object of 64 px or smaller.

5. **`min_distance` in `peak_local_max` is a sharp knob.** On three synthetic spheres:
   `min_distance=5` → 12 seeds, `=7` → 3 seeds (correct), `=12` → **0 seeds**, and
   watershed with no markers silently returns one label for everything. Compare your
   seed count to `ndi.label(binary)[1]`.

6. **3D**: footprints must be `morphology.ball`, not `disk`. Pass `spacing=(dz, dy, dx)`
   or the volume is wrong. `eccentricity` and `perimeter` raise `NotImplementedError` on
   3D labels — everything else works.

7. **`io.imread` on a multi-page TIFF returns a `(Z, Y, X)` array**, not a list. For
   OME-TIFF metadata (pixel size, channel names) use `tifffile` directly.

## Choosing a threshold

`threshold_otsu` for a bimodal histogram; `threshold_local(img, block_size=35, offset=10)`
for uneven illumination (`block_size` must be **odd**); `threshold_multiotsu(img, classes=3)`
for three or more populations. `filters.try_all_threshold(img)` compares six methods at
once — use it interactively, not in a production script.

## Registration

`phase_cross_correlation` does **rigid translation only**. Its returned `error` is not a
quality score (it sits near 1.0 even for a perfect match) — don't threshold on it. For
rotation, scale, or elastic deformation, use the Fiji TurboReg/StackReg plugins via the
Groovy coder.

## Files

| File | What it covers |
|---|---|
| `SCRIPT_API.md` | Verified signatures, the complete `regionprops_table` property lists (shape-only vs intensity-requiring), the threshold menu, the 0.26 deprecation table, `min_distance` tuning data |
| `WORKFLOW_SEGMENT_MEASURE.py` | 2D: threshold → clean → watershed → `regionprops_table` → CSV + label TIFF, with μm conversion and over-segmentation guard |
| `WORKFLOW_3D_STACK.py` | 3D: `ball` footprints, anisotropic `spacing`, the 2D-only properties omitted |
| `WORKFLOW_REGISTRATION.py` | Rigid drift correction of a `(T, Y, X)` stack; recovers known shifts exactly |

All three workflows run untouched on synthetic data, so you can see the output before
pointing them at real files.
