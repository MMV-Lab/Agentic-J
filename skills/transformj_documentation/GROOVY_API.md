# TransformJ Groovy API

## Recommended Automation Surface

Use the ImageScience transform classes that TransformJ wraps:

```groovy
import imagescience.image.Image
import imagescience.transform.Scale

def image = Image.wrap(imp)
def out = new Scale().run(image, 1.25d, 1.25d, 1.0d, 1.0d, 1.0d, Scale.LINEAR)
```

This path runs headlessly and returns `imagescience.image.Image` objects that can be converted to `ImagePlus` with `imageplus()`.

## Standard ImageJ Helpers

| Task | Call |
|------|------|
| Open image | `def imp = IJ.openImage(path)` |
| Wrap as ImageScience image | `def image = Image.wrap(imp)` |
| Save output TIFF | `IJ.saveAsTiff(output.imageplus(), path)` |
| Preserve original before in-place operations | `def output = image.duplicate()` |
| Close input | `imp.close()` |

## Interpolation Constants

Scale, Translate, Rotate, and Affine share the same interpolation choices:

| Label | Constant |
|-------|----------|
| Nearest Neighbor | `NEAREST` |
| Linear | `LINEAR` |
| Cubic Convolution | `CUBIC` |
| Cubic B-Spline | `BSPLINE3` |
| Cubic O-MOMS | `OMOMS3` |
| Quintic B-Spline | `BSPLINE5` |

Use nearest neighbor for label images and masks. Use linear or higher-order interpolation for continuous intensity images.

## Scale

```groovy
import imagescience.transform.Scale

def scaler = new Scale()
def out = scaler.run(image, xFactor, yFactor, zFactor, 1.0d, 1.0d, Scale.LINEAR)
```

| Parameter | Meaning |
|-----------|---------|
| `xFactor`, `yFactor`, `zFactor` | Scale factors; each must be greater than 0 |
| `tfactor`, `cfactor` | Time and channel scale factors; TransformJ GUI exposes x/y/z only, so use `1.0d` for t/c parity |
| `interpolation` | One of the constants above |

To preserve physical image dimensions after scaling, adjust output aspects:

```groovy
import imagescience.image.Aspects

def a = image.aspects()
out.aspects(new Aspects(a.x / xFactor, a.y / yFactor, a.z / zFactor, a.t, a.c))
```

## Translate

```groovy
import imagescience.transform.Translate

def translator = new Translate()
translator.background = 0.0d
def out = translator.run(image, xDistance, yDistance, zDistance, Translate.LINEAR)
```

| Parameter | Meaning |
|-----------|---------|
| `xDistance`, `yDistance`, `zDistance` | Distances in physical units for the direct API |
| `background` | Value used where shifted output has no source pixel |
| `interpolation` | One of the interpolation constants |

To pass voxel-unit offsets, multiply by calibration:

```groovy
def cal = imp.getCalibration()
def out = translator.run(image, dxPixels * cal.pixelWidth, dyPixels * cal.pixelHeight, dzSlices * cal.pixelDepth, Translate.LINEAR)
```

## Rotate

```groovy
import imagescience.transform.Rotate

def rotator = new Rotate()
rotator.background = 0.0d
def out = rotator.run(image, zAngle, yAngle, xAngle, Rotate.LINEAR, adjustBounds, resampleIsotropically, antiAliasBorders)
```

| Parameter | Meaning |
|-----------|---------|
| `zAngle`, `yAngle`, `xAngle` | Rotation angles in degrees, applied in z, then y, then x order |
| `adjustBounds` | If true, output dimensions expand to contain the full rotated image |
| `resampleIsotropically` | If true, output voxels are resampled to the smallest x/y/z spacing |
| `antiAliasBorders` | If true, reduces stair-casing at image/background transitions |
| `background` | Value used outside the input image |

## Turn

```groovy
import imagescience.transform.Turn

def out = new Turn().run(image, zQuarterTurns, yQuarterTurns, xQuarterTurns)
```

| Parameter | Meaning |
|-----------|---------|
| `zQuarterTurns`, `yQuarterTurns`, `xQuarterTurns` | Number of 90-degree turns around each axis |

Quarter-turn values are reduced modulo 4. Turn does not interpolate and is preferred for 90, 180, or 270 degree label-image rotations.

## Mirror

```groovy
import imagescience.image.Axes
import imagescience.transform.Mirror

def out = image.duplicate()
new Mirror().run(out, new Axes(true, false, false, false, false))
```

