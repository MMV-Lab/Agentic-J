---
name: bigfish
description: >-
  Big-FISH detects and counts small bright fluorescent spots (smFISH/RNA transcripts, puncta,
  foci, granules, vesicles) in 2D images and 3D stacks, and is the DEFAULT spot-detection tool
  because it needs NO parameter tuning and NO deep-learning model. It runs a Laplacian-of-Gaussian
  filter plus local-maximum detection, then picks the intensity threshold ITSELF via the elbow
  method — you pass `threshold=None` and supply only two PHYSICAL values, `voxel_size` and
  `spot_radius`, both in NANOMETRES. In the MAIN env; `import bigfish.detection`. Use it for
  counting spots per image or per cell, spots in 3D confocal stacks, and batch runs over many
  images where hand-tuning a threshold is impractical. It ALSO produces true per-object
  SEGMENTATION (area, mean, integrated density per punctum) via WORKFLOW_SPOT_SEGMENTATION.py,
  which thresholds for object extent and uses the detected spots as watershed seeds. CRITICAL
  PITFALLS: voxel_size must be READ from the image calibration, never guessed (ImageJ writes
  ResolutionUnit=1 and hides the unit in its own metadata, so naive readers silently fall back to
  a wrong value); spot_radius must MATCH the actual object size and 150 nm applies ONLY to
  diffraction-limited spots — a mismatched radius silently destroys detection; detect_spots returns
  POINTS, so never stamp fixed-radius disks and call the result a segmentation; both parameters and
  the returned INTEGER PIXEL coordinates are ordered (z,y,x) for 3D / (y,x) for 2D, never (x,y).
  Prefer TrackMate when spots must be LINKED across time (tracking). For SUB-PIXEL accuracy stay
  here and use detection.fit_subpixel, which refines the detected spots in place.
---

# Big-FISH — Documentation Index

Big-FISH finds **small bright spots** in fluorescence images and tells you where
they are and how many there are. It is a classical (non-deep-learning) detector:
Laplacian-of-Gaussian filtering followed by local-maximum detection and an
intensity threshold.

**Why this is the default spot detector: the threshold is automatic.** The usual
pain of spot detection is hand-tuning an intensity cutoff per image. Big-FISH
removes it — call `detect_spots(..., threshold=None)` and it builds the curve of
"spot count vs. threshold", finds the elbow (the kink where fast-decaying false
positives give way to the slowly-decaying true spots) and uses that value. The
only numbers you provide are physical facts about the acquisition:

| You supply | How to OBTAIN it | Units |
|---|---|---|
| `voxel_size` | **read from the file's calibration** — never guessed (pitfall B1) | **nanometres**, `(z,y,x)` or `(y,x)` |
| `spot_radius` | **measured from your objects** — 150 nm only if they are truly diffraction-limited (pitfall B2) | **nanometres**, `(z,y,x)` or `(y,x)` |

Neither is a knob to sweep — but neither is a constant you may assume. Both must be
*obtained from the data*. Assuming them is the single most common way this tool
fails, and it fails **silently**: measured on real data, a `spot_radius` 12× too
small still returned a plausible-looking spot list while the detections no longer
corresponded to the objects.

Installed in the main env (`local_imagent_J`) — no env switch needed, scripts do
**not** need an `# imagentj-env:` header.

## When to use this vs. alternatives

- **Big-FISH (this skill)** — counting spots/puncta/foci, 2D or 3D, one image or
  thousands. No tuning, no model, no GPU. **Start here.** For per-object **area and
  intensity** use `WORKFLOW_SPOT_SEGMENTATION.py`, which adds real object extent on
  top of the detection.
- **`detection.fit_subpixel` (this skill)** — when you need **sub-pixel**
  coordinates, e.g. measuring inter-spot distances near the diffraction limit.
  Refines `detect_spots` output in place; no second tool required (pitfall B5).
- **TrackMate** — when spots must be **linked across time** into tracks. Big-FISH
  detects per-image; it does not track.
- **skimage `blob_log` / `peak_local_max`** — when you want the raw primitives and
  intend to supply your own threshold.

## Minimal example

```python
import bigfish.detection as detection

spots, threshold = detection.detect_spots(
    images=image,               # 2D (y,x) or 3D (z,y,x) numpy array
    threshold=None,             # ← automatic; do not hand-tune
    return_threshold=True,
    voxel_size=(300, 100, 100), # nm, (z,y,x)
    spot_radius=(400, 150, 150))# nm, (z,y,x)

print(f"{len(spots)} spots (auto threshold={threshold})")
```

`spots` is an `(N, 3)` integer array of `(z, y, x)` — or `(N, 2)` of `(y, x)` for
a 2D image.

## Files

