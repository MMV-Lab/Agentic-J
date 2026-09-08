# scikit-image — Python Script API

Introspected from the installed build: **scikit-image 0.26.0**, main env
`/opt/conda/envs/local_imagent_J`. Every signature, property name and behaviour below
was verified by running it.

## Verified signatures

```python
filters.gaussian(image, sigma=1, mode='nearest', cval=0, preserve_range=False,
                 truncate=4.0, *, channel_axis=None, out=None)
filters.threshold_otsu(image=None, nbins=256, *, hist=None)
filters.threshold_local(image, block_size=3, method='gaussian', offset=0,
                        mode='reflect', param=None, cval=0)

measure.label(label_image, background=None, return_num=False, connectivity=None)
measure.regionprops_table(label_image, intensity_image=None, properties=('label','bbox'),
                          *, cache=True, separator='-', extra_properties=None, spacing=None)

morphology.remove_small_objects(ar, min_size=<DEPRECATED>, connectivity=1, *, max_size=64, out=None)
morphology.remove_small_holes(ar, area_threshold=<DEPRECATED>, connectivity=1, *, max_size=64, out=None)
morphology.closing(image, footprint=None, out=None, *, mode='reflect', cval=0.0)
morphology.opening(image, footprint=None, out=None, *, mode='reflect', cval=0.0)

segmentation.watershed(image, markers=None, connectivity=1, offset=None, mask=None,
                       compactness=0, watershed_line=False)
segmentation.relabel_sequential(label_field, offset=1)
segmentation.clear_border(labels, buffer_size=0, bgval=0, mask=None, *, out=None)

feature.peak_local_max(image, min_distance=1, threshold_abs=None, threshold_rel=None,
                       exclude_border=True, num_peaks=inf, footprint=None, labels=None,
                       num_peaks_per_label=inf, p_norm=inf)

exposure.rescale_intensity(image, in_range='image', out_range='dtype')

registration.phase_cross_correlation(reference_image, moving_image, *, upsample_factor=1,
                                     space='real', disambiguate=False, reference_mask=None,
                                     moving_mask=None, overlap_ratio=0.3,
                                     normalization='phase')
```

## Thresholding

All available global methods in `skimage.filters`:

```
threshold_otsu      threshold_li        threshold_yen       threshold_triangle
threshold_isodata   threshold_mean      threshold_minimum   threshold_multiotsu
threshold_local     threshold_niblack   threshold_sauvola
```

- **Global, bimodal histogram** → `threshold_otsu`.
- **Uneven illumination** → `threshold_local(img, block_size=35, offset=10)`.
  `block_size` must be **odd** — an even value raises
  `ValueError: block_size must be odd!`.
- **Three or more classes** → `threshold_multiotsu(img, classes=3)` returns `classes-1`
  thresholds (e.g. `[86, 172]`), then `np.digitize(img, thresholds)`.
- **Exploring** → `filters.try_all_threshold(img, figsize=(10, 8))` renders Otsu / Li /
  Yen / Triangle / Isodata / Mean side by side. Use once, interactively; not in a
  production script.

## `regionprops_table` properties

`spacing=(dy, dx)` (or `(dz, dy, dx)`) converts to **physical units directly** —
verified: a 100-px object with `spacing=(0.5, 0.5)` reports `area = 25.0`.

### Shape-only (no `intensity_image` needed)
```
label, area, area_bbox, area_convex, area_filled, num_pixels,
axis_major_length, axis_minor_length, eccentricity, equivalent_diameter_area,
euler_number, extent, feret_diameter_max, orientation, perimeter, perimeter_crofton,
solidity, bbox, centroid, centroid_local, coords, coords_scaled,
inertia_tensor, inertia_tensor_eigvals,
moments, moments_central, moments_hu, moments_normalized,
image, image_convex, image_filled, slice
```

### Require `intensity_image`
```
intensity_mean, intensity_max, intensity_min, intensity_median, intensity_std,
centroid_weighted, centroid_weighted_local, image_intensity,
moments_weighted, moments_weighted_central, moments_weighted_hu,
moments_weighted_normalized
```

Requesting an intensity property without `intensity_image` raises `AttributeError`.

### Old names still work
The pre-0.19 names are silent aliases — verified, **no deprecation warning**:

| Old | Current |
|---|---|
| `mean_intensity` | `intensity_mean` |
| `max_intensity` | `intensity_max` |
| `major_axis_length` | `axis_major_length` |
| `minor_axis_length` | `axis_minor_length` |
| `equivalent_diameter` | `equivalent_diameter_area` |

Prefer the current names. Do not mix conventions in one `properties=` tuple.

Columns with multiple components expand with a separator: `centroid` →
`centroid-0`, `centroid-1`. `bbox` → `bbox-0` … `bbox-3`.

## Deprecations in 0.26 — these fire FutureWarning today and break in 2.0

| Deprecated | Use instead |
|---|---|
| `morphology.binary_closing(img, fp)` | `morphology.closing(img, fp)` |
| `morphology.binary_opening(img, fp)` | `morphology.opening(img, fp)` |
| `remove_small_objects(..., min_size=N)` | `remove_small_objects(..., max_size=N)` |
| `remove_small_holes(..., area_threshold=N)` | `remove_small_holes(..., max_size=N)` |

**The `min_size` → `max_size` rename changed the boundary.** `max_size=N` removes objects
with area **≤ N**; the old `min_size=N` removed area **< N**. Passing `min_size` today
routes to `max_size`, so old code silently changed behaviour at exactly `area == N`.
Verified on objects of 4 / 9 / 16 px: `max_size=8` keeps 2 objects (removes the 4-px one),
`max_size=3` keeps all 3.

