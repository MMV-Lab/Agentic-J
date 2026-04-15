# ilastik — Groovy API Guide

This file contains the Groovy paths used by this skill.

## HDF5 Commands

```groovy
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ExportCommand
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.io.ListDatasetsCommand

def dataset = datasetIOService.open(INPUT_TIFF)

command.run(ExportCommand, true,
    "input", dataset,
    "exportPath", new File(OUTPUT_H5),
    "datasetName", DATASET_NAME,
    "compressionLevel", 0
).get()

def listModule = command.run(ListDatasetsCommand, true,
    "file", new File(OUTPUT_H5)
).get()

def table = listModule.getOutput("datasets")

def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = new File(INPUT_H5)
importCommand.datasetName = DATASET_NAME
importCommand.axisOrder = AXIS_ORDER
importCommand.run()

def importedDataset = datasetService.create(importCommand.output)
datasetIOService.save(importedDataset, OUTPUT_TIFF)
```

## Pixel Classification Command

```groovy
#@ CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.PixelClassificationCommand

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = new File(EXECUTABLE)
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def dataset = datasetIOService.open(INPUT_TIFF)

def future = command.run(PixelClassificationCommand, true,
    "projectFileName", new File(PROJECT_FILE),
    "inputImage", dataset,
    "pixelClassificationType", OUTPUT_TYPE
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
```

## Autocontext Command

```groovy
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.AutocontextCommand

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = new File(EXECUTABLE)
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = new File(INPUT_H5)
importCommand.datasetName = DATASET_NAME
importCommand.axisOrder = AXIS_ORDER
importCommand.run()

def dataset = datasetService.create(importCommand.output)

def future = command.run(AutocontextCommand, true,
    "projectFileName", new File(PROJECT_FILE),
    "inputImage", dataset,
    "AutocontextPredictionType", OUTPUT_TYPE
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
```

## Object Classification Command

```groovy
#@ CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.ObjectClassificationCommand

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = new File(EXECUTABLE)
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def rawDataset = datasetIOService.open(INPUT_TIFF)
def secondDataset = datasetIOService.open(SECOND_INPUT_TIFF)

def future = command.run(ObjectClassificationCommand, true,
    "projectFileName", new File(PROJECT_FILE),
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", "Probabilities",
    "objectExportSource", OUTPUT_TYPE
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
```

## Multicut Command

```groovy
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.MulticutCommand

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = new File(EXECUTABLE)
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def rawImport = new ImportCommand()
rawImport.setContext(context)
rawImport.select = new File(INPUT_H5)
rawImport.datasetName = INPUT_DATASET
rawImport.axisOrder = INPUT_AXES
rawImport.run()

def probImport = new ImportCommand()
probImport.setContext(context)
probImport.select = new File(PROB_H5)
probImport.datasetName = PROB_DATASET
probImport.axisOrder = PROB_AXES
probImport.run()

def rawDataset = datasetService.create(rawImport.output)
def boundaryDataset = datasetService.create(probImport.output)

def future = command.run(MulticutCommand, true,
    "projectFileName", new File(PROJECT_FILE),
    "inputImage", rawDataset,
    "boundaryPredictionImage", boundaryDataset
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
```

## Tracking Command

```groovy
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.TrackingCommand

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = new File(EXECUTABLE)
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def rawImport = new ImportCommand()
rawImport.setContext(context)
rawImport.select = new File(RAW_H5)
rawImport.datasetName = RAW_DATASET
rawImport.axisOrder = RAW_AXES
rawImport.run()

def secondImport = new ImportCommand()
secondImport.setContext(context)
secondImport.select = new File(PROB_H5)
secondImport.datasetName = PROB_DATASET
secondImport.axisOrder = PROB_AXES
secondImport.run()

def rawDataset = datasetService.create(rawImport.output)
def secondDataset = datasetService.create(secondImport.output)

def future = command.run(TrackingCommand, true,
    "projectFileName", new File(PROJECT_FILE),
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", "Probabilities"
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
```

## Preconditions

- `ilastik4ij` must be installed in Fiji.
- The input image must be readable as a `Dataset`.
- The export path must end with `.h5`.
- Use a dataset name that ilastik expects. This skill uses `/data`.
- For `Import HDF5`, determine the dataset name and axis order before import.
- For Pixel Classification, an ilastik executable and a trained `.ilp` project
  must be available.
- For Autocontext, an ilastik executable and a trained `.ilp` project must be
  available.
- For Object Classification, a trained `.ilp` project, one raw image, and one
  matching probability image must be available.
- For Multicut, a trained `.ilp` project, one raw image, and one matching
  boundary-probability image must be available.
- For Tracking, a trained `.ilp` project, one raw time series, and one
  matching probability or segmentation input must be available.
- The image dimensionality and channel layout must match the `.ilp` project.
- Some sample `.ilp` bundles reference sibling files under `inputdata/`.
  Preserve that directory layout when reusing such bundles.

## Parameters

### `ExportCommand`

