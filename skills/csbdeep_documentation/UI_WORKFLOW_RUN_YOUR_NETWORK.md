# CSBDeep UI Workflow: Run Your Network

## Preconditions

- Fiji has the `CSBDeep` update site enabled and has been restarted.
- You have an exported CSBDeep / CARE model ZIP or a direct URL to one.
- The input image is already open in Fiji.
- The selected model is compatible with the image dimensionality and content.

## Steps

1. Open the image you want to restore in Fiji.
2. Run `Plugins > CSBDeep > Run your network`.
3. Choose one model source:
   `Import model (.zip)` for a local exported ZIP, or
   `Import model (.zip) from URL` for a remote ZIP.
4. Leave input normalization enabled unless the model documentation says the image is already normalized.
5. Set the lower and upper normalization percentiles. The plugin defaults are `3.0` and `99.8`.
6. Set `Number of tiles`. Increase this if the image is large or the run exhausts memory.
7. Keep `Tile size has to be multiple of` at the model-appropriate value. The generic command defaults to `32`.
8. Increase `Overlap between tiles` if you see visible tile seams.
9. Leave `Batch size` at `1` unless the model and available memory support larger batches.
10. Click `OK` to run the model.
11. Inspect the new output image window and save it to a fresh path if the result looks correct.

## Interpretation

- For `Run your network`, the output is a new restored image produced by the selected model.
- A successful result should preserve the input field of view while reducing noise or applying the model's intended transformation.
- Good results look cleaner or sharper without introducing obvious tiled seams, duplicated structures, or new hallucinated objects.
- If the model is probabilistic or architecture-specific, the channel layout can differ from the input. Check the output dimensions before downstream analysis.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No output image appears | Invalid model source or runtime failure before output creation | Re-check the model ZIP / URL and inspect the Fiji log |
| Immediate TensorFlow load error | Broken or manually reconfigured TensorFlow runtime | Reconfigure TensorFlow from `Edit > Options > TensorFlow...` or restore the container's default Fiji installation |
| Out-of-memory failure | Tiles are too large for available memory | Increase `Number of tiles` and reduce `Batch size` |
| Visible seams between tiles | Overlap is too small | Increase `Overlap between tiles` |
| Output contrast looks clipped or flat | Percentile normalization is too aggressive | Widen the percentile range or disable input normalization |
| Model rejects the image shape | Input dimensionality does not match the model | Use a compatible image or switch to a model trained for that layout |
