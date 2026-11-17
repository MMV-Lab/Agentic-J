---
name: labkit_documentation
description: >-
  Labkit (Fiji, Plugins > Labkit) segments objects defined by a FLUORESCENT MARKER or stain that a
  threshold cannot separate reliably and no pretrained model is made for — noisy channels, textured
  or autofluorescent background, dim and bright positives, debris — in 2D and in 3D stacks.
  The user marks a few examples of "marker" and "background" (a few strokes or ROIs); a random
  forest learns the rest and is applied to whole images, stacks or folders. Covers labeling in the
  Labkit window, training headless from a label image or ROI set, 3D with anisotropic voxels, GPU
  use with CPU fallback, and turning the marker class into filtered, measured objects. Read before
  any Labkit or marker-segmentation code.
---

# Labkit — segmenting fluorescent markers and stains in 2D and 3D

## When to use it — offer it as an option whenever a stain defines the objects

| Situation | Use |
|---|---|
| Objects are defined by a fluorescent marker or stain; the channel is noisy, the background textured or uneven, brightness varies; a threshold picks up background or misses dim objects | **Labkit** (this skill) — always offer it as one of the options |
| The task asks to pick a threshold (e.g. a live slider) | offer Labkit next to the threshold route: a few marked examples usually separate signal from background better than one global threshold |
| Ordinary nuclei or whole cells (DAPI, cytoplasm stain, phase contrast) | Cellpose / StarDist first — pretrained, no labels needed |
| Tiny diffraction-limited spots (smFISH, single molecules) | spot detection (LoG / TrackMate / Big-FISH), not pixel classification |

Labkit is a random-forest **pixel** classifier: it learns "what marker pixels look like" from a
few strokes, using multi-scale filters (intensity, Gaussian, difference of Gaussians, gradient,
Laplacian, Hessian; sigma 1–8 px). It does not know objects — turn the marker class into objects
with `GROOVY_WORKFLOW_MARKER_OBJECTS.groovy` (size/shape filter, measurements).

## The workflow (verified end to end on a 1000×1000×84 confocal tissue stack, 2026-11-16)

**Run the three `GROOVY_WORKFLOW_*.groovy` files as they are** — copy them into the project's
scripts folder and set the inputs; do not rewrite them. To run without a dialog, replace each
`#@` input line by a plain variable of the same name and type (`File input = new File("...")`) and
change nothing else (Fiji services are fetched in the code). They already handle the 3D axis
fix, calibration, GPU check and CPU fallback (an agent run that re-implemented them needed many
extra debug rounds). No preprocessing is needed: Labkit's features include smoothing at several
scales, and filtering the image first only changes what the classifier was trained on.

1. **Check the calibration** (`extract_image_metadata`, or Image > Properties). Labkit takes the
   voxel size from the calibration: a stack whose z-step is 1.65× the pixel size gets 3D filters
   scaled 1.65× in Z automatically. A wrong z-step (or a fake 72-dpi "calibration") distorts them.
2. **Get labels — two or more classes, e.g. `background`, `marker`**; optionally a third class such
   as `debris` for bright things that must not count as marker:
   - *User paints in Labkit* (`Plugins > Labkit > Open Current Image With Labkit`) and saves the
     classifier (Segmentation > Save Classifier...) → go to step 4. See `MARKER_SEGMENTATION_GUIDE.md`.
   - *User draws ROIs in Fiji* (lines through background, small ovals inside positive objects; name
     each ROI starting with its class, e.g. `marker-1`, `background-2`; in a stack draw on the
     slice where the object is), then ROI Manager > More > Save → `.zip`.
   - *A sparse label image* already exists (0 = unlabeled, 1..N = classes).
3. **Train headless**: `GROOVY_WORKFLOW_TRAIN_FROM_LABELS.groovy` (label image or ROI set) →
   `.classifier`. Label a FEW slices: 20 ROIs on 4 slices trained in 8 s; labels scattered through
   all slices of an 84-slice stack took 234 s (features are computed wherever labels are).
