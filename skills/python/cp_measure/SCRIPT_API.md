# cp_measure — Python Script API

Every identifier and default below was introspected from the installed build
(`cp_measure @ git+https://github.com/afermg/cp_measure.git`, main env
`/opt/conda/envs/local_imagent_J`). Feature counts were produced by running each
function on a 2-object label image.

> **This is the GitHub API.** The PyPI package `cp-measure` exposes an older
> `featurize()` function with a `(C, H, W)` shape contract. It is NOT what is installed.
> If you see `featurize` in a snippet, that snippet is for the wrong version.

## Entry points

```python
from cp_measure.bulk import (
    get_core_measurements,        # 1 label image + 1 intensity image  → 271 features
    get_core_measurements_3d,     # 3D volumes (Z, Y, X)               → 418 features
    get_correlation_measurements, # 2 intensity channels + 1 label image
    get_multimask_measurements,   # 2 label images
)
```

Each returns `dict[str, Callable]`. `get_core_measurements(legacy=False, sanitize=True)`.

**Keep `sanitize=True`.** With `sanitize=False`, gapped label ids (`[1, 3, 7]`) raise
`TypeError: 'NoneType' object is not subscriptable`.

## Argument order — the trap

The two families take arguments in **different orders**. Getting this wrong does not
raise; it returns numbers computed from the wrong arrays.

| Family | Signature |
|---|---|
| core | `fn(masks, pixels)` — **labels first** |
| core 3d | `fn(masks, pixels)` — labels first |
| correlation | `fn(pixels_1, pixels_2, masks)` — **labels LAST** |
| multimask | `fn(masks1, masks2)` |

## Return types

- core / core 3d → `dict[str, np.ndarray]`, one value per object.
- correlation → `dict[str, list[float]]`, one value per object (a **list**, not an array).
- multimask `overlap` → `dict[str, float]` — **image-level scalars**, not per-object.
- multimask `neighbors` → `dict[str, list]` — per-object.

Values are ordered by **ascending label id**, so they align with
`np.unique(labels[labels > 0])`.

---

## Core measurements (2D) — 271 features in 8 groups

### `sizeshape(masks, pixels, calculate_advanced=True, new_features=True, spacing=None)` → 78
Works with `pixels=None` (shape needs no intensity).
`spacing=(dy, dx)` gives physical units directly.

```
Area, BoundingBoxArea, BoundingBoxMaximum_X, BoundingBoxMaximum_Y,
BoundingBoxMinimum_X, BoundingBoxMinimum_Y, Center_X, Center_Y, Compactness,
ConvexArea, Eccentricity, EquivalentDiameter, EulerNumber, Extent, FilledArea,
FormFactor, MajorAxisLength, MinorAxisLength, MaximumRadius, MeanRadius,
MedianRadius, Orientation, Perimeter, PerimeterCrofton, Solidity,
CentralMoment_{0..2}_{0..3}, NormalizedMoment_{0..3}_{0..3},
SpatialMoment_{0..2}_{0..3}, HuMoment_{0..6},
InertiaTensor_{0..1}_{0..1}, InertiaTensorEigenvalues_{0..1}
```

### `intensity(masks, pixels, edge_measurements=True, legacy=False)` → 21
```
Intensity_IntegratedIntensity, Intensity_IntegratedIntensityEdge,
Intensity_LowerQuartileIntensity, Intensity_UpperQuartileIntensity,
Intensity_MADIntensity, Intensity_MassDisplacement,
Intensity_MaxIntensity, Intensity_MaxIntensityEdge,
Intensity_MeanIntensity, Intensity_MeanIntensityEdge,
Intensity_MedianIntensity, Intensity_MinIntensity, Intensity_MinIntensityEdge,
Intensity_StdIntensity, Intensity_StdIntensityEdge,
Location_CenterMassIntensity_{X,Y,Z}, Location_MaxIntensity_{X,Y,Z}
```
`Location_*_Z` is present but 0 for 2D input.

