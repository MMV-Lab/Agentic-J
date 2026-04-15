# ilastik — UI Workflow: Run a Pre-trained Autocontext Project

Use this workflow when you already have a trained ilastik Autocontext project
and want to apply it to an image from Fiji.

## Before You Start

- Enable the `ilastik` update site in Fiji and restart.
- Have a trained Autocontext `.ilp` project file ready.
- Close that `.ilp` project in ilastik before Fiji runs it.
- Open the raw image in Fiji.
- Make sure the image dimensionality and channel layout match the project.

## Step 1 — Configure the ilastik Executable

1. Open `Plugins > ilastik > Configure ilastik executable location`.
2. Set the path to the ilastik executable.
3. Set the thread limit and RAM limit if needed.
4. Save the configuration.

## Step 2 — Start the Prediction Dialog

1. Open `Plugins > ilastik > Run Autocontext Prediction`.
2. If multiple images are open, select the raw input image in the dialog.
3. Select the trained `.ilp` project file.

## Step 3 — Choose the Output Type

1. Choose `Probabilities` when you need the stage-2 class probabilities.
2. Choose `Segmentation` when you need the stage-2 segmentation result.

## Step 4 — Run the Prediction

1. Start the command.
2. Watch the ImageJ console if you need status messages.

## Step 5 — Inspect the Result

1. For probability output, inspect the returned float image channels.
2. For segmentation output, apply a LUT such as
   `Image > Lookup Tables > glasbey` if the label image looks dark.

## Notes

- This workflow applies an existing ilastik project. It does not train one.
- For headless execution from Fiji scripting, use
  `GROOVY_WORKFLOW_AUTOCONTEXT.groovy`.