Note `remove_small_objects` **defaults to `max_size=64`** — calling it with no size
argument deletes every object of 64 px or smaller.

Also note the second positional argument is still `min_size`, so
`remove_small_objects(binary, 64)` warns. Always pass `max_size=` by keyword.

## Pitfalls (all reproduced)

### 1. `filters.gaussian` rescales to [0,1] unless you say otherwise
Verified on a constant 1000-valued `uint16` image:

| Call | Output max |
|---|---|
| `gaussian(img, sigma=1)` | `0.0153` |
| `gaussian(img, sigma=1, preserve_range=True)` | `1000.0` |

Without `preserve_range=True`, every downstream intensity measurement is meaningless.

### 2. A boolean mask RAISES — it does not silently mismeasure
```python
measure.regionprops_table(labels > 0, properties=("label", "area"))
# TypeError: Non-integer image types are ambiguous: use skimage.measure.label ...
```
The error text suggests `label_image.astype(np.uint8)`. **Do not do that** to count
objects — it merges everything into a single label. Verified: two separate 100-px
squares → `astype(np.uint8)` gives one object with `area = 200`.

Always: `labels = measure.label(binary)`.

(Contrast with `cp_measure`, which accepts a bool mask and silently measures ONE object
without raising.)

### 3. `regionprops` returns PIXEL units by default
`area` is px², `perimeter` is px. Either pass `spacing=`, or multiply explicitly:
```python
df["area_um2"] = df["area"] * (pixel_size_um ** 2)
```

### 4. Gapped label ids after filtering
`remove_small_objects` on a *label* image leaves ids like `[1, 3, 7]`. Harmless for
`regionprops_table` (which reports the real ids in the `label` column) but it breaks any
code that indexes a per-object array by id. `segmentation.relabel_sequential(labels)`
returns a 3-tuple `(relabeled, forward_map, inverse_map)`.

### 5. `io.imread` on a multi-page TIFF returns a `(Z, Y, X)` array, not a list
For OME-TIFF metadata (pixel size, channel names) use `tifffile` directly.

### 6. 3D data
- Footprints must be `morphology.ball(r)` (shape `(2r+1,)*3`), not `disk(r)`.
- Pass `spacing=(dz, dy, dx)` for anisotropic voxels, or `area` (which is the **volume**
  in 3D) is wrong. Verified: an 1800-voxel object with `spacing=(2.0, 0.5, 0.5)` reports
  `area = 900.0`.
- **`eccentricity` and `perimeter` raise `NotImplementedError` on 3D labels.** These two
  only. Verified working in 3D: `area`, `feret_diameter_max`, `solidity`,
  `axis_major_length`, `equivalent_diameter_area`, `euler_number`, `extent`.

## Watershed: splitting touching objects

The distance-transform + peak-seeds recipe, which is what you want for round, touching
cells:

```python
distance = ndi.distance_transform_edt(binary)
coords = feature.peak_local_max(distance, footprint=np.ones((3, 3)), labels=binary)
markers = np.zeros(distance.shape, dtype=bool)
markers[tuple(coords.T)] = True
markers, _ = ndi.label(markers)
labels = segmentation.watershed(-distance, markers, mask=binary)
```

`peak_local_max` returns **coordinates**, not a boolean image (it did return an image
before 0.20). Watershed on `-distance` floods basins from the object centres outward.

### `min_distance` is the over-segmentation knob, and it is sharp

Measured on three synthetic spheres (`ndi.label` on the binary says the true answer
is **3** connected components):

| `min_distance` | seeds found |
|---|---|
| 3 | 21 |
| 5 | 12 |
| 7 | **3** |
| 9 | 3 |
| 12 | **0** |

Too small and every object shatters. Too large and you get **zero seeds**, after which
`watershed` with no markers returns a single label covering everything. Neither case
raises.

**Sanity-check it**: `ndi.label(binary)[1]` gives the number of connected components.
Your seed count should be ≥ that and of the same order. If watershed returns far more
objects than components, raise `min_distance`.

For anisotropic 3D data, pass `sampling=(dz, dy, dx)` to
`ndi.distance_transform_edt` — the distance map is then in physical units and
`min_distance` becomes robust (verified: 3 seeds for every `min_distance` in 3…7).

## Registration

`phase_cross_correlation` handles **rigid translation only**, and returns
`(shift, error, phasediff)` where `shift` moves `moving_image` onto `reference_image`.

```python
shift, error, phasediff = phase_cross_correlation(reference, moving, upsample_factor=10)
corrected = ndi.shift(moving, shift)
```
`upsample_factor=10` gives 1/10-pixel precision. For rotation/scale, or elastic
deformation, use the Fiji TurboReg/StackReg plugins via the Groovy coder — skimage has
no robust elastic registration.

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | When to use skimage vs cp_measure; the pitfalls in brief |
| `SCRIPT_API.md` | This file — verified signatures, full property lists, threshold menu |
| `WORKFLOW_SEGMENT_MEASURE.py` | Threshold → clean → watershed → `regionprops_table` → CSV, with μm conversion |
| `WORKFLOW_REGISTRATION.py` | Rigid drift correction of a stack with `phase_cross_correlation` |
| `WORKFLOW_3D_STACK.py` | 3D segmentation with `ball` footprints and anisotropic `spacing` |