### `texture(masks, pixels, scale=3, gray_levels=256)` → 52
13 Haralick statistics × 4 directions (`_00`, `_01`, `_02`, `_03`). Names carry the
parameters: `Contrast_3_00_256` = statistic `Contrast`, `scale=3`, direction `00`,
`gray_levels=256`.
```
AngularSecondMoment, Contrast, Correlation, DifferenceEntropy, DifferenceVariance,
Entropy, InfoMeas1, InfoMeas2, InverseDifferenceMoment, SumAverage, SumEntropy,
SumVariance, Variance          (each × _00 _01 _02 _03)
```
**Texture is the function that rejects out-of-range floats** — it calls
`skimage.util.img_as_ubyte` internally. See Pitfalls.

### `zernike(masks, pixels, zernike_numbers=9)` → 30
`Zernike_{n}_{m}` for the 30 valid (n, m) pairs with n ≤ 9. Shape only — intensity unused.

### `radial_zernikes(labels, pixels, zernike_degree=9)` → 60
`RadialDistribution_ZernikeMagnitude_{n}_{m}` and
`RadialDistribution_ZernikePhase_{n}_{m}` — the same 30 pairs, magnitude + phase.

### `radial_distribution(labels, pixels, scaled=True, bin_count=4, maximum_radius=100)` → 12
```
RadialDistribution_FracAtD_{i}of4, RadialDistribution_MeanFrac_{i}of4,
RadialDistribution_RadialCV_{i}of4        for i in 1..4
```
Raising `bin_count` raises the feature count (3 × bin_count).

### `granularity(mask, pixels, subsample_size=0.25, image_sample_size=0.25, element_size=10, granular_spectrum_length=16)` → 16
`Granularity_1` … `Granularity_16`. Count equals `granular_spectrum_length`.
Note this one names its first parameter `mask` (singular) — positional order is unchanged.

### `feret(masks, pixels)` → 2
`MaxFeretDiameter`, `MinFeretDiameter`.

---

## Core measurements (3D) — `get_core_measurements_3d()`

Takes `(Z, Y, X)` label and intensity volumes. Only 4 groups exist:

| Group | Features |
|---|---|
| `sizeshape` | 212 |
| `texture` | 169 |
| `intensity` | 21 |
| `granularity` | 16 |

No `zernike`, `radial_zernikes`, `radial_distribution`, or `feret` in 3D.

---

## Correlation (colocalisation) — `get_correlation_measurements()`

**`fn(pixels_1, pixels_2, masks)`** — two intensity channels, one label image.
Returns per-object lists.

| Function | Signature | Returns |
|---|---|---|
| `pearson` | `(pixels_1, pixels_2, masks)` | `Correlation_Pearson`, `Correlation_Slope` |
| `manders_fold` | `(pixels_1, pixels_2, masks, thr=15)` | `Correlation_Manders_1`, `_2` |
| `rwc` | `(pixels_1, pixels_2, masks, thr=15)` | `Correlation_RWC_1`, `_2` |
| `costes` | `(pixels_1, pixels_2, masks, fast_costes='Faster', thr=15)` | `Correlation_Costes_1`, `_2` |

Verified sanity checks: identical channels → `Pearson = 1.0`; inverted channel
(`1 - a`) → `Pearson = -1.0`; independent noise → `Pearson ≈ 0`.

`costes` is by far the slowest measurement in the library. `fast_costes='Faster'` is the
default; leave it. Skip `costes` entirely unless the task explicitly asks for Costes'
automatic threshold.

---

## Multimask — `get_multimask_measurements()`

**`fn(masks1, masks2)`** — two label images.

### `overlap(masks1, masks2, wants_emd=False, max_points=250, decimation_method='K Means', max_distance=100, penalize_missing=False)`
Returns **9 image-level scalars** (not per-object) — this is a segmentation-agreement
metric, e.g. predicted masks vs ground truth:
```
Overlap_RandIndex, Overlap_AdjustedRandIndex, Overlap_Ffactor,
Overlap_Precision, Overlap_Recall,
Overlap_TruePosRate, Overlap_TrueNegRate, Overlap_FalsePosRate, Overlap_FalseNegRate
```
Verified: `overlap(lab, lab)["Overlap_RandIndex"] == 1.0`.

