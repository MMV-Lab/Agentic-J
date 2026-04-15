# ilastik — UI Workflow: Run a Pre-trained Object Classification Project

Use this workflow when you already have a trained ilastik object-classification
project and want to apply it in Fiji to a raw image plus a matching probability
or segmentation image.

## Before You Start

- Enable the `ilastik` update site in Fiji and restart.
- Have a trained Object Classification `.ilp` project ready.
- Close that `.ilp` project in ilastik before Fiji runs it.
- Open the raw image in Fiji.
- Open the matching probability or segmentation image in Fiji.
- Make sure both open images describe the same scene and dimensions.

## Step 1 — Configure the ilastik Executable

1. Open `Plugins > ilastik > Configure ilastik executable location`.
2. Set the path to the ilastik executable.
3. Set the thread limit and RAM limit if needed.
4. Save the configuration.

## Step 2 — Start the Prediction Dialog

1. Open `Plugins > ilastik > Run Object Classification Prediction`.
2. Select the trained `.ilp` project file.
3. Select the raw image.
4. Select the probability or segmentation image.
5. Choose the matching second-input type.

## Step 3 — Choose the Output Type

1. Choose `Object Predictions` for one class-valued image.
2. Choose `Object Probabilities` for per-class object scores.
3. Choose `Object Identities` for the object-identity image.

## Step 4 — Run the Prediction

1. Start the command.
2. Watch the ImageJ console if you need status messages.

## Step 5 — Inspect the Result

1. For `Object Predictions`, apply a LUT such as
   `Image > Lookup Tables > glasbey_on_dark` if the image looks dark.
2. For `Object Probabilities`, inspect the returned float image channels.
3. For `Object Identities`, inspect the integer-valued identity map.

## Notes

- This workflow applies an existing ilastik project. It does not train one.
- Keep the raw image and the second input aligned in dimensionality and scene
  content.
- For headless execution from Fiji scripting, use
  `GROOVY_WORKFLOW_OBJECT_CLASSIFICATION.groovy`.
