# TransformJ Overview

## Provenance

TransformJ is an ImageJ plugin suite by Erik Meijering for geometric image transformation and manipulation. The TransformJ plugins are wrappers around ImageScience transformation algorithms, with GUI entries under `Plugins > ImageScience > TransformJ`.

Official documentation states that TransformJ can handle ImageJ-supported images up to five dimensions and provides these user-facing tools:

| Tool | Purpose |
|------|---------|
| Affine | Apply a 4 x 4 affine transformation matrix |
| Matrix | Create, edit, load, save, invert, and print affine matrices |
| Scale | Resize images in x, y, and z |
| Translate | Shift images in x, y, and z |
| Rotate | Rotate by arbitrary angles around z, y, and x |
| Turn | Rotate by multiples of 90 degrees without interpolation |
| Mirror | Reverse element order along any available dimension |
| Crop | Crop x, y, z, t, and c ranges |
| Embed | Place an image into a larger output image |
| Options | Set package-level display, closing, progress, and logging preferences |
| Panel | Open a quick-access panel for the other TransformJ tools |

## Typical Use Cases

| Use case | Recommended mode |
|----------|------------------|
| Downsample or upsample intensity images | Scale |
| Shift a stack by a known offset | Translate |
| Deskew or rotate by a non-90-degree angle | Rotate or Affine |
| Rotate labels or masks by 90, 180, or 270 degrees | Turn |
| Flip a specimen or channel order | Mirror |
| Extract a spatial, z, time, or channel subvolume | Crop |
| Pad an image before convolution, registration, or model inference | Embed |
| Apply a known homogeneous transform from another workflow | Affine |

## Input Requirements

| Requirement | Notes |
|-------------|-------|
| Image type | ImageJ-readable images; TransformJ documentation says the suite handles ImageJ-supported image types |
| Dimensions | 2D, 3D, time, channel, and hyperstack data are supported by the plugin family |
| Calibration | Rotate, Translate, Scale, and Affine use voxel calibration for physical-unit behavior where applicable |
| Matrix file for Affine | Text file with exactly 4 rows and 4 columns; tabs, spaces, or commas are accepted by the documented plugin format |
| Coordinates | GUI Crop and Embed use ImageJ conventions: x/y start at 0; z/t/c start at 1. Direct API coordinates are 0-based in every dimension |

## Output Types

| Mode | Output |
|------|--------|
| Scale | New image of the same pixel type, with dimensions determined by scale factors |
| Translate | Same-size shifted image, with uncovered voxels filled by `backgroundValue` |
| Rotate | New image; dimensions are preserved or expanded depending on `adjustBounds` |
| Turn | New image produced by element reordering; no interpolation |
| Mirror | Mirrored image; the direct workflow duplicates the input before mirroring |
| Crop | New image containing the inclusive coordinate range |
| Embed | New larger image with background filled by zero, min, max, repeat, mirror, or clamp |
| Affine | New image transformed by a 4 x 4 homogeneous matrix |

## Automation Level

The executable workflow in this skill uses direct `imagescience.transform.*` classes. This is the validated headless automation path because the TransformJ ImageJ1 plugin wrappers create `GenericDialog` dialogs.

TransformJ plugin command names and menu paths are source-grounded from the official `plugins.config`, but this skill does not use headless `IJ.run("TransformJ ...")` plugin calls in the runnable workflow.

## Installation

Use matching TransformJ and ImageScience versions:

1. Enable the Fiji `ImageScience` update site when it provides both jars.
2. If the update site only installs an older `imagescience.jar`, manually install:
   - `TransformJ_-4.1.0.jar`
   - `ImageScience-3.1.0.jar`
3. Restart Fiji after installing or replacing jars.

TransformJ 4.1.0 requires ImageJ 1.53e and ImageScience 3.1.0.

## Known Limitations

- Headless plugin macros are excluded from the runnable workflow because the TransformJ wrappers instantiate ImageJ1 dialogs.
- The `Matrix` plugin is a GUI matrix editor. For automation, use a checked 4 x 4 text file and load it into `imagescience.transform.Transform`.
- `Rotate` and `Affine` can require substantial memory because higher-order interpolation uses floating-point working images.
- TransformJ performs known geometric transformations. It is not an intensity-based registration optimizer and does not estimate elastic or nonlinear warps.
- Interpolation can alter masks, label images, and quantitative intensities. Use `Turn`, `Mirror`, `Crop`, or nearest-neighbor interpolation when exact label values must be preserved.
- The workflow writes a TIFF and fails if the output path already exists.

## Evidence Boundaries

| Claim type | Covered in this skill |
|------------|-----------------------|
| Official-doc claim | TransformJ scope, tool list, 5D capability, interpolation families, coordinate conventions, installation requirements, and citation |
| Source-grounded claim | Menu command names from `plugins.config` and wrapper behavior from the TransformJ Java source |
| Container-validated claim | Direct Groovy automation through `imagescience.transform.*` for Scale, Translate, Rotate, Turn, Mirror, Crop, Embed, and Affine |
| Excluded or unverified | Headless `IJ.run("TransformJ ...")` dialog execution and GUI-only Matrix editing |

## Citation

If publishing results based on TransformJ, acknowledge Erik Meijering and consider citing:

E. H. W. Meijering, W. J. Niessen, M. A. Viergever. "Quantitative Evaluation of Convolution-Based Methods for Medical Image Interpolation." Medical Image Analysis, vol. 5, no. 2, June 2001, pp. 111-126.

## Links

| Resource | URL |
|----------|-----|
| ImageJ TransformJ page | https://imagej.net/plugins/transformj |
| TransformJ official page | https://imagescience.org/meijering/software/transformj/ |
| TransformJ GitHub source | https://github.com/ImageScience/TransformJ |
| ImageScience GitHub source | https://github.com/ImageScience/ImageScience |
| ImageScience update site | https://sites.imagej.net/ImageScience/ |
| Release notes | https://imagescience.org/meijering/software/transformj/releases/ |
