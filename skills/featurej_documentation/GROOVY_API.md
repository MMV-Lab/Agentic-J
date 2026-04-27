# FeatureJ - Groovy API

This file documents the validated Groovy automation surface for FeatureJ in this
repo. The adopted path is the installed `imagescience.*` API that FeatureJ uses
internally, not a guessed `IJ.run(...)` macro string.

## General Rules

1. Open a grayscale `8-bit`, `16-bit`, or `32-bit` image.
2. Wrap the active `ImagePlus` as an ImageScience `Image`.
3. Use `new Aspects()` when smoothing scales should be interpreted in pixel units.
4. Save result images through `image.imageplus()`.
5. Use an area ROI or an explicit bounding box plus mask image for `Statistics`.

## Headless Script Invocation

Run the checked-in workflow from Fiji's command line with quoted `File` and
`String` parameter values:

```bash
/opt/Fiji.app/fiji-linux-x64 --headless --run \
  /app/skills/featurej_documentation/GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy \
  "inputFile='/data/example_1.tif',outputDir='/data/featurej_validation/workflow_output',mode='Edges'"
```

Do not pass file paths as unquoted bare values such as
`inputFile=/data/example_1.tif`; SciJava parses the `--run` argument as an
expression list, so bare slash-prefixed paths are not treated as literal files.

## Validated Setup Pattern

```groovy
import ij.IJ
import ij.ImagePlus
import imagescience.image.Aspects
import imagescience.image.FloatImage
import imagescience.image.Image

ImagePlus imp = IJ.openImage(inputFile.absolutePath)
if (imp == null) {
    throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
}
if (imp.getType() == ImagePlus.COLOR_RGB || imp.getType() == ImagePlus.COLOR_256) {
    throw new IllegalArgumentException("FeatureJ requires grayscale input images.")
}

Image image = Image.wrap(imp)
image.aspects(new Aspects())     // use pixel units instead of physical calibration
FloatImage work = new FloatImage(image)
```

## Derivatives

Validated call:

```groovy
import imagescience.feature.Differentiator
import imagescience.image.FloatImage

def image = new FloatImage(Image.wrap(imp))
image.aspects(new Aspects())
new Differentiator().run(image, 1.5d, 1, 0, 0)
```

Parameters:

| Parameter | Meaning | Validated values |
|-----------|---------|------------------|
| `scale` | Gaussian smoothing sigma | positive floating-point value such as `1.5d` |
| `xOrder` | derivative order in `x` | `0` to `10` |
| `yOrder` | derivative order in `y` | `0` to `10` |
| `zOrder` | derivative order in `z` | `0` to `10` |

Outputs:

- One float32 derivative image
- The result is signed
- Order `0` in a dimension means smoothing only in that dimension

## Edges

Validated call:

```groovy
import imagescience.feature.Edges
import imagescience.image.FloatImage
import imagescience.segment.Thresholder

def image = new FloatImage(Image.wrap(imp))
image.aspects(new Aspects())

def out = new Edges().run(image, 1.5d, true)
new Thresholder().hysteresis(out, 20.0d, 40.0d)
```

Parameters:

| Parameter | Meaning | Validated values |
|-----------|---------|------------------|
| `scale` | Gaussian derivative sigma for the gradient magnitude | positive floating-point value such as `1.5d` |
| `suppress` | non-maximum suppression | `true`, `false` |
| `lowerThreshold` | lower edge threshold | empty, or a floating-point value such as `20.0d` |
| `higherThreshold` | higher edge threshold | empty, or a floating-point value such as `40.0d` |

Threshold semantics:

- no thresholds: keep the continuous gradient magnitude image
- one threshold: hard threshold to `0/255`
- two thresholds: hysteresis threshold to `0/255`

## Laplacian

Validated call:

```groovy
import imagescience.feature.Laplacian
import imagescience.image.FloatImage
import imagescience.segment.ZeroCrosser

def image = new FloatImage(Image.wrap(imp))
image.aspects(new Aspects())

def out = new Laplacian().run(image, 1.5d)
new ZeroCrosser().run(out)
```

Parameters:

| Parameter | Meaning | Validated values |
|-----------|---------|------------------|
| `scale` | Gaussian derivative sigma | positive floating-point value such as `1.5d` |
| `computeLaplacian` | compute the signed Laplacian image | `true`, `false` in the workflow |
| `detectZeroCrossings` | convert the image to a zero-crossing map | `true`, `false` in the workflow |

Outputs:

- without zero-crossing detection: one signed float32 Laplacian image
- with zero-crossing detection: binary `0/255` zero-crossing map

## Hessian

Validated call:

```groovy
import imagescience.feature.Hessian
import imagescience.image.FloatImage
import imagescience.image.Image

Image image = Image.wrap(imp)
image.aspects(new Aspects())

def eigenimages = new Hessian().run(new FloatImage(image), 1.5d, false)
```

Parameters:

| Parameter | Meaning | Validated values |
|-----------|---------|------------------|
| `scale` | Gaussian derivative sigma for second-order structure | positive floating-point value such as `1.5d` |
| `absolute` | compare eigenvalues by magnitude instead of signed value | `true`, `false` |

Output ordering:

| Input dimensionality | Returned images |
|----------------------|-----------------|
| 2D | largest, smallest |
| 3D | largest, middle, smallest |

Each eigenimage is signed float32 when `absolute = false`; enabling absolute comparison replaces the signed values with their magnitudes.

## Structure

Validated call:

```groovy
import imagescience.feature.Structure
import imagescience.image.FloatImage
import imagescience.image.Image

Image image = Image.wrap(imp)
image.aspects(new Aspects())

def eigenimages = new Structure().run(new FloatImage(image), 1.5d, 3.0d)
```

Parameters:

| Parameter | Meaning | Validated values |
|-----------|---------|------------------|
| `smoothingScale` | derivative scale for the tensor elements | positive floating-point value such as `1.5d` |
| `integrationScale` | Gaussian scale for smoothing the tensor elements | positive floating-point value such as `3.0d` |

Output ordering:

| Input dimensionality | Returned images |
|----------------------|-----------------|
| 2D | largest, smallest |
| 3D | largest, middle, smallest |

Each eigenimage is non-negative float32.

## Statistics

Validated call:

```groovy
import ij.gui.Roi
import ij.process.ByteProcessor
import imagescience.feature.Statistics
import imagescience.image.Coordinates
import imagescience.image.Image

def roi = new Roi(50, 50, 128, 128)
def bounds = roi.getBounds()

def lower = new Coordinates(x: bounds.x, y: bounds.y)
def upper = new Coordinates(
    x: bounds.x + bounds.width - 1,
    y: bounds.y + bounds.height - 1
)

def maskProcessor = roi.getMask()
if (maskProcessor == null) {
    maskProcessor = new ByteProcessor(1, 1)
    maskProcessor.set(0, 0, 255)
}

def stats = new Statistics()
stats.run(Image.wrap(imp), lower, upper, Image.wrap(new ImagePlus("Mask", maskProcessor)))
double mean = stats.get(Statistics.MEAN)
```

Metric constant mapping:

| UI label | Groovy constant |
|----------|-----------------|
| `Minimum` | `Statistics.MINIMUM` |
| `Maximum` | `Statistics.MAXIMUM` |
| `Mean` | `Statistics.MEAN` |
| `Median` | `Statistics.MEDIAN` |
| `Elements` | `Statistics.ELEMENTS` |
| `Mass` | `Statistics.MASS` |
| `Variance` | `Statistics.VARIANCE` |
| `Mode` | `Statistics.MODE` |
| `S-deviation` | `Statistics.SDEVIATION` |
| `A-deviation` | `Statistics.ADEVIATION` |
| `L1-norm` | `Statistics.L1NORM` |
| `L2-norm` | `Statistics.L2NORM` |
| `Skewness` | `Statistics.SKEWNESS` |
| `Kurtosis` | `Statistics.KURTOSIS` |

ROI notes:

- full-image statistics: use the full image bounds and a `1x1` all-on mask
- rectangle ROI: the same `1x1` all-on mask is valid, matching FeatureJ's own handling
- irregular area ROI: use `roi.getMask()`
- line ROI: not supported

## FeatureJ Options in Direct Automation

The validated Groovy path does not depend on the persistent `FeatureJ Options`
preferences. Instead, the workflow maps the important behavior explicitly:

| FeatureJ option | Direct Groovy handling in this skill |
|-----------------|--------------------------------------|
| `Isotropic Gaussian image smoothing` | Preserve calibration when `usePhysicalCalibration=true`, otherwise call `image.aspects(new Aspects())` |
| `Close input images after processing` | The workflow closes the opened input image after writing outputs |
| `Save result images before closing` | The workflow writes named output files directly and refuses to overwrite existing files |
| `Progress indication` | Not exposed as a workflow parameter |
| `Log messaging` | Not exposed as a workflow parameter |

## Explicit Exclusions

- direct `IJ.run(...)` macro strings for FeatureJ dialogs
- scripted use of `FeatureJ Panel`, `FeatureJ Help`, or `Help > About Plugins > FeatureJ...`
- checked-in batch support for per-channel, per-time-frame, or per-slice `Statistics` tables
