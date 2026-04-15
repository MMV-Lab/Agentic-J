# ilastik — Overview

`ilastik4ij` wraps selected ilastik workflows inside Fiji. The plugin moves data
between Fiji and ilastik through temporary HDF5 files, and it can also expose
the HDF5 transfer steps directly as menu commands.

## Core Capabilities

- HDF5 export from Fiji to ilastik-compatible `.h5`
- HDF5 import from `.h5` into Fiji with explicit dataset selection
- HDF5 dataset inspection before import
- Pixel Classification inference from a trained `.ilp` project
- Autocontext inference from a trained `.ilp` project
- Object Classification inference from a trained `.ilp` project plus a second
  probability or segmentation image
- Multicut inference from a trained `.ilp` project plus a boundary-probability
  image
- Tracking inference from a trained `.ilp` project plus a second probability or
  segmentation time series

## Committed Workflow Coverage

The committed Groovy workflows in this skill cover:

- `Export HDF5`
- `Import HDF5`
- `List HDF5 Datasets`
- `Run Pixel Classification Prediction`
- `Run Autocontext Prediction`
- `Run Object Classification Prediction`
- `Run Multicut`
- `Run Tracking`

## Compatibility Boundary

- Configure the ilastik executable before running any prediction wrapper.
- Close the `.ilp` project in ilastik before Fiji runs it.
- Keep spatial dimensionality, channel count, and channel order consistent
  between training and inference.
- Use `Export HDF5` for training data preparation when you want Fiji-to-ilastik
  HDF5 compatibility.
- Some external example projects expect a sibling `inputdata/` directory with
  referenced datasets next to the `.ilp` file. Keep that directory layout when
  reusing those bundles.

## File Map

- `GROOVY_API.md`: command classes, parameters, and helper calls
- `GROOVY_WORKFLOW_EXPORT_HDF5.groovy`: TIFF to HDF5 export
- `GROOVY_WORKFLOW_IMPORT_HDF5.groovy`: HDF5 dataset import
- `GROOVY_WORKFLOW_PIXEL_CLASSIFICATION.groovy`: pixel-classification inference
- `GROOVY_WORKFLOW_AUTOCONTEXT.groovy`: autocontext inference
- `GROOVY_WORKFLOW_OBJECT_CLASSIFICATION.groovy`: object-classification inference
- `GROOVY_WORKFLOW_MULTICUT.groovy`: multicut inference
- `GROOVY_WORKFLOW_TRACKING.groovy`: tracking inference
- `UI_GUIDE.md`: menu paths and wrapper inputs
- `UI_WORKFLOW_PIXEL_CLASSIFICATION.md`: manual pixel-classification steps
- `UI_WORKFLOW_AUTOCONTEXT.md`: manual autocontext steps
- `UI_WORKFLOW_OBJECT_CLASSIFICATION.md`: manual object-classification steps
- `UI_WORKFLOW_MULTICUT.md`: manual multicut steps
- `UI_WORKFLOW_TRACKING.md`: manual tracking steps