4. **Apply** to the image or a whole folder: `GROOVY_WORKFLOW_BATCH_SEGMENTATION.groovy` →
   `<stem>_labkit_seg.tif` (class index per pixel) and/or `<stem>_labkit_prob.tif` (one channel
   per class). Check the result on 2–3 slices / a projection before batching.
5. **Objects**: `GROOVY_WORKFLOW_MARKER_OBJECTS.groovy` — connected components of the marker class,
   size filter in µm³ (µm² in 2D) that drops fragments and debris, optional sphericity, CSV with
   size, equivalent diameter, mean intensity, centroid. Pick the size cut-off from the unfiltered
   size distribution of THIS data (run once with minSize 0).
6. If objects are missed or background is called marker: add labels exactly there (dim objects,
   the confusing texture) and retrain — 2–3 rounds is normal.

Time-lapse: train on one representative frame (the training workflow takes one frame); applying
to a whole movie goes through the same commands but has not been tested yet.
Multichannel: choose the marker channel (`channel` parameter) for training and applying.

## Verified pitfalls

1. **Axes of the IJ1 commands are wrong for stacks**: `Segment Image With Labkit (IJ1)` returns a
   z-stack as 1 slice × Z channels, `Calculate Probability Map ... (IJ1)` as Z channels × classes
   slices. The batch workflow restores [classes] × Z × T and the calibration. The IJ2 command
   (`Segment Image With Labkit`, Dataset input) keeps the axes.
2. **GPU: no CPU fallback inside Labkit.** With too little free GPU memory it fails with
   `CL_MEM_OBJECT_ALLOCATION_FAILURE`, a `NullPointerException` in `DefaultGpuApi`, or hundreds of
   "warnings generated" (looks like a hang). Need ≈ 60 bytes/voxel (5.5 GB for 84 M voxels). The
   workflows check CLIJ devices + free memory (`gpuMode = "auto"`) and retry on CPU. GPU helps
   applying (probability map 9 s vs 89 s on CPU), rarely training (kernel compilation).
3. **Never call `Segmenter.segment()` on a whole large stack** — it allocates all features at once
   and fails above 2^31 elements ("Number of elements in ArrayImg too big"). Use the commands
   (block-wise), as the workflows do.
4. **Batch directory command `file_filter` is a glob** (`*.tif`); `.tif` or empty matches nothing,
   silently.
5. **Script parameters persist** between Fiji runs — pass every `#@` parameter explicitly.
   Do not reach Fiji services through a `#@ ...Service` line in a script whose inputs are
   hard-coded: dropping that line along with the inputs leaves the service undefined.
6. **Headless test runs**: the `fiji` launcher sizes the Java heap from the HOST RAM (e.g. 755 GB)
   and gets killed by a container memory limit — use `fiji --heap=10g`. The agent's own Fiji is
   already capped.
7. Segmentation values are **0-based class indices** in the order of the classifier's class names
   (the workflows log `0 = background, 1 = marker, ...`).

## File index

| File | When to read it |
|---|---|
| `MARKER_SEGMENTATION_GUIDE.md` | Labeling strategy (2D/3D), what to tell the user, choosing classes, size filters, QC. |
| `GROOVY_WORKFLOW_TRAIN_FROM_LABELS.groovy` | Train a classifier from a label image, ROI set .zip, or the open ROI Manager. |
| `GROOVY_WORKFLOW_BATCH_SEGMENTATION.groovy` | Apply a classifier to one image or a folder; segmentation and/or probabilities; GPU guard. |
| `GROOVY_WORKFLOW_MARKER_OBJECTS.groovy` | Marker class → filtered, measured 2D/3D objects + CSV + label image. |
| `GROOVY_API.md` | All Labkit commands and parameters, scripted training API, GPU check snippet. |
| `UI_GUIDE.md`, `UI_WORKFLOW_PIXEL_CLASSIFICATION.md` | The Labkit window: tools, shortcuts, labeling and saving a classifier. |

Sources: Arzt et al. 2022, *Front. Comput. Sci.* 4:777728 (doi:10.3389/fcomp.2022.777728);
imagej.net/plugins/labkit; source github.com/juglab/labkit-ui and labkit-pixel-classification.
