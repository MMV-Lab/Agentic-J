# OrientationJ - Groovy API

This file separates OrientationJ's scripting surface into:

- container-validated `IJ.run(...)` calls
- standard Fiji helpers needed to save OrientationJ image and table outputs
- source-grounded caveats where the local Fiji runtime differs from the official EPFL page

## General Rules

1. OrientationJ is a macro-recordable IJ1 plugin. Use `IJ.run(...)` with the active grayscale image.
2. The active image must be 8-bit, 16-bit, or 32-bit grayscale. The plugin rejects RGB inputs for the main analysis path.
3. In the validated repo workflow, Analysis, Distribution, Vector Field, Corner Harris, and Dominant Direction all worked through `IJ.run(...)`.
4. Vector Field and Corner Harris place overlays on the active source image. Save those overlays by flattening the active image after the command runs.
5. The official EPFL page documents gradient indices `0` through `4`. The source UI also exposes index `5` (`Hessian`), but this skill keeps the checked-in workflow on the official documented `0` through `4` range.

## Validated Setup Pattern

```groovy
import ij.IJ
import ij.ImagePlus
import ij.WindowManager

ImagePlus imp = IJ.openImage(inputFile.absolutePath)
if (imp == null) {
    throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
}
if (!(imp.getType() in [ImagePlus.GRAY8, ImagePlus.GRAY16, ImagePlus.GRAY32])) {
    throw new IllegalArgumentException("OrientationJ expects an 8-bit, 16-bit, or 32-bit grayscale image.")
}

imp.show()
WindowManager.setCurrentWindow(imp.getWindow())
```

## Gradient Index Mapping

Validated and adopted in this skill:

| Index | Gradient |
|-------|----------|
| `0` | `Cubic Spline` |
| `1` | `Finite Difference` |
| `2` | `Fourier` |
| `3` | `Riesz Filters` |
| `4` | `Gaussian` |

Source-grounded but not adopted in the checked-in workflow:

| Index | Gradient |
|-------|----------|
| `5` | `Hessian` |

## Analysis

Official macro example on the EPFL page:

```groovy
IJ.run(imp, "OrientationJ Analysis",
    "tensor=1.0 gradient=0 color-survey=on hue=Orientation sat=Coherency bri=Original-Image ")
```

Container-validated call used in this repo:

```groovy
IJ.run(imp, "OrientationJ Analysis",
    "tensor=1.0 gradient=0 hsb=on hue=Orientation sat=Coherency bri=Original-Image " +
    "color-survey=on orientation=on coherency=on energy=on radian=off ")
```

Validated parameter keys:

| Key | Meaning | Validated values |
|-----|---------|------------------|
| `tensor` | local structure-tensor sigma | floating-point number such as `1.0` |
| `gradient` | gradient operator index | `0` to `4` |
| `hsb` | color survey in HSB or RGB | `on`, `off` |
| `hue` | survey hue channel | `Orientation`, `Coherency`, `Energy`, `Gradient-X`, `Gradient-Y`, `Constant`, `Original-Image` |
| `sat` | survey saturation or green channel | same value set as `hue` |
| `bri` | survey brightness or blue channel | same value set as `hue` |
| `color-survey` | show color survey window | `on` |
| `orientation` | show orientation image | `on` |
| `coherency` | show coherency image | `on` |
| `energy` | show energy image | `on` |
| `radian` | orientation units | `on` or `off` |

Validated outputs:

- `OJ-Energy-1`
- `OJ-Orientation-1`
- `OJ-Coherency-1`
- `OJ-Color-survey-1`

Saved analysis outputs in the repo pass had these characteristics:

- `OJ-Orientation-1.tif`: `float32`, about `-90` to `90` degrees when `radian=off`
- `OJ-Coherency-1.tif`: `float32`, about `0` to `1`
- `OJ-Energy-1.tif`: `float32`, rescaled image
- `OJ-Color-survey-1.tif`: RGB image

## Distribution

Official macro example on the EPFL page:

```groovy
IJ.run(imp, "OrientationJ Distribution",
    "tensor=1.0 gradient=0 radian=on histogram=on min-coherency=20.0 min-energy=10.0 ")
```

Container-validated call used in this repo:

```groovy
IJ.run(imp, "OrientationJ Distribution",
    "tensor=1.0 gradient=0 radian=off histogram=on table=on " +
    "min-coherency=10.0 min-energy=5.0 ")
```

Validated parameter keys:

| Key | Meaning | Validated values |
|-----|---------|------------------|
| `tensor` | local structure-tensor sigma | floating-point number such as `1.0` |
| `gradient` | gradient operator index | `0` to `4` |
| `radian` | orientation units | `on`, `off` |
| `histogram` | show histogram plot image | `on` |
| `table` | show histogram table | `on` |
| `min-coherency` | coherency threshold in percent | floating-point percent such as `10.0` |
| `min-energy` | energy threshold in percent of max energy | floating-point percent such as `5.0` |

Source-grounded keys not observed as separate exported windows in the validated Groovy launcher pass:

| Key | Source meaning |
|-----|----------------|
| `binary mask` | selected mask image |
| `orientation mask` | selected orientation image |

Validated outputs:

- `OJ-Histogram-1-slice-1`
- `OJ-Distribution-1`

Validated table columns:

- `Orientation`
- `Slice1`, or one `SliceN` column per slice for stack inputs

The EPFL page states that the histogram is built from pixels whose coherency exceeds `min-coherency` and whose energy exceeds `min-energy`. It also states the histogram is weighted by coherency.

## Vector Field

Container-validated call used in this repo:

```groovy
IJ.run(imp, "OrientationJ Vector Field",
    "tensor=1.0 gradient=0 radian=off vectorgrid=24 vectorscale=100 " +
    "vectortype=0 vectoroverlay=on vectortable=on ")
```

Validated parameter keys:

| Key | Meaning | Validated values |
|-----|---------|------------------|
| `tensor` | local structure-tensor sigma | floating-point number |
| `gradient` | gradient operator index | `0` to `4` |
| `radian` | angle units | `on`, `off` |
| `vectorgrid` | patch size in pixels | integer such as `24` |
| `vectorscale` | vector length scaling percent | floating-point number |
| `vectortype` | vector-length mode | `0` to `3` |
| `vectoroverlay` | draw overlay on active image | `on`, `off` |
| `vectortable` | show vector table | `on`, `off` |

Validated `vectortype` mapping from source UI:

| Index | Meaning |
|-------|---------|
| `0` | `Maximum` |
| `1` | `Energy` |
| `2` | `Coherency` |
| `3` | `Energy x Coherency` |

Validated outputs:

- `OJ-Table-Vector-Field-`
- overlay on the active image

Validated table columns:

- `X`
- `Y`
- `Slice`
- `DX`
- `DY`
- `Orientation`
- `Coherency`
- `Energy`

Runtime note:

- In the GUI-backed repo probe, the vector table appeared as an IJ1 table window and was exported successfully.
- In headless Fiji, the overlay export remained reliable, but the IJ1 table was not always materialized as a `TextWindow`.

## Corner Harris

Container-validated call used in this repo:

```groovy
IJ.run(imp, "OrientationJ Corner Harris",
    "tensor=1.0 gradient=0 harris-index=on harrisk=0.05 harrisl=3 " +
    "harrismin=10.0 harrisoverlay=on harristable=on ")
```

Validated parameter keys:

| Key | Meaning | Validated values |
|-----|---------|------------------|
| `tensor` | local structure-tensor sigma | floating-point number |
| `gradient` | gradient operator index | `0` to `4` |
| `harris-index` | show Harris index image | `on` |
| `harrisk` | Harris response parameter | floating-point number such as `0.05` |
| `harrisl` | corner window size | integer such as `3` |
| `harrismin` | minimum percentage level | floating-point percent such as `10.0` |
| `harrisoverlay` | draw detected corners on active image | `on`, `off` |
| `harristable` | show detected-corner table | `on`, `off` |

Validated outputs:

- `OJ-Harris-index-1`
- `OJ-Table-Corners Harris-`
- overlay on the active image

Validated table columns:

- `X`
- `Y`
- `Slice`
- `Harris Index`

Runtime note:

- In the GUI-backed repo probe, the corner table appeared as an IJ1 table window and was exported successfully.
- In headless Fiji, the Harris index image and overlay export remained reliable, but the IJ1 table was not always materialized as a `TextWindow`.

## Dominant Direction

Container-validated call used in this repo:

```groovy
IJ.run(imp, "OrientationJ Dominant Direction", "")
```

No macro parameters were required in the validated pass.

Validated output:

- results table titled `Dominant Direction of <image title>`

Validated table columns:

- `Slice`
- `Orientation [Degrees]`
- `Coherency [%]`

Runtime note:

- In the GUI-backed repo probe, Dominant Direction produced an IJ1 table window.
- In headless Fiji, the checked-in workflow uses a direct CSV fallback based on the plugin's own `computeSpline(...)` implementation when no table window is available.

## Measure

Official macro example on the EPFL page:

```groovy
IJ.run(imp, "OrientationJ Measure", "sigma=0.0")
```

Source-grounded notes:

- The official webpage shows `sigma=.0.0`, which appears to be a typo.
- The source reads a single macro key named `sigma` and defaults it to `0.0`.
- This plugin depends on an existing ROI and writes tab-separated results to the ImageJ log.

This skill does not provide a checked-in workflow for `OrientationJ Measure`, because ROI creation and placement are interactive decisions outside this repo's validated automation pass.

## Saving OrientationJ Outputs

The validated workflow in this skill uses standard Fiji helpers after `IJ.run(...)`:

- save new OrientationJ image windows with `IJ.saveAsTiff(...)`
- save new `TextWindow` tables as CSV
- save Vector Field and Corner Harris overlays by flattening the active image:

```groovy
ImagePlus overlayImp = imp.flatten()
IJ.saveAsTiff(overlayImp, outputFile.absolutePath)
```