| Axis boolean | Meaning |
|--------------|---------|
| `x` | Mirror left-right |
| `y` | Mirror top-bottom |
| `z` | Reverse slice order |
| `t` | Reverse frame order |
| `c` | Reverse channel order |

`Mirror.run(...)` modifies the input `Image` in place. Duplicate first unless in-place behavior is intended.

## Crop

```groovy
import imagescience.image.Coordinates
import imagescience.transform.Crop

def start = new Coordinates(x0, y0, z0, t0, c0)
def stop = new Coordinates(x1, y1, z1, t1, c1)
def out = new Crop().run(image, start, stop)
```

| Parameter | Meaning |
|-----------|---------|
| `start` | Inclusive 0-based start coordinate in x/y/z/t/c |
| `stop` | Inclusive 0-based stop coordinate in x/y/z/t/c |

All direct API dimensions are 0-based. Stop coordinates are inclusive.

## Embed

```groovy
import imagescience.image.Coordinates
import imagescience.image.Dimensions
import imagescience.transform.Embed

def dims = new Dimensions(outX, outY, outZ, outT, outC)
def pos = new Coordinates(x0, y0, z0, t0, c0)
def out = new Embed().run(image, dims, pos, Embed.ZERO)
```

| Filling constant | Meaning |
|------------------|---------|
| `Embed.ZERO` | Fill background with 0 |
| `Embed.MINIMUM` | Fill with input minimum |
| `Embed.MAXIMUM` | Fill with input maximum |
| `Embed.REPEAT` | Repeat input values |
| `Embed.MIRROR` | Mirror input values around edges |
| `Embed.CLAMP` | Clamp to input edge values |

The input image must fit entirely within `dims` starting at `pos`.

## Affine

```groovy
import imagescience.transform.Affine
import imagescience.transform.Transform

double[][] matrix = [
    [1.0d, 0.0d, 0.0d, 20.0d],
    [0.0d, 1.0d, 0.0d, 10.0d],
    [0.0d, 0.0d, 1.0d,  0.0d],
    [0.0d, 0.0d, 0.0d,  1.0d]
] as double[][]

def affiner = new Affine()
affiner.background = 0.0d
def out = affiner.run(image, new Transform(matrix), Affine.LINEAR, adjustBounds, resampleIsotropically, antiAliasBorders)
```

| Parameter | Meaning |
|-----------|---------|
| `Transform` | 4 x 4 homogeneous transform matrix |
| `interpolation` | One of the interpolation constants |
| `adjustBounds` | Expand result bounds to include the transformed image |
| `resampleIsotropically` | Resample to isotropic voxels |
| `antiAliasBorders` | Reduce stair-casing at image/background transitions |

TransformJ assumes a right-handed coordinate system with the origin at the center of the image or volume.

## Plugin Command Names

The TransformJ jar registers these ImageJ commands:

| Menu path | Command name |
|-----------|--------------|
| `Plugins > ImageScience > TransformJ > TransformJ Affine` | `TransformJ Affine` |
| `Plugins > ImageScience > TransformJ > TransformJ Crop` | `TransformJ Crop` |
| `Plugins > ImageScience > TransformJ > TransformJ Embed` | `TransformJ Embed` |
| `Plugins > ImageScience > TransformJ > TransformJ Matrix` | `TransformJ Matrix` |
| `Plugins > ImageScience > TransformJ > TransformJ Mirror` | `TransformJ Mirror` |
| `Plugins > ImageScience > TransformJ > TransformJ Options` | `TransformJ Options` |
| `Plugins > ImageScience > TransformJ > TransformJ Panel` | `TransformJ Panel` |
| `Plugins > ImageScience > TransformJ > TransformJ Rotate` | `TransformJ Rotate` |
| `Plugins > ImageScience > TransformJ > TransformJ Scale` | `TransformJ Scale` |
| `Plugins > ImageScience > TransformJ > TransformJ Translate` | `TransformJ Translate` |
| `Plugins > ImageScience > TransformJ > TransformJ Turn` | `TransformJ Turn` |

Use these commands from the GUI or a non-headless ImageJ macro context. This skill does not use them for headless automation because the wrappers construct ImageJ1 `GenericDialog` windows.

## Exclusions

- No headless `IJ.run("TransformJ ...")` workflow is provided.
- No GUI automation is provided for the `Matrix` editor.
- No registration optimizer or deformation-field estimation is claimed.
- No undocumented TransformJ macro option strings are required by the executable workflow.
