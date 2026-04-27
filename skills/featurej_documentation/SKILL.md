---
name: featurej_documentation
description: FeatureJ is a Fiji/ImageJ plugin suite for multi-scale differential feature extraction in grayscale images. This skill documents the validated Groovy automation path through the installed ImageScience classes for Derivatives, Edges, Laplacian, Hessian, Structure, and Statistics, plus the verified FeatureJ menu surface and a parameterized workflow script that saves TIFF and CSV outputs.
---

Install via the Fiji update site **ImageScience**, then restart Fiji.

---

## Primary Use Case in This Skill Set

Open one grayscale 2D or 3D image, run one FeatureJ mode, and save the result
as a deterministic TIFF or CSV file.

The most common path is `Edges` for a Canny-style edge map. `Derivatives`,
`Laplacian`, `Hessian`, `Structure`, and `Statistics` are additional validated
surfaces.

---

## Minimal Groovy Script - Edges Mode

```groovy
import ij.IJ
import imagescience.feature.Edges
import imagescience.image.Aspects
import imagescience.image.FloatImage
import imagescience.segment.Thresholder

def imp = IJ.openImage("/data/example_1.tif")   // must be grayscale
def image = new FloatImage(imp)
image.aspects(new Aspects())                    // pixel-unit smoothing scales

def edges = new Edges().run(image, 1.5d, true)  // suppress non-maxima
new Thresholder().hysteresis(edges, 20.0d, 40.0d)

IJ.saveAsTiff(edges.imageplus(), "/tmp/example_1-edges.tif")
```

See [GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy](GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy)
for a parameterized multi-mode script that saves all validated FeatureJ outputs.

Headless Fiji invocation:

```bash
/opt/Fiji.app/fiji-linux-x64 --headless --run \
  /app/skills/featurej_documentation/GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy \
  "inputFile='/data/example_1.tif',outputDir='/data/featurej_validation/workflow_output',mode='Edges'"
```

When using `--run`, quote `File` and `String` parameter values inside the
argument string. Unquoted paths such as `inputFile=/data/example_1.tif` are
parsed as SciJava expressions rather than literal file paths.

---

## Command Quick Reference

| Mode | Validated Groovy call | Key outputs |
|------|-----------------------|-------------|
| Derivatives | `new Differentiator().run(new FloatImage(image), 1.5d, 1, 0, 0)` | One 32-bit derivative image |
| Edges | `def out = new Edges().run(new FloatImage(image), 1.5d, true); new Thresholder().hysteresis(out, 20d, 40d)` | One 32-bit image: continuous gradient magnitude if unthresholded, binary `0/255` map if thresholded |
| Laplacian | `def out = new Laplacian().run(new FloatImage(image), 1.5d); new ZeroCrosser().run(out)` | One 32-bit Laplacian image, or binary `0/255` zero-crossing map if enabled |
| Hessian | `new Hessian().run(new FloatImage(image), 1.5d, false)` | `2` eigenimages in 2D, `3` in 3D |
| Structure | `new Structure().run(new FloatImage(image), 1.5d, 3.0d)` | `2` non-negative eigenimages in 2D, `3` in 3D |
| Statistics | `stats.run(image, lower, upper, maskImage); stats.get(Statistics.MEAN)` | Scalar measurements for the full image or an ROI |

---

## 5 Critical Pitfalls

### Pitfall 1 - RGB and indexed-color inputs are rejected

FeatureJ only accepts grayscale ImageJ image types (`8-bit`, `16-bit`, or
`32-bit`). Convert RGB or indexed-color data before running:

```groovy
IJ.run(imp, "8-bit", "")
```

### Pitfall 2 - Too-small or too-large smoothing scales can make derivatives meaningless

FeatureJ's derivative-family filters are scale-space operators. Very small
scales relative to the derivative order introduce sampling artifacts, while
very large scales truncate the Gaussian kernel and wash out the feature.

### Pitfall 3 - `Edges` threshold fields change the output meaning

With both threshold fields empty, `Edges` returns a continuous gradient
magnitude image. With one threshold, it performs hard thresholding. With two
thresholds, it performs hysteresis thresholding and returns a binary map.

### Pitfall 4 - `Hessian` sign interpretation changes when absolute comparison is enabled

Signed Hessian eigenimages distinguish bright-on-dark from dark-on-bright
structures. Absolute comparison removes that polarity information, so results
from signed and absolute runs should not be mixed in the same downstream logic.

### Pitfall 5 - `Statistics` does not support line ROIs, and float median/mode are approximate

FeatureJ `Statistics` accepts area ROIs but not line selections. On `32-bit`
float images, the median and mode are histogram-based estimates rather than
exact values.

---

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Derivative or edge map is dominated by pixel noise | Raise `smoothingScale` |
| Fine boundaries or thin ridges disappear | Lower `smoothingScale` |
| Edge map is almost empty | Lower the `Edges` thresholds |
| Edge map is too thick or full of weak responses | Raise the thresholds and keep non-maximum suppression enabled |
| Hessian or Structure output is too sensitive to tiny local texture | Raise `smoothingScale` and, for Structure, also raise `structureIntegrationScale` |
| Structure eigenimages look too spatially averaged | Lower `structureIntegrationScale` |
| Physical voxel calibration should control smoothing scale | Preserve calibration instead of forcing `new Aspects()` |

---

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin description, image requirements, use cases, installation, limitations, and links |
| `GROOVY_API.md` | Validated direct Groovy API through ImageScience classes, parameter notes, ROI handling, and exclusions |
| `GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy` | **Executable Fiji script**: opens an image, runs one validated FeatureJ mode, and saves TIFF or CSV outputs |
| `UI_GUIDE.md` | GUI reference for each FeatureJ menu entry and the Options dialog |
| `UI_WORKFLOW_MULTI_SCALE_FEATURE_EXTRACTION.md` | **Complete GUI walkthrough**: Derivatives, Edges, Laplacian, Hessian, Structure, and Statistics on one image |
| `SKILL.md` | This file - LLM quick-reference card |
