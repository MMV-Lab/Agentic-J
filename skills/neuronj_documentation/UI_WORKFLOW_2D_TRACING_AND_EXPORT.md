# NeuronJ - 2D Tracing and Export Workflow

## Preconditions

- `NeuronJ_.jar` and `imagescience.jar` are installed and Fiji has been restarted.
- The image is 2D and 8-bit grayscale or indexed color.
- Pixel size and unit are set in `Image > Properties` if calibrated length measurements are required.
- The image file is saved on disk; keep the `.ndf` file in the same folder with the same basename when automatic reload is desired.

## Workflow

1. Launch `Plugins > NeuronJ`.
2. In the NeuronJ toolbar, choose `Load image/tracings`.
3. Select the image to trace, or select an existing `.ndf` file to reload saved tracings and settings.
4. Open `Set parameters`.
5. Choose `Bright` or `Dark` for Neurite appearance.
6. Adjust Hessian smoothing scale, cost weight factor, snap window size, path-search window size, tracing smoothing range, and tracing subsampling factor as needed.
7. Choose `Add tracings`.
8. Click the start of a neurite.
9. Move along the neurite. When the proposed path is correct, click to fix the segment.
10. Continue adding anchor clicks until the neurite end is reached.
11. Finish the tracing with a double click, Tab, or Space.
12. Use Shift for temporary straight-line tracing in regions where the automatic path deviates.
13. Use Ctrl to temporarily disable cursor snapping when the snap target is wrong.
14. Use `Move vertices` to correct individual points after tracing.
15. Use `Label tracings` to set type, cluster, and label values.
16. Use `Measure tracings` to generate group, tracing, or vertex measurements.
17. Use `Save tracings` to write the `.ndf` file.
18. Use `Export tracings` to write text coordinate files or per-tracing `.roi` files.
19. Optionally run `GROOVY_WORKFLOW_NDF_EXPORT.groovy` on the saved `.ndf` file to create reproducible CSV and ROI outputs.

## Interpretation

An `.ndf` file stores tracing geometry and NeuronJ settings. It is the working save file for reloading and editing traces.

Text exports contain vertex coordinates, one vertex per line. A single-file export groups coordinates by tracing. Separate-file exports write one file per tracing and an overview file that lists the generated paths.

Measurement windows use pixels unless `Calibrate measurements` is enabled. With calibration enabled, length units and pixel dimensions come from `Image > Properties`; image values use the active calibration table when applicable.

Group measurements summarize selected tracings by type and cluster. Tracing measurements report one row per tracing. Vertex measurements report coordinates and image values at saved vertices.

ROI exports are ImageJ segmented-line selections. They are useful for downstream ImageJ ROI workflows but do not preserve NeuronJ type, cluster, label, or algorithm parameters.

The checked-in NDF workflow reports geometry from saved vertices. Its calibrated length columns are valid only when the supplied pixel width, pixel height, and unit match the original image calibration.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Plugins > NeuronJ` is missing | `NeuronJ_.jar` is not installed or Fiji was not restarted | Install `NeuronJ_.jar` into `plugins/`, confirm `imagescience.jar`, and restart Fiji |
| NeuronJ does not trace the currently open image | NeuronJ ignores the active image at launch | Load the image through the NeuronJ toolbar |
| Image is rejected on load | Input is not 2D 8-bit grayscale or indexed color | Convert the image before tracing |
| Suggested path follows background or a neighboring neurite | Appearance, snapping, or path costs do not match the image | Set Bright/Dark correctly, reduce snap window size, tune Hessian smoothing scale/cost weight, or use Shift for manual segments |
| Path search is slow after each click | Path-search window is too large for the image or machine | Reduce path-search window size and place anchor clicks closer together |
| Tracing loses sharp bends | Smoothing or subsampling is too strong | Reduce tracing smoothing range or tracing subsampling factor |
| Length units are pixels when microns were expected | Calibration was not enabled or image properties were not set | Set `Image > Properties`, enable `Calibrate measurements`, and rerun measurements |
| NDF CSV lengths do not match manual calibrated measurements | Workflow pixel size/unit did not match the original image | Pass the original `pixelWidth`, `pixelHeight`, and `lengthUnit` to `GROOVY_WORKFLOW_NDF_EXPORT.groovy` |
