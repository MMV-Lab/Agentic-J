# Big-FISH — Scripting Reference

Non-deep-learning spot detection with an **automatically chosen intensity
threshold**. Import from the main env:

```python
import numpy as np
import bigfish.stack as stack
import bigfish.detection as detection
```

All signatures below were introspected from the installed build (**0.6.2**).

---

## The one pattern you need

```python
spots, threshold = detection.detect_spots(
    images=image,                # np.ndarray, 2D (y,x) or 3D (z,y,x)
    threshold=None,              # ← AUTOMATIC. Leave as None.
    return_threshold=True,
    voxel_size=(300, 100, 100),  # nm, (z,y,x)  — from image metadata
    spot_radius=(400, 150, 150)) # nm, (z,y,x)  — expected spot size / PSF
```

Everything else in this file is refinement on top of that call.

### Units and axis order (the two things people get wrong)

- `voxel_size` and `spot_radius` are in **nanometres**. Not microns. Not pixels.
- Order is `(z, y, x)` for 3D and `(y, x)` for 2D — **z first, x last**.
- A scalar is accepted and means "same in every dimension" (only correct for
  isotropic data).

Converting from what you usually have:

| You have | Pass |
|---|---|
| pixel size 0.108 µm, z-step 0.3 µm | `voxel_size=(300, 108, 108)` |
| pixel size 65 nm, 2D image | `voxel_size=(65, 65)` |
| diffraction-limited spot, 100× NA1.4, ~520 nm emission | `spot_radius=(400, 150, 150)` (3D) or `(150, 150)` (2D) |

`spot_radius` is the **expected radius of the object**, and it sets the LoG kernel.
It does not need to be exact, but it **does** need the right order of magnitude —
and this is the parameter that silently destroys results when it is wrong.
~150 nm laterally is correct **only for diffraction-limited puncta**. For granules,
vesicles, parasites or anything else resolvable, measure it.

Measured sensitivity on a real image whose objects are ~3900 nm across:

| `spot_radius` | seeds found | behaviour |
|---|---|---|
| 150 nm (smFISH default, ~12× too small) | — | detections stop corresponding to the objects |
| 300 nm | 277 | heavy over-detection, objects shatter |
| 800 nm | 75 | over-segments |
| **1836 nm (measured)** | **55** | **matches the reference segmentation** |

With the radius matched to the objects, the automatic threshold is exact: recall
1.00 at every density from 5 to 400 spots. See "Calibration and object size" below
for how to obtain both numbers instead of assuming them.

---

## `detect_spots`

```python
detection.detect_spots(images, threshold=None, remove_duplicate=True,
                       return_threshold=False, voxel_size=None,
                       spot_radius=None, log_kernel_size=None,
                       minimum_distance=None)
```

| Parameter | Meaning |
|---|---|
| `images` | One `np.ndarray` (2D or 3D), **or a list of arrays** for batch mode (see below) |
| `threshold` | `None` → chosen automatically by the elbow method. Supply a number only to override |
| `remove_duplicate` | Drop duplicate local maxima at the same location. Keep `True` |
| `return_threshold` | Also return the threshold that was used — always turn this on so you can log it |
| `voxel_size` | nm, `(z,y,x)`/`(y,x)`. Required unless you pass `log_kernel_size` **and** `minimum_distance` |
| `spot_radius` | nm, `(z,y,x)`/`(y,x)`. Same requirement |
| `log_kernel_size` | Escape hatch: LoG sigma directly **in pixels**, bypassing the physical parameters |
| `minimum_distance` | Escape hatch: minimum peak separation **in pixels** |

**Returns** `spots` — an `(N, 3)` array of `(z, y, x)` for 3D input, `(N, 2)` of
`(y, x)` for 2D — with `dtype=int64`. With `return_threshold=True` returns
`(spots, threshold)`.

To get x/y out for a CSV or an overlay:

```python
x = spots[:, -1]
y = spots[:, -2]
z = spots[:, 0] if spots.shape[1] == 3 else None
```

### Batch mode: one shared threshold across many images

```python
spots_list, threshold = detection.detect_spots(
    images=[img1, img2, img3],   # list of arrays
    threshold=None, return_threshold=True,
    voxel_size=(100, 100), spot_radius=(150, 150))
# spots_list is a list of (N_i, 2) arrays, one per image; threshold is a single float
```

This computes **one** threshold from the pooled images. For a set acquired with
identical settings that is exactly what you want — counts become comparable across
the set. Detecting each image in a separate call gives each its own threshold and
the counts are then **not** comparable. Verified: `[64, 64] thr=8.0`.

Note this list is for *separate images*. A 3D volume is a single `(z,y,x)` array —
never a list of planes.

---

## How the automatic threshold works, and how to QC it

```python
thresholds, log_counts, auto_threshold = detection.get_elbow_values(
    images=image, voxel_size=(100, 100), spot_radius=(150, 150))
counts = np.exp(log_counts)          # ← the second return is on a LOG scale
```

