# ilastik — UI Workflow: Run a Pre-trained Multicut Project

Use this workflow when you already have a trained ilastik Multicut project and
want to apply it in Fiji to a raw image plus a matching boundary-probability
image.

## Before You Start

- Enable the `ilastik` update site in Fiji and restart.
- Have a trained Multicut `.ilp` project ready.
- Close that `.ilp` project in ilastik before Fiji runs it.
- Open the raw image in Fiji.
- Open the matching boundary-probability image in Fiji.
- Make sure both open images describe the same volume and dimensions.

## Step 1 — Configure the ilastik Executable

1. Open `Plugins > ilastik > Configure ilastik executable location`.
2. Set the path to the ilastik executable.
3. Set the thread limit and RAM limit if needed.
4. Save the configuration.

## Step 2 — Start the Prediction Dialog

1. Open `Plugins > ilastik > Run Multicut`.
2. Select the trained `.ilp` project file.
3. Select the raw image.
4. Select the boundary-probability image.

## Step 3 — Run the Prediction

1. Start the command.
2. Watch the ImageJ console if you need status messages.

## Step 4 — Inspect the Result

1. Inspect the returned label image.
2. Apply a LUT such as `Image > Lookup Tables > glasbey` if the labels look
   dark.

## Notes

- This workflow applies an existing ilastik project. It does not train one.
- Keep the raw image and the boundary-probability image aligned in scene and
  dimensions.
- For headless execution from Fiji scripting, use
  `GROOVY_WORKFLOW_MULTICUT.groovy`.
