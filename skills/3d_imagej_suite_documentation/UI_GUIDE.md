# 3D ImageJ Suite — UI Guide

All suite entries covered by this skill live under `Plugins > 3DSuite`.

## Installation Check

The suite is installed when at least these menu entries are visible:

- `Plugins > 3DSuite > Filters > 3D Fast Filters`
- `Plugins > 3DSuite > Segmentation > 3D Simple Segmentation`
- `Plugins > 3DSuite > Analysis > 3D Volume`
- `Plugins > 3DSuite > Analysis > 3D Intensity Measure`
- `Plugins > 3DSuite > 3D Manager V4 Macros`

If the menu tree is missing, enable the `3D ImageJ Suite` update site from
Fiji's updater and restart Fiji.

## 1. 3D Fast Filters

**Menu:** `Plugins > 3DSuite > Filters > 3D Fast Filters`

Use this plugin to smooth or morphologically filter a 3D stack with an
ellipsoidal neighbourhood.

Documented filter families include:

- `Mean`
- `Median`
- `Minimum`
- `Maximum`
- `MaximumLocal`
- `TopHat`
- `OpenGray`
- `CloseGray`
- `Variance`
- `Sobel`
- `Adaptive`

The dialog records the filter choice and the three radii in pixels. Use equal
X, Y, and Z radii when the stack is isotropic.

## 2. 3D Simple Segmentation

**Menu:** `Plugins > 3DSuite > Segmentation > 3D Simple Segmentation`

This plugin thresholds and labels bright 3D objects on a dark background.

Documented controls from the installed plugin are:

- `Seeds`
- `Low threshold (included)`
- `Min size`
- `Max size (-1 for infinity)`
- `Individual voxels are objects`
- `32-bit segmentation (nb objects > 65,535)`

Use a `Low threshold` of `128` for an already-binarized stack with `0`
background and `255` foreground.

## 3. 3D Watershed

**Menu:** `Plugins > 3DSuite > Segmentation > 3D Watershed`

This seeded watershed combines a signal image and a seed image. If no seed image
is selected, the plugin computes seeds automatically from local maxima.

Documented controls from the installed plugin are:

- `Seeds Threshold`
- `Image Threshold`
- `Image`
- `Seeds`
- `Radius for automatic seeds`
- `Show animation (slow)`

Use this workflow when you need seed-controlled splitting rather than simple
connected-component labeling.

## 4. 3D Spot Segmentation

**Menu:** `Plugins > 3DSuite > Segmentation > 3D Spot Segmentation`

This plugin segments spot-like objects from a raw image plus a seed image. If
the seed input is left on `Automatic`, the plugin computes seeds from local
maxima.

Documented controls from the installed plugin and official docs include:

- `Seeds Threshold`
- `Local background`
- `Diff threshold`
- `Radius 0`
- `Radius 1`
- `Radius 2`
- `Weight`
- `Radius max`
- `SD pc`
- `Local threshold method`
- `Spot segmentation method`
- `Watershed`
- `Volume min`
- `Volume max`
- `Seeds Image`
- `Spot Image`
- `Radius for automatic seeds`
- `Output`

Use the automatic-seed mode when you have a single bright spot channel and do
not already have a dedicated seed image.

## 5. 3D Nuclei Segmentation

**Menu:** `Plugins > 3DSuite > Segmentation > 3D Nuclei Segmentation`

This plugin is specialized for nuclei-like objects in a 3D stack and uses an
ImageJ auto-threshold method plus an optional separation pass.

Documented controls from the installed plugin are:

- `Method`
- `Separate`
- `Manual threshold`

Use `Separate` when touching nuclei should be split before the 3D expansion
step.

## 6. 3D Volume

**Menu:** `Plugins > 3DSuite > Analysis > 3D Volume`

Use the active binary or labelled object stack as input. The documented output
table includes:

- `Label`
- `Value`
- `Channel`
- `Frame`
- `Volume(pix)`
- `Volume(unit)`
- `Surface(pix)`
- `Surface(unit)`
- `SurfaceCorrected(pix)`
- `SurfaceNb`

## 7. 3D Intensity Measure

**Menu:** `Plugins > 3DSuite > Analysis > 3D Intensity Measure`

This measurement dialog requires two open images:

- `Objects`
- `Signal`

The documented result fields include:

- `Label`
- `Value`
- `Average`
- `Minimum`
- `Maximum`
- `StandardDeviation`
- `IntegratedDensity`
- `Channel`
- `Frame`

Use a binary or labelled image for `Objects`. The `Signal` image is the
grayscale stack from which voxel intensities are measured.

## 8. 3D Manager

**Menu entries:**

- `Plugins > 3DSuite > 3D Manager`
- `Plugins > 3DSuite > 3D Manager Options`
- `Plugins > 3DSuite > 3D Manager V4 (beta)`
- `Plugins > 3DSuite > 3D Manager V4 Macros`

`3D Manager Options` controls which geometry, intensity, distance, and contact
measurements the manager computes. The installed `3D Manager V4 Macros` entry
loads macro extension calls with the `Ext.Manager3DV4_*` prefix.

Keep the V4 macro loader on a display-backed Fiji session. In this repo's
container it touches the 3D viewer during startup, so the extension is not a
true headless macro path.

For new scripted workflows, prefer the V4 macro extension names documented in
`SCRIPT_API.md`.