### `neighbors(masks1, masks2, distance_method='Expand until adjacent', distance=5)`
Returns 7 per-object features, suffixed `_Expanded`:
```
Neighbors_NumberOfNeighbors_Expanded, Neighbors_PercentTouching_Expanded,
Neighbors_FirstClosestObjectNumber_Expanded, Neighbors_FirstClosestDistance_Expanded,
Neighbors_SecondClosestObjectNumber_Expanded, Neighbors_SecondClosestDistance_Expanded,
Neighbors_AngleBetweenNeighbors_Expanded
```

---

## Pitfalls (all reproduced, not from docs)

### 1. Float intensity outside [0,1] → `ValueError` in `texture`
```
ValueError: Images of type float must be between -1 and 1.
```
Raised by `skimage.util.img_as_ubyte` inside `get_texture`. A 16-bit image cast to
float (`img.astype(np.float64)`, values 0…65535) triggers it.

| Input | Works? |
|---|---|
| `uint8` / `uint16` raw | ✅ pass unchanged |
| `float` in `[0, 1]` | ✅ |
| `float` with raw 16-bit values | ❌ ValueError |

```python
if np.issubdtype(pixels.dtype, np.floating) and pixels.max() > 1.0:
    pixels = pixels / pixels.max()
```
**Simplest rule: leave integer images as integers.**

### 2. A boolean mask is silently ONE object
`fn(labels > 0, px)` does not raise. It returns a single row for the whole foreground.
```python
assert labels.dtype != bool, "pass an integer LABEL image, not a boolean mask"
```

### 3. `sanitize=False` + gapped labels → `TypeError`
Keep the default. Or `labels, _, _ = skimage.segmentation.relabel_sequential(labels)`.

### 4. Correlation takes labels LAST
`pearson(labels, ch1, ch2)` runs and returns plausible-looking numbers that are wrong.
It is `pearson(ch1, ch2, labels)`.

### 5. Units are pixels
`Area` is px², `Perimeter` is px, `MaxFeretDiameter` is px. Convert with the pixel size
from PROJECT STATE, or pass `spacing=` to `sizeshape`.

## Performance — measured, and the README is wrong

Benchmark: 16 objects, 256×256 `uint16`, all 8 core groups.

| Group | Time | Share |
|---|---|---|
| **`texture`** | **5.99 s** | **96.1 %** |
| `granularity` | 0.110 s | 1.8 % |
| `radial_distribution` | 0.061 s | 1.0 % |
| `sizeshape` | 0.023 s | 0.4 % |
| `radial_zernikes` | 0.016 s | 0.3 % |
| `zernike` | 0.014 s | 0.2 % |
| `intensity` | 0.012 s | 0.2 % |
| `feret` | 0.004 s | 0.1 % |
| total | 6.23 s | |

The project README says *"the Granularity measurement is particularly slow (~80% of the
compute time)"*. **That does not hold for this build** — granularity is 1.8%, and
`texture` is essentially the entire cost. **If a task needs speed, drop `texture`,
not `granularity`.**

All four correlation measurements together cost 0.047 s on the same data (`costes` 50%
of that, but still only 0.024 s). Costes' cost is data-dependent — its threshold search
converges fast on noise and can be far slower on real, structured images — so treat this
as a floor, not a promise.

There is **no** 900× texture cost cliff on continuous float in this build: texture
quantises to `gray_levels=256` first. (That cliff existed in the old PyPI `featurize`.)
Same data, `texture` alone: 3.7 s on `uint16`, 1.5 s on float in [0,1].

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | When to use cp_measure, the three pitfalls, the minimal pattern |
| `SCRIPT_API.md` | This file — every function, default, feature name, verified |
| `WORKFLOW_MEASURE_LABELS.py` | Label image + intensity → 271-feature CSV, with unit conversion and verification |
| `WORKFLOW_COLOCALIZATION.py` | Two channels + labels → per-object Pearson/Manders/RWC CSV |
