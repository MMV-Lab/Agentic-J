# OrientationJ - UI Workflow For Analysis And Distribution

Use this workflow when you have a grayscale image with visible directional structure and want both local orientation maps and a global orientation histogram.

## Preconditions

- OrientationJ is installed from `BIG-EPFL`
- Fiji has been restarted after installation
- the image is open and active
- the image is grayscale

## Part 1 - Analysis Maps

1. Open the image in Fiji.
2. Run `Plugins > OrientationJ > OrientationJ Analysis`.
3. In the dialog:
   - set `Local window sigma` to `1.0` as a starting point
   - keep `Gradient` on `Cubic Spline`
   - switch the orientation unit to `deg` if you want degree-valued orientation images
   - enable `Energy`
   - enable `Orientation`
   - enable `Coherency`
   - enable `Color-survey`
   - keep color space on `HSB`
   - set `Hue = Orientation`
   - set `Saturation = Coherency`
   - set `Brightness = Original-Image`
4. Click `Run`.
5. Click `Show` beside `Color-survey`.
6. Click `Show` beside `Orientation`.
7. Click `Show` beside `Coherency`.
8. Click `Show` beside `Energy`.

Expected result:

- a color survey image where hue follows local orientation
- a scalar orientation image
- a coherency image
- an energy image

## Part 2 - Orientation Histogram

1. Return to the source image window.
2. Run `Plugins > OrientationJ > OrientationJ Distribution`.
3. In the dialog:
   - keep `Local window sigma` at `1.0`
   - keep `Gradient` on `Cubic Spline`
   - set the angle unit to `deg` if you want degree labels
   - set `Min. Coherency` to `10`
   - set `Min. Energy` to `5`
   - enable `Histogram`
   - enable `Table`
4. Click `Run`.
5. Click `Show` beside `Histogram`.
6. Click `Show` beside `Table`.

Expected result:

- a histogram plot window showing the orientation distribution
- a table with one `Orientation` column and one column per slice

## Save Outputs

1. Save the analysis images as TIFF.
2. Save the histogram plot image if you want a figure.
3. Save the distribution table as CSV.

## Interpreting the Outputs

### Orientation image
- Pixel values are the local dominant angle at that point.
- With the orientation unit set to `deg` and `radian=off` in the macro, values range from about `-90` to `90`.
- With the orientation unit set to `rad` and `radian=on`, values range from about `-π/2` to `π/2` (~`-1.57` to `1.57`).
- The angle convention is the orientation of the structure, not its gradient direction — a horizontal fibre reads near `0°`, a vertical fibre near `±90°`.
- Use a cyclic colormap (e.g. `HSB` or `physics`) in Fiji's `Image > Lookup Tables` when viewing the orientation image; linear grayscale does not reflect the angular nature of the data.

### Coherency image
- Values range from `0` to `1`.
- `0` means the neighborhood is isotropic (no preferred direction).
- `1` means the neighborhood is perfectly aligned along one direction.
- In practice, fibrous structures give coherency in the `0.3`–`0.9` range; flat background gives values near `0`.

### Energy image
- Reflects how much gradient signal exists locally.
- Low-energy regions (near-constant intensity) carry unreliable orientation estimates — treat them as masked-out even when the orientation value is numerically defined.

### Color survey
- The default encoding is `Hue = Orientation`, `Saturation = Coherency`, `Brightness = Original-Image`.
- Bright, saturated pixels = strong signal with well-defined orientation.
- Washed-out / near-grey pixels = low coherency (no preferred direction there).
- Dark pixels = low source intensity regardless of orientation.

### Distribution histogram
- X axis = orientation (degrees or radians); Y axis = summed coherency of pixels falling into that bin.
- A single narrow peak = strongly aligned sample.
- A broad peak or multiple peaks = multiple fibre populations or weak alignment.
- Pixels below `Min. Coherency` or `Min. Energy` are excluded, so a histogram that looks empty is often a threshold problem, not a data problem.

### Dominant Direction table
- Returns one angle and one coherency percentage per slice.
- Use it when you need a single summary number per image rather than a full distribution.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Orientation map looks noisy / speckled | `Local window sigma` too small | Increase `Local window sigma` (e.g. 1.0 → 2.0 or 3.0) |
| Fine fibre directions are averaged out | `Local window sigma` too large | Decrease `Local window sigma` (e.g. 1.0 → 0.5) |
| Histogram is empty or nearly empty | Thresholds too high | Lower `Min. Coherency` and `Min. Energy` |
| Histogram dominated by background | Thresholds too low | Raise `Min. Coherency` to suppress weakly oriented pixels |
| Color survey looks washed out everywhere | Sample has low coherency overall | Check the coherency image; the sample may genuinely be isotropic |
| Orientation image values are near `±1.5` instead of `±90` | `radian=on` is set | Switch orientation unit to `deg` or set `radian=off` in the macro |
| RGB image is rejected | Plugin requires grayscale | `Image > Type > 8-bit` first |
| No visible output window appears | Feature checkbox was off | Re-open the dialog and enable the relevant output checkbox |

## Related Modes

- `Plugins > OrientationJ > OrientationJ Vector Field` — discrete direction vectors on a grid, for figures.
- `Plugins > OrientationJ > OrientationJ Corner Harris` — Harris corner detection using the structure tensor.
- `Plugins > OrientationJ > OrientationJ Dominant Direction` — one dominant angle per slice when a full histogram is not needed.
- `Plugins > OrientationJ > OrientationJ Measure` — ROI-based orientation/coherency measurement to the log.
