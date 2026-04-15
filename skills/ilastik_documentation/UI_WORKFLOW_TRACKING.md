# ilastik — UI Workflow: Run a Pre-trained Tracking Project

Use this workflow when you already have a trained ilastik Tracking project and
want to apply it in Fiji to a raw time series plus a matching probability or
segmentation input.

## Before You Start

- Enable the `ilastik` update site in Fiji and restart.
- Have a trained Tracking `.ilp` project ready.
- Close that `.ilp` project in ilastik before Fiji runs it.
- Open the raw time-series image in Fiji.
- Open the matching probability or segmentation image in Fiji.
- Make sure both open images describe the same time axis and scene.

## Step 1 — Configure the ilastik Executable

1. Open `Plugins > ilastik > Configure ilastik executable location`.
2. Set the path to the ilastik executable.
3. Set the thread limit and RAM limit if needed.
4. Save the configuration.

## Step 2 — Start the Prediction Dialog

1. Open `Plugins > ilastik > Run Tracking`.
2. Select the trained `.ilp` project file.
3. Select the raw time-series image.
4. Select the matching probability or segmentation image.
5. Choose the matching second-input type.

## Step 3 — Run the Prediction

1. Start the command.
2. Watch the ImageJ console if you need status messages.

## Step 4 — Inspect the Result

1. Inspect the returned lineage-ID image stack over time.
2. Apply a LUT such as `Image > Lookup Tables > glasbey_on_dark` if the labels
   look dark.

## Notes

- This workflow applies an existing ilastik project. It does not train one.
- Keep the raw image and the second input aligned in time and scene content.
- For headless execution from Fiji scripting, use
  `GROOVY_WORKFLOW_TRACKING.groovy`.
