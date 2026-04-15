# Labkit — UI Workflow: Train, Export, and Reuse a Pixel Classifier

This is the shortest Labkit workflow covered by this skill:
annotate a representative image, train a classifier, export the segmentation,
and save the classifier for batch reuse.

## Before You Start

- Choose a representative image.
- Use images that are similar to each other.
- Normalize brightness and contrast across the dataset.
- Optional background removal can improve reproducibility.

## Step 1 — Open the Representative Image

1. Open the image in Fiji.
2. Start Labkit from `Plugins > Labkit > Open Current Image With Labkit`.
3. If the Labkit window appears black instead of showing the image, press `S`
   and adjust the contrast.

## Step 2 — Label Foreground and Background

1. Select `foreground`.
2. Select the pencil tool and draw on foreground pixels.
3. Select `background`.
4. Mark background pixels with the pencil tool.

Notes:

- Use `D` to draw, `E` to erase, and `F` to flood fill.
- For manual contour-style labeling, you can also use `Add label`, draw a
  contour, then flood fill the interior and save the labeling.

## Step 3 — Train the Pixel Classifier

1. In the Segmentation section, click `Labkit Pixel Classifier`.
2. A new entry named `Labkit Pixel Classifier #1` appears.
3. Click the play button next to that classifier entry.
4. Wait for the segmentation overlay to appear on the image.

## Step 4 — Export the Segmentation Result

1. In Labkit, open `Segmentation > Show Segmentation Result in ImageJ`.
2. In the exported ImageJ result window, save the segmentation as TIFF if you
   want a disk copy for review or benchmarking.

## Step 5 — Save the Classifier for Batch Reuse

1. In Labkit, open `Segmentation > Save Classifier...`.
2. Save the classifier to a known location for reuse in batch workflows.
3. Reuse that saved `.classifier` file with the batch command in
   `GROOVY_API.md`.
