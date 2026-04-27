# TransformJ UI Guide

## Installation Check

TransformJ appears under:

`Plugins > ImageScience > TransformJ`

If the menu is absent, install matching TransformJ and ImageScience jars, then restart Fiji. TransformJ 4.1.0 requires ImageScience 3.1.0.

## Menu Surface

| Menu item | Opens |
|-----------|-------|
| `TransformJ Affine` | Dialog for applying a 4 x 4 matrix file |
| `TransformJ Crop` | Dialog for x/y/z/t/c crop ranges |
| `TransformJ Embed` | Dialog for embedding into a larger output image |
| `TransformJ Matrix` | Matrix creation and editing panel |
| `TransformJ Mirror` | Dialog for mirroring along available dimensions |
| `TransformJ Options` | Global TransformJ display, close, save, progress, and log settings |
| `TransformJ Panel` | Floating quick-access panel for TransformJ tools |
| `TransformJ Rotate` | Dialog for arbitrary z/y/x rotations |
| `TransformJ Scale` | Dialog for x/y/z scaling |
| `TransformJ Translate` | Dialog for x/y/z translation |
| `TransformJ Turn` | Dialog for 90-degree z/y/x turns |

## Shared Choices

### Interpolation

Available for Affine, Rotate, Scale, and Translate:

| Choice | Use when |
|--------|----------|
| Nearest Neighbor | Labels, masks, categorical images |
| Linear | General intensity images and faster exploratory work |
| Cubic Convolution | Smooth intensity images when more quality is needed |
| Cubic B-Spline | Higher-quality smooth interpolation |
| Cubic O-MOMS | Higher-order interpolation alternative |
| Quintic B-Spline | Highest-order listed interpolation, with more computation |

### Background

Affine, Rotate, and Translate use a numeric background value for output pixels that do not map to input pixels.

Embed uses a background mode:

| Choice | Meaning |
|--------|---------|
| Zero | Fill with 0 |
| Minimum | Fill with input minimum |
| Maximum | Fill with input maximum |
| Repeat | Tile/repeat input values |
| Mirror | Mirror input values around borders |
| Clamp | Extend edge values |

## Dialog Reference

### TransformJ Scale

| Control | Meaning |
|---------|---------|
| `x-Factor`, `y-Factor`, `z-Factor` | Scaling factors; must be greater than 0 |
| `x-Size`, `y-Size`, `z-Size` | Output size preview/entry; changing a size updates the matching factor |
| `Interpolation` | Interpolation scheme |
| `Preserve physical image dimensions` | Adjust voxel size so physical extent is preserved |

### TransformJ Translate

| Control | Meaning |
|---------|---------|
| `x-Distance`, `y-Distance`, `z-Distance` | Translation distance |
| `Voxel units for distances` | Interpret distances as pixels/slices instead of physical units |
| `Interpolation` | Interpolation scheme for non-integer translations |
| `Background` | Numeric fill value for uncovered output pixels |

### TransformJ Rotate

| Control | Meaning |
|---------|---------|
| `z-Angle`, `y-Angle`, `x-Angle` | Rotation angles in degrees, applied in z, then y, then x order |
| `Interpolation` | Interpolation scheme |
| `Background` | Numeric fill value |
| `Adjust bounds to fit result` | Expand output bounds so the full rotated image fits |
| `Resample isotropically` | Use isotropic output voxels based on the smallest input voxel spacing |
| `Anti-alias borders` | Reduce stair-casing at image/background transitions |

### TransformJ Turn

| Control | Meaning |
|---------|---------|
| `z-Angle`, `y-Angle`, `x-Angle` | Each is one of `0`, `90`, `180`, or `270` degrees |

Turn reorders elements and does not interpolate.

### TransformJ Mirror

Only dimensions present in the image are shown.

| Control | Meaning |
|---------|---------|
| `x-Mirror` | Reverse x order |
| `y-Mirror` | Reverse y order |
| `z-Mirror` | Reverse slice order |
| `t-Mirror` | Reverse time frame order |
| `c-Mirror` | Reverse channel order |

### TransformJ Crop

Only dimensions present in the image are shown.

| Control | Meaning |
|---------|---------|
| `x-Range`, `y-Range` | Inclusive pixel ranges, with x/y starting at 0 |
| `z-Range`, `t-Range`, `c-Range` | Inclusive slice/frame/channel ranges, with z/t/c starting at 1 |

If a rectangular ROI is active before opening Crop, its bounding box presets the x/y ranges.

### TransformJ Embed

| Control | Meaning |
|---------|---------|
| `x-Size`, `y-Size`, `z-Size`, `t-Size`, `c-Size` | Output image size |
| `x-Position`, `y-Position` | 0-based position of the input image's first pixel |
| `z-Position`, `t-Position`, `c-Position` | 1-based position of the first input slice/frame/channel |
| `Background` | Fill method for regions outside the input image |

The input must fit entirely inside the requested output dimensions.

### TransformJ Affine

| Control | Meaning |
|---------|---------|
| `Matrix file` | Full path to a 4 x 4 matrix text file |
| `Browse` | Select an existing matrix file |
| `Create` | Open the TransformJ Matrix editor |
| `Interpolation` | Interpolation scheme |
| `Background` | Numeric fill value |
| `Adjust bounds to fit result` | Expand output bounds |
| `Resample isotropically` | Use isotropic voxel spacing |
| `Anti-alias borders` | Reduce stair-casing at image/background transitions |

### TransformJ Matrix

| Control | Meaning |
|---------|---------|
| 4 x 4 grid | Homogeneous affine matrix; last row is fixed |
| `Rotate` | Compose a rotation into the matrix |
| `Scale` | Compose a scale into the matrix |
| `Shear` | Compose a shear into the matrix |
| `Translate` | Compose a translation into the matrix |
| `Invert` | Replace current matrix with its inverse |
| `Reset` | Restore identity matrix |
| `Copy` | Copy matrix to the system clipboard |
| `Print` | Print matrix to the ImageJ log |
| `Undo` | Revert the previous matrix change |
| `Load` | Load a matrix text file |
| `Save` | Save the current matrix |
| `Close` | Close the editor |

### TransformJ Options

| Control | Meaning |
|---------|---------|
| `Adopt brightness and contrast from input images` | Result display uses input display range |
| `Close input images after transforming` | Close source windows after generating outputs |
| `Save result images before closing` | Ask before closing result images |
| `Progress indication` | Show ImageJ progress bar updates |
| `Log messaging` | Emit ImageScience log messages |

## GUI Boundaries

The dialogs are intended for interactive Fiji/ImageJ use. For batch or headless execution, use the direct Groovy workflow in this skill.
