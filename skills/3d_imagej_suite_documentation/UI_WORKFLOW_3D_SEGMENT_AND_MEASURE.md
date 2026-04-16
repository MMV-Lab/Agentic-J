# 3D ImageJ Suite — UI Workflow: Segment And Measure Bright 3D Objects

This workflow uses Fiji's graphical interface to smooth a 3D stack, threshold
it, label connected 3D objects, and measure both volume and intensity.

## Before You Start

- Confirm `Plugins > 3DSuite` is present in Fiji.
- Open a 3D grayscale stack with bright objects on a dark background.
- If you want to reproduce the validation workflow from this repo, first export
  `data/ilastik_validation/core/3d1c.h5` to a TIFF stack outside this workflow.

## Step 1 — Open The 3D Stack

1. `File > Open...`
2. Select your 3D TIFF stack.
3. Scroll through slices and confirm the objects are brighter than the background.

## Step 2 — Smooth The Stack

1. Make the input stack active.
2. Open `Plugins > 3DSuite > Filters > 3D Fast Filters`.
3. Set:
   - `Filter` = `Mean`
   - `Radius X` = `1`
   - `Radius Y` = `1`
   - `Radius Z` = `1`
4. Click `OK`.

Result: a new filtered stack is created.

## Step 3 — Threshold To A Binary Stack

1. Make the filtered stack active.
2. Open `Image > Adjust > Threshold...`
3. Adjust the threshold until the bright objects are fully selected.
4. Click `Apply`.
5. If Fiji asks how to convert the stack, accept stack-wide conversion so the
   result contains only `0` and `255` voxel values.

Result: a binary 3D stack suitable for `3D Simple Segmentation`.

## Step 4 — Label Connected 3D Objects

1. Keep the binary stack active.
2. Open `Plugins > 3DSuite > Segmentation > 3D Simple Segmentation`.
3. Use:
   - `Seeds` = `None`
   - `Low threshold (included)` = `128`
   - `Min size` = `20`
   - `Max size (-1 for infinity)` = `-1`
   - `Individual voxels are objects` = unchecked
   - `32-bit segmentation (nb objects > 65,535)` = unchecked unless needed
4. Click `OK`.

Result: a labelled 3D stack is created, with one integer label per object.

## Step 5 — Measure Object Volume

1. Make the labelled stack active.
2. Open `Plugins > 3DSuite > Analysis > 3D Volume`.
3. Review the `Results` table.

The table reports per-object voxel volume and calibrated volume. Save the table
from the Results window with `File > Save As...`.

## Step 6 — Measure Intensity On The Original Signal

1. Keep both the labelled stack and the original grayscale stack open.
2. Open `Plugins > 3DSuite > Analysis > 3D Intensity Measure`.
3. In the dialog:
   - `Objects` = the labelled stack from Step 4
   - `Signal` = the original or filtered grayscale stack
4. Click `OK`.

The `Results` table reports per-object mean, minimum, maximum, standard
deviation, and integrated density. Save the table from the Results window with
`File > Save As...`.

## Optional Step — Inspect Objects In 3D Manager

1. Make the labelled stack active.
2. Open `Plugins > 3DSuite > 3D Manager`.
3. Add or import the current image into the manager.
4. Use `3D Manager Options` if you need additional geometry or intensity fields.

## Troubleshooting

| Symptom | Likely cause | Fix |
|--------|--------------|-----|
| No objects are labelled | Threshold is too high or the binary stack is inverted | Lower the threshold or invert so objects are bright |
| One large merged object appears | The thresholded objects still touch | Use a stronger threshold or switch to the seeded `3D Watershed` workflow |
| Too many tiny objects are reported | Noise survives the threshold | Increase the mean-filter radius or raise `Min size` |
| The intensity table is empty | The wrong image was chosen for `Objects` | Select the labelled stack, not the raw grayscale stack |
