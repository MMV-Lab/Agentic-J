# FeatureJ - OVERVIEW

## What It Is

FeatureJ is a Fiji/ImageJ plugin suite for extracting multi-scale differential
features from grayscale images. The package groups several related operators:

- `Derivatives` for Gaussian-scaled partial derivatives
- `Edges` for Canny-style edge detection
- `Laplacian` for second-order response and zero-crossings
- `Hessian` for eigenvalue-based ridge, blob, and plate cues
- `Structure` for structure-tensor eigenvalues and directional texture strength
- `Statistics` for gray-value measurements over the full image or an ROI

The official FeatureJ pages describe the menu-driven interface. In this repo,
the validated automation path uses the installed `imagescience.*` classes that
FeatureJ itself calls internally.

---

## Typical Inputs and Use Cases

### Membrane and boundary highlighting

- **Input:** grayscale fluorescence, brightfield, or histology image
- **Path:** `Edges` with non-maximum suppression and one or two thresholds
- **Goal:** binary or near-binary edge maps for QA, segmentation seeding, or figure overlays

### Neurite, vessel, and curvilinear structure analysis

- **Input:** 2D or 3D grayscale image with elongated bright or dark structures
- **Path:** `Hessian`
- **Goal:** distinguish line-like or blob-like responses through the Hessian eigenimages

### Oriented texture and fiber organization

- **Input:** fibrous or anisotropic grayscale image
- **Path:** `Structure`
- **Goal:** quantify directional structure strength using the largest and smallest structure-tensor eigenvalues

### Custom derivative feature design

- **Input:** image where first- or higher-order derivatives are the desired intermediate
- **Path:** `Derivatives`
- **Goal:** create signed derivative maps for downstream filters or custom measurements

### Laplacian and zero-crossing feature maps

- **Input:** grayscale image with blob-like or edge-like transitions
- **Path:** `Laplacian`
- **Goal:** inspect the second-order response directly or export a zero-crossing map

### ROI-based quality control

- **Input:** raw image or any FeatureJ-derived output image
- **Path:** `Statistics`
- **Goal:** measure intensity range, variance, skewness, kurtosis, and related metrics in a full image or ROI

---

## Input Image Requirements

| Requirement | Details |
|-------------|---------|
| Dimensionality | 2D images, stacks, hyperstacks, and grayscale 5D images |
| Bit depth | `8-bit`, `16-bit`, or `32-bit` grayscale |
| Channels / time | Per-channel and per-time-point processing is supported by the official FeatureJ surface |
| Calibration | Optional. FeatureJ can either respect pixel/voxel spacing or treat smoothing scales as pixel units |
| Color data | RGB and indexed-color images are rejected by the FeatureJ input check |

---

## Output Types

| Output | Produced by | What it contains |
|--------|-------------|------------------|
| Derivative image | `Derivatives` | One signed float32 image for the selected derivative orders |
| Gradient magnitude or binary edge map | `Edges` | Continuous edge strength when unthresholded, binary `0/255` map when thresholded |
| Laplacian image or zero-crossing map | `Laplacian` | Signed second-order response, or binary `0/255` zero-crossing output |
| Hessian eigenimages | `Hessian` | `2` float32 eigenimages in 2D, `3` in 3D; sign depends on absolute-comparison setting |
| Structure eigenimages | `Structure` | `2` float32 eigenimages in 2D, `3` in 3D; values are non-negative |
| Results table or CSV | `Statistics` | Full-image or ROI measurements such as mean, variance, skewness, and kurtosis |

---

## Automation Level

- **Official UI surface:** `Derivatives`, `Edges`, `Laplacian`, `Hessian`, `Structure`, `Statistics`, `Options`, `Panel`, and `Help`
- **Validated Groovy automation path in this repo:** direct `imagescience.feature.*`, `imagescience.segment.*`, and `imagescience.image.*` classes
- **Checked-in workflow:** [GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy](GROOVY_WORKFLOW_FEATURE_EXTRACTION.groovy) saves TIFF and CSV outputs for one selected mode
- **Launcher note:** this skill does not rely on bare `fiji-linux-x64 --headless --run` as the adopted execution path in the current container; use Fiji's Script Editor or a SciJava-aware launcher for the workflow file

---

## Installation

**Fiji (recommended):**
1. Open `Help > Update...`
2. Click `Manage update sites`
3. Enable `ImageScience`
4. Click `Apply changes`
5. Restart Fiji

**Manual install:**
Download `FeatureJ_.jar` and `imagescience.jar` from the official FeatureJ
download page and place them in Fiji's `plugins/` and `jars/` directories
respectively.

---

## Known Limitations

- **Grayscale only:** FeatureJ rejects RGB and indexed-color inputs.
- **Two eigenimages in 2D:** `Hessian` and `Structure` return only largest and smallest eigenvalues on single-slice images; the middle eigenvalue exists only in 3D.
- **Persistent UI options:** the `FeatureJ Options` dialog writes preferences that affect later manual runs.
- **Statistics ROI limits:** line ROIs are not supported.
- **Float median and mode:** on `32-bit` images these are histogram-based approximations.
- **This skill excludes `Panel`, `Help`, and `About` from automation claims:** they are part of the UI surface but not adopted as scripted workflow steps here.
- **This skill does not claim direct `IJ.run(...)` macro strings as the primary automation surface:** the direct ImageScience API is the validated path in this repo.

---

## Links

| Resource | URL |
|----------|-----|
| FeatureJ main page | https://imagescience.org/meijering/software/featurej/ |
| ImageJ plugin page | https://imagej.net/plugins/featurej |
| Derivatives docs | https://imagescience.org/meijering/software/featurej/derivatives/ |
| Edges docs | https://imagescience.org/meijering/software/featurej/edges/ |
| Laplacian docs | https://imagescience.org/meijering/software/featurej/laplacian/ |
| Hessian docs | https://imagescience.org/meijering/software/featurej/hessian/ |
| Structure docs | https://imagescience.org/meijering/software/featurej/structure/ |
| Statistics docs | https://imagescience.org/meijering/software/featurej/statistics/ |
| Options docs | https://imagescience.org/meijering/software/featurej/options/ |
| Release notes | https://imagescience.org/meijering/software/featurej/releases/ |
| ImageScience update site | https://sites.imagej.net/ImageScience/ |
