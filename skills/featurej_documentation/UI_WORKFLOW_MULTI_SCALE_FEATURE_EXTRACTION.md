# FeatureJ - UI Workflow: Multi-Scale Feature Extraction

## Goal

Run the main FeatureJ modes on one grayscale image so you can compare:

- first-order derivatives
- thresholded edge maps
- Laplacian zero-crossings
- Hessian eigenimages
- Structure-tensor eigenimages
- ROI-based statistics

## Preconditions

- FeatureJ is installed from the `ImageScience` update site
- one grayscale image is open and active
- the image is `8-bit`, `16-bit`, or `32-bit`
- for the settings below, `data/example_1.tif` is a suitable test image

## 1. Prepare the Image

1. Open the image.
2. If the image is RGB, convert it first with `Image > Type > 8-bit` or another grayscale type.
3. If physical voxel calibration matters for your smoothing scale, confirm it in `Image > Properties...` before opening `FeatureJ Options`.

## 2. Derivatives

1. Open `Plugins > FeatureJ > FeatureJ Derivatives`.
2. Set `x-Order = 1`.
3. Set `y-Order = 0`.
4. Set `z-Order = 0`.
5. Set `Smoothing scale = 1.5`.
6. Click `OK`.

Expected result:

- one signed derivative image opens
- positive and negative values indicate opposite transition directions

## 3. Edges

1. Open `Plugins > FeatureJ > FeatureJ Edges`.
2. Enable `Compute gradient-magnitude image`.
3. Set `Smoothing scale = 1.5`.
4. Enable `Suppress non-maximum gradients`.
5. Set `Lower threshold value = 20`.
6. Set `Higher threshold value = 40`.
7. Click `OK`.

Expected result:

- one edge map opens
- with two thresholds, the output is a binary `0/255` image

## 4. Laplacian

1. Open `Plugins > FeatureJ > FeatureJ Laplacian`.
2. Enable `Compute Laplacian image`.
3. Set `Smoothing scale = 1.5`.
4. Enable `Detect zero-crossings`.
5. Click `OK`.

Expected result:

- one zero-crossing map opens
- with zero-crossing detection enabled, the output is binary `0/255`

## 5. Hessian

1. Open `Plugins > FeatureJ > FeatureJ Hessian`.
2. Enable `Largest eigenvalue of Hessian tensor`.
3. Disable `Middle eigenvalue of Hessian tensor` for a 2D image.
4. Enable `Smallest eigenvalue of Hessian tensor`.
5. Disable `Absolute eigenvalue comparison`.
6. Set `Smoothing scale = 1.5`.
7. Click `OK`.

Expected result:

- for a 2D image, two eigenimages open
- the sign of the eigenvalues is preserved because absolute comparison is off

## 6. Structure

1. Open `Plugins > FeatureJ > FeatureJ Structure`.
2. Enable `Largest eigenvalue of structure tensor`.
3. Disable `Middle eigenvalue of structure tensor` for a 2D image.
4. Enable `Smallest eigenvalue of structure tensor`.
5. Set `Smoothing scale = 1.5`.
6. Set `Integration scale = 3.0`.
7. Click `OK`.

Expected result:

- for a 2D image, two structure-tensor eigenimages open
- values are non-negative

## 7. Statistics

1. Draw a rectangular ROI on the active image, for example a `128 x 128` region.
2. Open `Plugins > FeatureJ > FeatureJ Statistics`.
3. Enable the metrics you want, for example:
   `Minimum`, `Maximum`, `Mean`, `Median`, `Variance`, `Skewness`, `Kurtosis`.
4. Enable `Image name displaying` if you will measure several images.
5. Set `Decimal places = 3`.
6. Click `OK`.

Expected result:

- one new row is appended to the ImageJ results table
- measurements are limited to the ROI if one was present

## Interpretation

| Output | How to read it |
|--------|----------------|
| `Derivatives` | Values are signed. Positive and negative regions indicate opposite intensity-change directions. Large magnitude means a strong local transition. |
| `Edges` | With thresholds applied, values are binary `0/255`. White pixels are accepted edges after suppression and thresholding. |
| `Laplacian` zero-crossings | Binary `0/255`. White pixels mark detected sign changes in the Laplacian response. |
| `Hessian` eigenimages | In 2D, the largest and smallest eigenvalue images summarize local second-order curvature. Signed outputs preserve bright-on-dark vs dark-on-bright polarity. |
| `Structure` eigenimages | Values are non-negative. Large largest-eigenvalue responses indicate strong local directional structure. The smallest eigenvalue tends toward zero in strongly anisotropic regions. |
| `Statistics` | `Mean`, `Variance`, `Skewness`, and `Kurtosis` summarize the selected ROI or full image. On float images, `Median` and `Mode` are approximate histogram-based values. |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| FeatureJ reports that the image is not grayscale | RGB or indexed-color image | Convert to `8-bit`, `16-bit`, or `32-bit` grayscale first |
| Derivative or Hessian result looks dominated by speckle | `Smoothing scale` too small | Raise the smoothing scale |
| Fine structures disappear | `Smoothing scale` or `Integration scale` too large | Lower the corresponding scale |
| Edge map is almost empty | Thresholds are too high | Lower the lower and higher thresholds |
| Edge map is thick or noisy | Non-maximum suppression is off, or thresholds are too low | Enable suppression and raise thresholds |
| Hessian signs are hard to interpret | Signed eigenvalues are being compared to absolute-magnitude expectations | Enable `Absolute eigenvalue comparison` for magnitude-only interpretation |
| Statistics does not work on the selection | A line ROI was used | Switch to an area ROI such as a rectangle, oval, polygon, or freehand area |