| Field | Type | Meaning |
|------|------|---------|
| `input` | `Dataset` | Image to export. |
| `exportPath` | `File` | Output `.h5` file. |
| `datasetName` | `String` | Dataset path inside the HDF5 file. Default in this skill: `/data`. |
| `compressionLevel` | `int` | Gzip compression level from `0` to `9`. |

### `ListDatasetsCommand`

| Field | Type | Meaning |
|------|------|---------|
| `file` | `File` | HDF5 file to inspect. |
| `datasets` | `GenericTable` output | Table of dataset paths, types, dimensions, and axes. |

### `ImportCommand`

| Field | Type | Meaning |
|------|------|---------|
| `select` | `File` | HDF5 file to import from. |
| `datasetName` | `String` | Dataset path inside the HDF5 file. |
| `axisOrder` | `String` | Row-major axis string used for the imported dataset. |
| `output` | `ImgPlus` output | Imported image data. |

### `IlastikOptions`

| Field | Type | Meaning |
|------|------|---------|
| `executableFile` | `File` | Path to the ilastik executable, for example `run_ilastik.sh`. |
| `numThreads` | `int` | Thread limit passed through the ilastik environment. |
| `maxRamMb` | `int` | RAM limit in MiB passed through the ilastik environment. |

### `PixelClassificationCommand`

| Field | Type | Meaning |
|------|------|---------|
| `projectFileName` | `File` | Trained ilastik Pixel Classification project (`.ilp`). |
| `inputImage` | `Dataset` | Raw input image from Fiji. |
| `pixelClassificationType` | `String` | Validated values: `Probabilities` and `Segmentation`. |
| `predictions` | `ImgPlus` output | Prediction result returned by the command. |

### `AutocontextCommand`

| Field | Type | Meaning |
|------|------|---------|
| `projectFileName` | `File` | Trained ilastik Autocontext project (`.ilp`). |
| `inputImage` | `Dataset` | Raw input image from Fiji. |
| `AutocontextPredictionType` | `String` | Validated values: `Probabilities` and `Segmentation`. |
| `predictions` | `ImgPlus` output | Autocontext result returned by the command. |

### `ObjectClassificationCommand`

| Field | Type | Meaning |
|------|------|---------|
| `projectFileName` | `File` | Trained ilastik Object Classification project (`.ilp`). |
| `inputImage` | `Dataset` | Raw input image from Fiji. |
| `inputProbOrSegImage` | `Dataset` | Probability map or segmentation image for the same scene. |
| `secondInputType` | `String` | Validated value in this skill: `Probabilities`. |
| `objectExportSource` | `String` | Validated values: `Object Predictions`, `Object Probabilities`, `Object Identities`. |
| `predictions` | `ImgPlus` output | Object-classification result returned by the command. |

### `MulticutCommand`

| Field | Type | Meaning |
|------|------|---------|
| `projectFileName` | `File` | Trained ilastik Multicut project (`.ilp`). |
| `inputImage` | `Dataset` | Raw input image from Fiji. |
| `boundaryPredictionImage` | `Dataset` | Boundary-probability image for the same scene. |
| `predictions` | `ImgPlus` output | Multicut segmentation returned by the command. |

### `TrackingCommand`

| Field | Type | Meaning |
|------|------|---------|
| `projectFileName` | `File` | Trained ilastik Tracking project (`.ilp`). |
| `inputImage` | `Dataset` | Raw time-series image from Fiji. |
| `inputProbOrSegImage` | `Dataset` | Matching probability or segmentation input. |
| `secondInputType` | `String` | Validated value in this skill: `Probabilities`. |
| `predictions` | `ImgPlus` output | Tracking result returned by the command. |

## Standard Helpers

These are standard Fiji / SCIFIO calls. They are not ilastik-specific.

| Purpose | Groovy call |
|---------|-------------|
| Open a dataset from disk | `datasetIOService.open(path)` |
| Run the export command | `command.run(ExportCommand, true, ...)` |
| Run the dataset listing command | `command.run(ListDatasetsCommand, true, ...)` |
| Import one HDF5 dataset | `new ImportCommand()`, `setContext(context)`, then `run()` |
| Load and save ilastik executable settings | `optionsService.getOptions(IlastikOptions)` and `options.save()` |
| Run Pixel Classification | `command.run(PixelClassificationCommand, true, ...)` |
| Run Autocontext | `command.run(AutocontextCommand, true, ...)` |
| Run Object Classification | `command.run(ObjectClassificationCommand, true, ...)` |
| Run Multicut | `command.run(MulticutCommand, true, ...)` |
| Run Tracking | `command.run(TrackingCommand, true, ...)` |
| Read the prediction output | `module.getOutput("predictions")` |
| Convert `ImgPlus` to `Dataset` for saving | `datasetService.create(predictions)` |
| Read the dataset table output | `listModule.getOutput("datasets")` |

## What This Guide Does Not Claim

- No claim that this repo ships an ilastik executable or a sample `.ilp`
  project file.

Use `OVERVIEW.md`, `UI_GUIDE.md`, and the `UI_WORKFLOW_*.md` files for the
documented wrapper dialogs.