| File | What it covers |
|------|---------------|
| `SCRIPT_API.md` | Full reference: `detect_spots`, `get_elbow_values`, `decompose_dense`, `detect_clusters`, background removal, batch/shared-threshold mode, 2D vs 3D, coordinate conventions, and how the automatic threshold works |
| `WORKFLOW_SPOT_DETECTION.py` | Ready-to-run: image (or folder) → spot coordinates CSV + per-image counts + elbow QC plot; edit the CONFIG block |
| `WORKFLOW_SPOTS_PER_CELL.py` | Ready-to-run: spots + a cell/nucleus LABEL image (from cellpose/stardist) → spots-per-cell CSV, the standard smFISH readout |
| `WORKFLOW_SPOT_SEGMENTATION.py` | Ready-to-run: image → per-object **segmentation mask** + area/mean/integrated-density CSV + contour QC. Reads calibration from the file, measures the object radius, splits touching objects. Use this whenever you need object EXTENT, not just position |

Each workflow falls back to synthetic data when its configured input is missing, so
running one untouched is the quickest way to check the skill still works.

## Critical pitfalls

- **B1 — READ the pixel size; never fall back to a guess.** Units are **nanometres**
  (`voxel_size=(300, 100, 100)` = 300 nm in z, 100 nm in x/y), and microns (`0.1`)
  or pixels (`1`) produce a nonsense LoG kernel. But the dangerous case is a
  *plausible* wrong value: a real run silently used a 100 nm/px fallback on an image
  whose true size was **322 nm/px**, a 3.2× error that no range check catches and
  that corrupts every physical column downstream.
  The trap is that **ImageJ writes `ResolutionUnit = 1` ("no absolute unit")** and
  puts the real unit in its own metadata block, so code handling only unit 2 (inch)
  and 3 (cm) finds nothing. Use `read_pixel_size_nm()` from
  `WORKFLOW_SPOT_SEGMENTATION.py`, which handles that case and **raises** rather
  than guessing. If calibration is genuinely absent, get it from the acquisition
  metadata — do not invent it.
- **B2 — `spot_radius` must MATCH your objects, and 150 nm is only for
  diffraction-limited spots.** This is the highest-impact parameter and it fails
  silently. Measured on real data (parasites, median diameter 12.1 px ≈ 3900 nm):
  leaving the smFISH default of 150 nm — ~12× too small — produced detections that
  no longer corresponded to the objects, while still returning a plausible-looking
  spot list. Conversely, with the radius matched to the objects the automatic
  threshold is exact: recall **1.00** at every density from 5 to 400 spots.
  Measure it rather than assuming: threshold the denoised image and take the median
  `equivalent_diameter / 2` (see `measure_object_radius_nm()`). **Caveat:** that
  median is taken over threshold *regions*, so when most objects touch it reports
  the radius of the merged clumps — then set the single-object radius explicitly.
- **B3 — axis order is `(z, y, x)`, not `(x, y, z)`.** This applies to
  `voxel_size`, `spot_radius`, and the **returned coordinates**. To write an
  x/y CSV or overlay on an image you must swap: `x = spots[:, -1]`,
  `y = spots[:, -2]`, `z = spots[:, 0]` (3D only).
- **B4 — Big-FISH returns POINTS. Never stamp fixed disks and call it a
  segmentation.** `detect_spots` gives one coordinate per spot and nothing about
  extent. Drawing a constant-radius disk at each point yields a mask of identical
  circles that overshoot small objects, truncate large ones, and make every
  area/intensity measurement meaningless — a real run produced 34 objects with only
  18 distinct areas, against 55 objects spanning 12–847 px for a true segmentation
  of the same image. If you need per-object **area or integrated intensity**, use
  `WORKFLOW_SPOT_SEGMENTATION.py`: threshold for extent, Big-FISH spots as
  watershed seeds to split touching objects.
- **B5 — `detect_spots` coordinates are integer pixel indices, not sub-pixel.**
  It returns the local-maximum voxel, so localization error is up to ~0.5 px
  (measured: 0.345 px median on synthetic spots). If you need sub-pixel accuracy,
  do **not** reach for another tool — pass the result through
  `detection.fit_subpixel(image, spots, voxel_size, spot_radius)`, which Gaussian-fits
  each spot and returns float coordinates (measured: 0.012 px median error, a 29×
  improvement). Counting does not need this; distance measurements do.
- **B6 — a 3D stack must be one `(z, y, x)` array.** If you pass a *list* of 2D
  planes, `detect_spots` treats them as unrelated 2D images and returns a list of
  per-plane results with one shared threshold. That list mode is for **batch over
  many images**, which is a feature (see B7) — just don't use it for a volume.
- **B7 — batch mode shares one threshold across the list, which is what you want.**
  Passing `images=[img1, img2, ...]` computes a *single* auto threshold from all of
  them. For a set of images acquired under identical settings this makes counts
  comparable across the set; detecting each image separately gives each its own
  threshold and makes counts non-comparable.