**The second return value is `log(spot count)`, not the count.** It is also passed
through a 5-point centered moving average, and the tail is truncated where the count
drops below ~7 spots (which is why you get ~197 points rather than a round 200).
Exponentiate it to get real counts — verified: `exp(log_counts)` at the plateau is
exactly the ground-truth spot number. If you plot the raw return value on a log
y-axis you are plotting log-of-log and the curve will mislead you.

Returns ~200 candidate thresholds (the exact count varies with the image), the
log-scale smoothed spot count at each, and the value that `detect_spots` would select — verified to match
what `detect_spots` picks. A `RuntimeWarning: divide by zero encountered in log` from
`spot_detection.py` is expected and benign: it comes from taking `log(0)` at
thresholds so high that no spot survives.

Plotting `counts` against `thresholds` on a log y-axis
gives the elbow curve: a steep left branch (noise being cut away) that bends into a
shallow plateau (real spots). The chosen threshold sits at the bend.

**Read this plot whenever a count looks wrong.** A clean bend means the automatic
choice is trustworthy. No visible bend means the image does not have a separable
spot population — too few spots, no spots, or a background problem (pitfalls B8,
B10), and the count should not be reported without a caveat.

Lower-level pieces, if you need to drive the steps yourself:

```python
detection.local_maximum_detection(image, min_distance)        # -> bool mask of peaks
detection.automated_threshold_setting(image, mask_local_max)  # -> the elbow threshold
detection.spots_thresholding(image, mask_local_max, threshold, remove_duplicate=True)
```

These operate on the **LoG-filtered** image (`stack.log_filter`), not the raw one.

---

## Calibration and object size — obtain them, don't assume them

Both helpers live in `WORKFLOW_SPOT_SEGMENTATION.py`; copy them into any script.

### `read_pixel_size_nm(path) -> ((y_nm, x_nm), source) | (None, reason)`

**The trap:** ImageJ writes `ResolutionUnit = 1` ("no absolute unit") into the TIFF
and records the real unit (`micron`) in its own metadata block. Code that only
understands `ResolutionUnit` 2 (inch) and 3 (cm) therefore finds nothing and falls
back to a hardcoded guess. On a real file this produced 100 nm/px where the truth
was **322.2 nm/px** — a 3.2× error that no range check catches, that silently
wrecks the LoG kernel, and that corrupts every micron column in the output CSV.

The helper resolves calibration in this order, and returns `None` (so the caller
can **raise**) rather than guessing:

1. ImageJ `pixel_width`/`pixel_height` + `unit`
2. `ResolutionUnit == 2` → inch; `ResolutionUnit == 3` → cm
3. `ResolutionUnit` 1/absent → interpret `XResolution` as px per ImageJ's `unit`

Never substitute a default. If calibration is genuinely absent, take the pixel size
from the acquisition metadata and set it explicitly.

### `measure_object_radius_nm(mask, pixel_size_nm) -> ((y_nm, x_nm), radius_px)`

Takes the median `equivalent_diameter / 2` over the cleaned threshold mask. This
turns `spot_radius` from an assumption into a measurement.

**Caveat:** the median runs over threshold *regions*. If most objects touch, it
returns the radius of the merged clumps — too large — and the watershed then places
one seed per clump and splits nothing. Verified: on 25 deliberately touching pairs
the measured (pair) radius gave 25 objects, while the true single-object radius
gave the correct 50. When you know objects overlap, set the single-object radius.

---

## Segmentation: turning spots into objects with area and intensity

`detect_spots` returns **points**. It says nothing about extent, so it cannot give
you area or integrated density. Stamping a fixed-radius disk at each coordinate is
**not** a segmentation — it yields identical circles that overshoot small objects
and truncate large ones (pitfall B4).

The working pattern splits the job between the two things each tool is good at:

```python
flat  = denoise(image)                      # EDGE-PRESERVING smooth -> median -> background
mask  = flat > filters.threshold_otsu(flat) # EXTENT comes from the threshold
spots = detection.detect_spots(images=flat, threshold=None,
                               voxel_size=px, spot_radius=radius)
# SPLITTING comes from Big-FISH: one seed per spot, watershed inside the mask
markers = np.zeros(mask.shape, np.int32)
for i, (y, x) in enumerate([s for s in spots if mask[s[0], s[1]]], start=1):
    markers[y, x] = i
labels = segmentation.watershed(-flat, markers=markers, mask=mask)
props  = measure.regionprops(labels, intensity_image=image)   # measure the ORIGINAL
```

Three details that matter:

- **`denoise` must smooth with ANISOTROPIC DIFFUSION, not a Gaussian.** This is the
  threshold path, so anything that blurs across the gap between two neighbouring
  spots makes Otsu return them as one object. The workflow defaults to
  `SMOOTHING = "anisotropic"` — Perona-Malik gradient anisotropic diffusion, the
  filter behind Fiji's `Anisotropic Diffusion 2D` and AICS's
  `edge_preserving_smoothing_3d`, shipped as `anisotropic_diffusion()` (a numpy port
  of ITK's `GradientAnisotropicDiffusionImageFilter`, verified to 1.6e-07, so no ITK
  install). Its conductance is a multiple of the image's own RMS gradient, so it
  self-scales; `"tv"` and `"bilateral"` are also edge-preserving but take absolute
  strengths that need re-tuning per image. `"gaussian"` is kept only for
  well-separated objects and prints a warning. See pitfall B13.
- **Regions with no seed must keep their own label**, or objects Big-FISH missed
  vanish from the result. The workflow relabels them back in.
- **Measure on the original image**, never on the denoised or background-subtracted
  one, or your intensities are those of a filtered image.

Validated against an independent Fiji segmentation of the same 2048×2048 file:
54 objects (areas 21/104/578 px) against the reference's 55 (12/115/847). Plain
connected components gave 53 and distance-transform watershed over-split to 68.

---

## Sub-pixel refinement

```python
spots_subpixel = detection.fit_subpixel(image, spots, voxel_size, spot_radius)
```

Gaussian-fits each detected spot and returns **float** coordinates in the same
`(z,y,x)`/`(y,x)` order. Measured on synthetic spots: median localization error
drops from **0.345 px** (raw `detect_spots`) to **0.012 px**. Use it when you will
measure distances between spots; skip it when you only need counts (it costs time
and changes nothing about how many spots there are).

---

## Clustered / overlapping spots

Two independent tools, for two different questions.

**"Several transcripts are piled into one bright blob and I want the real count":**

```python
spots_post, dense_regions, reference_spot = detection.decompose_dense(
    image, spots, voxel_size, spot_radius,
    kernel_size=None, alpha=0.5, beta=1, gamma=5)
```

Builds an average spot from the isolated detections, then divides the integrated
intensity of each dense region by it to simulate the spots hidden inside. Returns
the corrected spot list. On images with no dense regions it is a safe no-op
(verified: `in=64 out=64 dense_regions=0`). `alpha` (0–1) sets the intensity
percentile defining a "dense" region, `beta` the brightness multiple above the
reference spot, `gamma` the background-removal kernel scale.

**"Which spots group into transcription sites / clusters":**

```python
clustered_spots, clusters = detection.detect_clusters(
    spots, voxel_size, radius=350, nb_min_spots=4)
```

DBSCAN in physical space: `radius` is in **nm**, `nb_min_spots` is the minimum
group size. `clustered_spots` is your spot array with a cluster-index column
appended (`-1` = not in a cluster); `clusters` is one row per cluster with its
centroid, spot count and index.

---

## Preprocessing (`bigfish.stack`)

```python
stack.read_image(path, sanity_check=False)      # tif/png/… -> np.ndarray
stack.remove_background_gaussian(image, sigma)  # subtract a Gaussian-blurred background
stack.log_filter(image, sigma)                  # the LoG filter used internally
stack.maximum_projection(image)                 # 3D -> 2D, max along z
stack.focus_projection(image, proportion=0.75, neighborhood_size=7, method="median")
```

The LoG filter inside `detect_spots` already suppresses mild background gradients,
so **do not preprocess before `detect_spots` by default**. Reach for
`remove_background_gaussian` only when there is visible large-scale
autofluorescence; use a `sigma` several times the spot radius in pixels so you
remove background and not signal. Do **not** pre-smooth this path at all — the LoG
*is* the smoothing step, and blurring first widens the effective kernel and shifts
the automatic threshold (pitfall B14).

**That advice does not carry over to the segmentation path.** `bigfish.stack` has
no edge-preserving filter — only `mean_filter`, `median_filter`, `gaussian_filter`,
`log_filter`, min/max, dilation/erosion and the two `remove_background_*` calls — and
neither does `skimage`. So when you threshold for object extent, use
`anisotropic_diffusion()` from `WORKFLOW_SPOT_SEGMENTATION.py` (nD, no extra
dependency); `skimage.restoration.denoise_tv_chambolle` (nD) and `denoise_bilateral`
(2D) are the fallbacks. A plain Gaussian there merges neighbouring spots (pitfall B13).

Prefer detecting in the full 3D volume over max-projecting first: projection merges
spots that overlap in x/y at different z and undercounts.

---

## Do not call

- **`detection.compute_snr_spots(...)`** — raises
  `AttributeError: module 'numpy' has no attribute 'int'` on this env. Big-FISH
  0.6.2 predates numpy 2.x, and its SNR helper uses the removed `np.int` alias
  (`bigfish/detection/utils.py:582`). It is the only reachable breakage in the
  detection API; everything documented above is verified working on numpy 2.5 /
  scikit-image 0.26.

---

## Reference

Imbert et al., *"FISH-quant v2: a scalable and modular tool for smFISH image
analysis"*, RNA (2022) — <https://doi.org/10.1261/rna.079073.121>.
Docs: <https://big-fish.readthedocs.io/>.
