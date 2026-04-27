---
name: transformj_documentation
description: TransformJ is a Fiji/ImageJ plugin suite for geometric image transformation and manipulation. This skill documents the source-grounded TransformJ UI surface and the validated Groovy automation path through the ImageScience transform classes for Scale, Translate, Rotate, Turn, Mirror, Crop, Embed, and Affine.
---

Install **TransformJ 4.1.0** and **ImageScience 3.1.0**. In Fiji, use the ImageScience update site when it provides both jars, or install the official jars manually.

## Primary Use Case

Apply deterministic geometric transformations to 2D, 3D, time, channel, or hyperstack images, then save a transformed TIFF for downstream analysis.

For headless automation, use `imagescience.transform.*` classes. The TransformJ GUI commands use ImageJ1 `GenericDialog` dialogs and are not the preferred headless path.

## Minimal Groovy Script - Scale Mode

```groovy
import ij.IJ
import imagescience.image.Image
import imagescience.transform.Scale

def imp = IJ.openImage("/data/example_1.tif")
def input = Image.wrap(imp)

def scaler = new Scale()
scaler.messenger.log(false)
scaler.progressor.display(false)

def output = scaler.run(input, 1.25d, 0.75d, 1.0d, 1.0d, 1.0d, Scale.LINEAR)
IJ.saveAsTiff(output.imageplus(), "/tmp/example_1-transformj-scale.tif")
```

Parameterized headless invocation:

```bash
/opt/Fiji.app/fiji-linux-x64 --headless --run \
  /app/skills/transformj_documentation/GROOVY_WORKFLOW_GEOMETRIC_TRANSFORM.groovy \
  "inputFile='/data/example_1.tif',outputFile='/data/transformj_validation/scale.tif',mode='Scale',scaleX=1.25,scaleY=0.75,scaleZ=1.0,interpolation='Linear'"
```

When using `--run`, quote `File` and `String` parameter values inside the argument string. Unquoted paths are parsed as SciJava expressions.

## Command Quick Reference

| Mode | Validated Groovy call | Key output |
|------|------------------------|------------|
| Scale | `new Scale().run(image, sx, sy, sz, 1d, 1d, Scale.LINEAR)` | Resized image with the same pixel type |
| Translate | `translator.background = bg; translator.run(image, dx, dy, dz, Translate.LINEAR)` | Same-size shifted image with uncovered regions set to `background` |
| Rotate | `rotator.background = bg; rotator.run(image, zDeg, yDeg, xDeg, Rotate.LINEAR, adjust, resample, antialias)` | Rotated image; dimensions change when `adjust` is true |
| Turn | `new Turn().run(image, zQuarterTurns, yQuarterTurns, xQuarterTurns)` | Exact 90-degree reordering without interpolation |
| Mirror | `new Mirror().run(outputDuplicate, new Axes(x, y, z, t, c))` | Same-size mirrored duplicate |
| Crop | `new Crop().run(image, startCoordinates, stopCoordinates)` | Cropped image; direct API coordinates are 0-based in all dimensions |
| Embed | `new Embed().run(image, outputDimensions, startCoordinates, Embed.ZERO)` | Larger canvas containing the input at the requested position |
| Affine | `affiner.background = bg; affiner.run(image, transform, Affine.LINEAR, adjust, resample, antialias)` | Affine-transformed image from a 4 x 4 matrix |

## 5 Critical Pitfalls

1. **TransformJ 4.1.0 requires ImageScience 3.1.0.** Older ImageScience jars can still expose transform classes, but the TransformJ plugin wrapper refuses to run.
2. **Headless `IJ.run("TransformJ ...")` is GUI-bound.** The plugin wrappers instantiate ImageJ1 dialogs, so use direct `imagescience.transform.*` calls for headless workflows.
3. **Coordinate conventions differ by surface.** TransformJ GUI uses x/y pixels from 0 and z/t/c indices from 1 for Crop and Embed; the direct ImageScience API uses 0-based coordinates in all dimensions.
4. **Rotate and Affine can change image bounds and calibration.** `adjustBounds` changes output dimensions; `resampleIsotropically` can change voxel spacing and memory use.
5. **Interpolation choice changes scientific meaning.** Turn, Mirror, Crop, and Embed can preserve exact values; Scale, Translate, Rotate, and Affine interpolate unless nearest neighbor is selected.

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Thin labels or segmentation masks become blurred | Use `Nearest Neighbor`, or prefer `Turn` for 90-degree rotations |
| Rotated object is clipped | Enable `adjustBounds`; set a suitable `backgroundValue` |
| Output is much larger or slower than expected | Disable `resampleIsotropically`, lower scale factors, or crop first |
| Translation distance is off after calibration changes | Set `translateVoxelUnits=true` for pixel/slice units, or pass physical distances intentionally |
| Crop or Embed fails with an out-of-range error | Check 0-based API coordinates and inclusive crop stop coordinates |
| Affine output is empty or shifted unexpectedly | Confirm the 4 x 4 matrix, center-origin convention, and `adjustBounds` setting |

## File Index

| File | Contents |
|------|----------|
| `OVERVIEW.md` | Plugin scope, input/output expectations, automation level, installation, limitations, citation, and links |
| `GROOVY_API.md` | Validated direct Groovy API calls, parameter tables, indexing rules, and excluded macro paths |
| `GROOVY_WORKFLOW_GEOMETRIC_TRANSFORM.groovy` | Executable Fiji script covering Scale, Translate, Rotate, Turn, Mirror, Crop, Embed, and Affine |
| `UI_GUIDE.md` | Source-grounded TransformJ menu surface and dialog control reference |
| `UI_WORKFLOW_GEOMETRIC_TRANSFORM.md` | Manual GUI walkthrough with interpretation and troubleshooting |
| `SKILL.md` | This quick-reference card |
