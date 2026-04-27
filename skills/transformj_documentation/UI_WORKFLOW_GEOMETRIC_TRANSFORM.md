# TransformJ GUI Workflow: Geometric Transformation

## Preconditions

- TransformJ and ImageScience are installed with compatible versions.
- The input image is open in Fiji.
- For Affine, a 4 x 4 matrix text file is available, or the Matrix editor will be used to create one.
- Choose nearest-neighbor interpolation for masks and labels unless interpolation of label values is intended.

## Workflow A: Resize an Intensity Image

1. Open the image.
2. Choose `Plugins > ImageScience > TransformJ > TransformJ Scale`.
3. Set `x-Factor`, `y-Factor`, and `z-Factor`.
4. Choose `Interpolation`.
5. Enable `Preserve physical image dimensions` only when the output should keep the same physical extent with adjusted voxel spacing.
6. Click `OK`.
7. Save the result with `File > Save As > Tiff...`.

## Workflow B: Shift an Image by a Known Offset

1. Open the image.
2. Choose `Plugins > ImageScience > TransformJ > TransformJ Translate`.
3. Enter `x-Distance`, `y-Distance`, and `z-Distance`.
4. Enable `Voxel units for distances` when the offsets are in pixels or slices.
5. Choose `Interpolation`.
6. Set `Background` to the value that should fill uncovered output areas.
7. Click `OK`.
8. Save the result.

## Workflow C: Rotate Without Clipping

1. Open the image.
2. Choose `Plugins > ImageScience > TransformJ > TransformJ Rotate`.
3. Enter `z-Angle`, `y-Angle`, and `x-Angle`.
4. Choose `Interpolation`.
5. Set `Background`.
6. Enable `Adjust bounds to fit result`.
7. Enable `Resample isotropically` only when anisotropic voxel spacing would otherwise lose resolution.
8. Enable `Anti-alias borders` when the image-background boundary shows stair steps.
9. Click `OK`.
10. Save the result.

## Workflow D: Preserve Exact Label Values

Use exact operations when possible:

1. For 90-degree rotations, choose `TransformJ Turn`, select `z-Angle`, `y-Angle`, and `x-Angle`, then click `OK`.
2. For flips, choose `TransformJ Mirror`, select one or more dimension checkboxes, then click `OK`.
3. For subvolumes, choose `TransformJ Crop`, enter inclusive ranges, then click `OK`.
4. Save the result.

## Workflow E: Apply a 4 x 4 Matrix

1. Open the image.
2. Choose `Plugins > ImageScience > TransformJ > TransformJ Affine`.
3. Enter a full `Matrix file` path, or click `Create` to open `TransformJ Matrix`.
4. In the Matrix editor, compose transforms with `Rotate`, `Scale`, `Shear`, and `Translate`, or edit matrix values directly.
5. Click `Save` in the Matrix editor, then close it.
6. In the Affine dialog, choose `Interpolation`, `Background`, `Adjust bounds to fit result`, `Resample isotropically`, and `Anti-alias borders`.
7. Click `OK`.
8. Save the transformed image.

## Interpretation

| Output | How to read it |
|--------|----------------|
| Scale | Pixel values are interpolated unless nearest neighbor is used. Output dimensions follow scale factors or derived output sizes. |
| Translate | Output dimensions match input dimensions. Uncovered areas contain the selected background value. |
| Rotate | With `Adjust bounds` enabled, dimensions expand to fit the rotated image. Without it, content outside the original bounds is clipped. |
| Turn | Values are reordered exactly. This is suitable for label images and masks. |
| Mirror | Values are reordered exactly along selected axes. |
| Crop | The output contains the inclusive range selected in each dimension. |
| Embed | The original image appears at the requested position inside a larger image; outside regions follow the selected background mode. |
| Affine | The output follows the 4 x 4 matrix under TransformJ's center-origin coordinate convention. |

For quantitative intensity images, inspect whether interpolation changed intensity statistics in regions of interest. For labels, verify that the unique label values are still valid after any interpolated operation.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| TransformJ menu is missing | Plugin jar is absent or Fiji was not restarted | Install TransformJ and ImageScience, then restart Fiji |
| TransformJ reports an ImageScience version error | ImageScience jar is older than the TransformJ requirement | Install ImageScience 3.1.0 for TransformJ 4.1.0 |
| Rotated result is clipped | `Adjust bounds to fit result` is disabled | Re-run Rotate or Affine with `Adjust bounds` enabled |
| Label image has fractional or blended values | Interpolation was used on categorical data | Use Turn/Mirror/Crop where possible, or use nearest-neighbor interpolation |
| Translation offset is too small or too large | Physical units and voxel units were mixed | Toggle `Voxel units for distances` or check image calibration |
| Crop range error | x/y and z/t/c indexing conventions were mixed | Use 0-based x/y ranges and 1-based z/t/c ranges in the GUI |
| Embed fails because the image does not fit | Output size or start position leaves insufficient room | Increase output size or lower the position values |
| Affine result is empty or far from expected | Matrix direction, units, or center-origin convention is wrong | Check the 4 x 4 matrix, try identity plus one transform in Matrix, and enable `Adjust bounds` |
| Output takes too long or runs out of memory | High-order interpolation, isotropic resampling, or large adjusted bounds | Use a lower-order interpolation, crop first, or disable isotropic resampling |