- **B8 — `threshold=None` needs enough spots to form an elbow, and can CRASH when
  it doesn't.** On an image with very few spots the elbow is ill-defined: the count
  becomes unreliable, and `detect_spots` can raise
  `ValueError: False is not in list` from `get_breaking_point` outright (observed on
  a 6-spot image). Wrap the call in `try/except` for anything unattended, and
  sanity-check with `get_elbow_values()` and the QC plot in
  `WORKFLOW_SPOT_DETECTION.py` before trusting a low-count result.
- **B9 — `get_elbow_values` returns `log(count)`, not the count.** The second return
  value is log-scaled *and* smoothed by a moving average, and its tail is truncated
  below ~7 spots (so you get ~197 points, not 200). Take `np.exp(...)` to recover
  real counts. Plotting the raw value on a log y-axis gives log-of-log and a curve
  that misrepresents where the elbow is.
- **B10 — uneven background breaks the assumption, and background flattening is
  NOT denoising.** Big-FISH expects spots on a roughly flat background. For strong
  autofluorescence gradients apply
  `bigfish.stack.remove_background_gaussian(image, sigma=...)` first (the LoG
  filter handles mild gradients on its own). But note what that call does: it
  subtracts a large-scale estimate, it does **not** suppress noise. Smoothing is a
  separate decision — see B13.
- **B11 — `compute_snr_spots()` is BROKEN on this env and must not be called.** It
  raises `AttributeError: module 'numpy' has no attribute 'int'` — Big-FISH 0.6.2
  (April 2022) still uses the `np.int` alias that numpy 2.x removed. This is the
  *only* reachable breakage: `detect_spots`, `get_elbow_values`, `fit_subpixel`,
  `decompose_dense` and `detect_clusters` are all verified working. If you need a
  per-spot signal quality number, compute it yourself from the image.
- **B12 — Big-FISH is unmaintained upstream (last release 0.6.2, April 2022).** It
  runs correctly on this env's numpy 2.5 / scikit-image 0.26 (verified end-to-end),
  but do not expect fixes upstream. If a numpy or scikit-image upgrade changes
  behaviour, re-check B11 first — that is where the version rot shows up.
