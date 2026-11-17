# Segmenting a fluorescent marker with Labkit — strategy, 2D and 3D

Typical task: a fluorescent marker or stain defines the objects. The positives vary in brightness
and sit on a noisy,
textured or autofluorescent background with bright debris. A global threshold either swallows background texture or loses the dim
positives; a pretrained nucleus/cell model is not made for the marker. A pixel classifier trained on
a few strokes of THIS stain handles it.

## 1. Classes

- Minimum: `background`, `marker`.
- Add a class for anything bright that must NOT count: `debris`, `vessel`, `edge`, small specks. A
  third class is better than hoping the size filter removes them — and a size filter is still
  applied afterwards (`GROOVY_WORKFLOW_MARKER_OBJECTS.groovy`).
- Multichannel image: train on the marker channel (`channel` parameter). The nuclear channel can
  be segmented separately (Cellpose/StarDist) and combined later (e.g. marker objects per nucleus).

## 2. Where to label (what to tell the user)

- **Few slices, many situations**: 3–5 slices spread through the stack, and on each: several
  positives of different brightness (include DIM ones), the background texture right next to them,
  and any bright confounders as their own class. Do not paint whole objects — a short stroke or a
  small blob inside each is enough; then strokes across background.
- Labels are expensive where they are scattered: training computes features around every label.
  Measured on a 1000×1000×84 stack: 20 ROIs on 4 slices → 8 s; scattered labels on all slices → 234 s.
- Iterate: apply, look at 2–3 slices and a max projection, add labels where it is wrong, retrain.

### Labeling options

| Option | How | Then |
|---|---|---|
| Labkit window | `Plugins > Labkit > Open Current Image With Labkit`; `D` draw, `E` erase, `N` next label; in 3D scroll through z, label on a few slices; `Labkit Pixel Classifier` → play → check overlay; `Segmentation > Save Classifier...` | apply with `GROOVY_WORKFLOW_BATCH_SEGMENTATION.groovy` |
| ROIs in Fiji | line ROIs through background, small oval/freehand ROIs inside positives; **name each ROI starting with its class** (`marker-…`, `background-…`); in a stack draw each ROI on its slice; ROI Manager > More > Save… → `.zip` | `GROOVY_WORKFLOW_TRAIN_FROM_LABELS.groovy` with `labelSource = "ROI set (.zip)"` |
| Label image | a TIFF of the same X/Y/Z size, 0 = unlabeled, 1..N = classes | `GROOVY_WORKFLOW_TRAIN_FROM_LABELS.groovy` with `labelSource = "label image"` |

## 3. 3D specifics

- **Calibration drives the 3D filters.** Labkit scales its filters by the voxel size relative to X
  (verified: 0.3245×0.3245×0.5357 µm → `[1, 1, 1.65]`). Confirm the z-step before training; for an
  uncalibrated stack set it (Image > Properties) or the filters treat z-steps like pixels.
- **Train and apply on the same kind of data**: same channel, same voxel size, similar intensity
  range. A classifier trained in 3D needs a 3D input (and a 2D one a 2D input).
- **Objects elongated in Z** (microscope blur) are normal; volumes and centroids from the objects
  workflow are in calibrated units, so compare them in µm³, not voxels.
- **Memory/time** (CPU, 1000×1000×84): apply ~70–90 s; GPU probability map ~9 s when ≥ 6 GB GPU
  memory is free (`gpuMode = "auto"` decides and falls back to CPU).

## 4. From marker voxels to cells

`GROOVY_WORKFLOW_MARKER_OBJECTS.groovy`: connected components (26-connected in 3D), size filter in
µm³, optional minimum sphericity, then CSV (volume, equivalent diameter, sphericity, mean intensity,
centroid) and a label image of the kept objects.

- Run it once with `minSize = 0`, look at the size column, choose the cut between the cloud of tiny
  fragments/debris and the real objects (a sphere of 3 µm diameter = 14 µm³; of 5 µm = 65 µm³;
  in 2D a disc of 5 µm = 20 µm²).
- QC: overlay kept vs dropped objects on a max projection and a few slices; the dropped ones should
  be fragments, the kept ones whole cells. Touching positives fused into one object show up as
  very large volumes — check the largest objects.
- Verified example (marker-positive cells in a 1000×1000×84 tissue stack): 101 components of the
  marker class → 47 kept at ≥ 20 µm³ (median 65 µm³ ≈ 5 µm diameter); dropped objects were small
  fragments and specks.

## 5. Reporting

State: classes and how many labels/slices, the voxel size used, GPU or CPU, the size (and
sphericity) cut-offs and why, the number of objects before/after filtering, and that a pixel
classifier was trained on this dataset (not a pretrained model). Save the `.classifier` with the
project so the result is reproducible.
