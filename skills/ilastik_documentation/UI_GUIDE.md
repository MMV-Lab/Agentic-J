# ilastik — UI Guide

This guide covers the documented ilastik plugin commands under
`Plugins > ilastik`.

## Installation

- Open `Help > Update...`.
- Click `Manage update sites`.
- Enable the `ilastik` update site.
- Apply updates and restart Fiji.

## Menu Overview

- `Plugins > ilastik > Configure ilastik executable location`
- `Plugins > ilastik > Export HDF5`
- `Plugins > ilastik > Import HDF5`
- `Plugins > ilastik > List HDF5 Datasets`
- `Plugins > ilastik > Run Pixel Classification Prediction`
- `Plugins > ilastik > Run Autocontext Prediction`
- `Plugins > ilastik > Run Object Classification Prediction`
- `Plugins > ilastik > Run Multicut`
- `Plugins > ilastik > Run Tracking`

## Configure ilastik

Use `Plugins > ilastik > Configure ilastik executable location` before running
any prediction wrapper.

Documented fields:

- `Executable path`: path to the ilastik binary executable
- `Threads (-1 for all)`: maximum thread count for ilastik
- `Memory (MiB)`: RAM limit for ilastik

The `.ilp` project file must be closed in ilastik before Fiji runs it.

## HDF5 Tools

### Export HDF5

- Menu path: `Plugins > ilastik > Export HDF5`
- Use it to save the current Fiji image as an HDF5 file that ilastik can open.
- Choose an output file, dataset name, and compression level.
- The plugin docs recommend `0` for raw data and higher compression for label
  or segmentation-like data.

### Import HDF5

- Menu path: `Plugins > ilastik > Import HDF5`
- Use it to open one dataset from an HDF5 file in Fiji.
- Select the HDF5 file, then choose the dataset name.
- Set the axis string so it matches the listed dimensions.

### List HDF5 Datasets

- Menu path: `Plugins > ilastik > List HDF5 Datasets`
- Use it to inspect dataset paths, types, dimensions, and axes before import.

## Prediction Wrappers

### Pixel Classification and Autocontext

- Menu paths:
  - `Plugins > ilastik > Run Pixel Classification Prediction`
  - `Plugins > ilastik > Run Autocontext Prediction`
- Inputs:
  - one raw image
  - one trained `.ilp` project
  - output type: `Probabilities` or `Segmentation`
- Outputs:
  - `Probabilities`: multi-channel float image
  - `Segmentation`: single-channel label image

### Object Classification

- Menu path: `Plugins > ilastik > Run Object Classification Prediction`
- Inputs:
  - one trained `.ilp` project
  - one raw image
  - one additional probability or segmentation image
  - input type: `Probabilities` or `Segmentation`
- Output:
  - one object-class image

### Multicut

- Menu path: `Plugins > ilastik > Run Multicut`
- Inputs:
  - one trained `.ilp` project
  - one raw image
  - one boundary-probability image
- Output:
  - one label image

### Tracking

- Menu path: `Plugins > ilastik > Run Tracking`
- Inputs:
  - one trained `.ilp` project
  - one raw image with a time axis
  - one additional probability or segmentation image with matching dimensions
  - input type: `Probabilities` or `Segmentation`
- Output:
  - one lineage-ID image stack

## Project Compatibility Notes

- Train the project on the same spatial dimensionality that you will process in
  Fiji.
- Keep the channel count and channel order consistent between training and
  inference.
- Exporting training data from Fiji with `Export HDF5` gives the plugin's most
  compatible HDF5 layout.
- Some external example projects reference sibling files under `inputdata/`
  next to the `.ilp` file. Keep that directory layout intact when reusing such
  bundles.

## Scope Boundary

- This guide does not document ilastik training inside Fiji. Train the `.ilp`
  project in ilastik itself.
- The committed Groovy workflows in this skill cover HDF5 export, HDF5 import,
  dataset listing, Pixel Classification, Autocontext, Object Classification,
  Multicut, and Tracking.