- **B13 — if you smooth before thresholding, use ANISOTROPIC DIFFUSION, not a plain
  Gaussian and not a hand-tuned denoiser.** A Gaussian blurs across the dark gap
  *between* two neighbouring spots as happily as it flattens noise, so a subsequent
  threshold sees one connected bright region and returns one object with the summed
  area. The standard fix is Perona-Malik gradient anisotropic diffusion — Fiji's
  `Anisotropic Diffusion 2D` plugin, and AICS's `edge_preserving_smoothing_3d`
  (ITK `GradientAnisotropicDiffusionImageFilter`). `WORKFLOW_SPOT_SEGMENTATION.py`
  ships it as `anisotropic_diffusion()`, a numpy port verified against ITK 5.4.6 to
  **1.6e-07**, so no ITK install is needed and it works in 2D and 3D.

  **Why it beats the other edge-preserving filters here: its strength is
  self-scaling.** ITK recomputes the image's mean squared gradient every iteration
  and sets `K = -2 · conductance² · <|∇I|²>`, so `conductance` is a multiple of the
  image's *own* RMS gradient. A fixed `TV_WEIGHT` or `sigma_spatial` is absolute, so
  a value tuned on one image over-smooths the next.

  **Measured on a real 2048×2048 confocal image** (parasites, 322 nm/px, a pair
  13 px apart). "Margin" is what actually decides the merge: how far the intensity
  valley between the two spots sits *below* the Otsu threshold — negative keeps them
  separate. "Merged"/"lost" are counted against the unsmoothed run.

  | smoothing | noise removed | margin | objects | merged | lost |
  |---|---|---|---|---|---|
  | none | 0% | −14.5 | 54 | 0 | 0 |
  | **anisotropic (AICS defaults)** | **44%** | **−14.0** | **54** | **0** | **0** |
  | Fiji `Anisotropic Diffusion 2D` | 33% | −14.0 | 54 | 0 | 0 |
  | bilateral | 58% | −9.8 | 52 | 0 | 2 |
  | tv `weight=0.01` | 60% | −8.2 | 55 | 0 | 0 |
  | gaussian σ=1 | 54% | −4.4 | 54 | 1 | 0 |
  | tv `weight=0.05` | 77% | −0.0 | **48** | **4** | **3** |

  Anisotropic diffusion removes noise almost for free: 44% of it for 0.5 units of
  margin. Every other filter trades margin away much faster, and `tv weight=0.05`
  runs the margin to zero and fuses four pairs outright.
  **The lesson is not "edge-preserving beats Gaussian" — it is that STRENGTH
  dominates.** At matched noise removal the edge-preserving filters do win (bilateral
  and Gaussian both remove 54%; bilateral keeps 9.8 of margin against 4.4). But an
  edge-preserving filter turned up too high merges spots just as a Gaussian does.

  **The one case where the default is the wrong choice: a noise-dominated image.**
  The same self-scaling that makes anisotropic diffusion safe makes it protect
  whatever dominates the gradient statistics — and when that is the noise, it
  faithfully preserves the noise. On the parasite image with 3× its native noise,
  the default returned **9774** objects (54 is correct), and it took 60 iterations
  and 4× the runtime to get to 51. `SMOOTHING = "tv"` with `TV_WEIGHT = 0.05` — the
  weight that is wrong as a default — returned **54 objects with one merge in 14 s**.
  An absolute weight ignores the image's statistics, which is a liability on clean
  data and an asset here. So: keep `anisotropic`, and switch to `tv` at
  `TV_WEIGHT ≈ 0.05` when a run returns thousands of tiny objects.

  **Watch out for hot pixels, whichever filter you pick.** Smoothing runs *before*
  the median in the ladder, so an isolated hot pixel is first spread into a blob too
  wide for `MEDIAN_RADIUS_PX = 1` to remove. With 0.05% hot pixels injected, the
  unsmoothed path was untouched (54 objects — the median kills single pixels), while
  bilateral produced 155 objects (119 spurious) and the Gaussian lost 43. Anisotropic
  degraded least (54 objects, one merge). Despeckle first if your camera has hot
  pixels.
  **Do not conclude "skip smoothing" either.** On synthetic data the *unsmoothed*
  image produced spurious extra objects (25–26 where 24 is correct) from noise
  fragments, which every filter avoided.
  Second effect: the Gaussian **inflates areas** — median area 110 px against 99
  unsmoothed on the objects all modes agree on, and 104 vs 91 over the whole image.
  **Where this applies:** the threshold-based `WORKFLOW_SPOT_SEGMENTATION.py`, which
  defaults to `SMOOTHING = "anisotropic"`. It does **not** apply to plain
  `detect_spots`: that path takes local *maxima* separated by `minimum_distance`, not
  connected components, so it does not fuse neighbours and needs no pre-smoothing
  (B14). One caveat inside this workflow: `split_touching()` passes the *smoothed*
  image to `detect_spots` for seeding, so the smoothing choice does move the seeds
  (52 seeds unsmoothed, 46 at `tv weight=0.05`). When smoothing fuses a pair at the
  threshold step and Big-FISH seeded only one of them, the watershed cannot undo it —
  that is exactly how the four merges above happened.
- **B14 — do not pre-smooth before `detect_spots`.** Its LoG filter is already the
  smoothing step, sized from `voxel_size`/`spot_radius`, and blurring first widens
  the effective kernel and shifts the automatic threshold. B13 is about the
  *threshold-based segmentation* path only. If `detect_spots` is finding noise
  peaks, the fix is a correct `spot_radius` (B2) or background removal (B10), not a
  Gaussian.

## Verified

Measured on synthetic Gaussian spots with known ground truth: the automatic
threshold recovers 64/64 spots in 2D and 32/32 in 3D with zero false positives, no
threshold supplied — and recall stays **1.00** from 5 to 400 spots *provided
`spot_radius` matches the objects* (pitfall B2). `fit_subpixel` lowers median
localization error from 0.345 px to 0.012 px.

`WORKFLOW_SPOT_SEGMENTATION.py` was validated against a real 2048×2048 confocal
image and an independent Fiji reference segmentation of the same file:

| | objects | area px (min/median/max) |
|---|---|---|
| Fiji reference (Otsu + Analyze Particles) | 55 | 12 / 115 / 847 |
| **this workflow, shipped default** | **54** | **16 / 98 / 419** |
| stamping fixed disks at spot coords (**wrong**, pitfall B4) | 34 | 97 / 102 / 329 |

Calibration was read correctly from the file as 322.2 nm/px (the run that guessed
100 nm/px was 3.2× off), and the object radius was measured at 1776 nm — against
the 150 nm default that caused the failure.

`anisotropic_diffusion()` was checked against `itk.GradientAnisotropicDiffusionImageFilter`
(ITK 5.4.6) on real 2D and 3D data over a sweep of iterations, conductance and time
step: **max absolute difference 1.6e-07**, i.e. float32 round-off. The port is the
same filter, so the AICS defaults carry over unchanged.

The `SMOOTHING` options were verified by running the workflow under every mode
(`anisotropic`, `tv`, `bilateral`, `gaussian`, `none`) on two real datasets plus the
separation sweep in pitfall B13;
`denoise_tv_chambolle` was confirmed to work on a 3D array, so the default survives
if the workflow is extended past 2D.
