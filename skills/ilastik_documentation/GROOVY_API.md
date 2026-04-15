# ilastik — Groovy API Guide

This file contains the Groovy paths used by this skill.

## Script Parameter Pattern

Use SciJava parameters for file and choice inputs. The executable path is a
string parameter so the workflow can fall back to `ILASTIK_EXECUTABLE` in
headless execution.

```groovy
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Project file", value = "/path/to/project.ilp") projectFile
#@ File (label = "Input TIFF", value = "/path/to/input.tif") inputFile
#@ String (label = "Output type", choices = {"Probabilities", "Segmentation"}, value = "Probabilities") outputType
#@ File (label = "Output TIFF", value = "/path/to/output.tif") outputFile
#@ Integer (label = "Threads (-1 for all)", value = -1) numThreads
#@ Integer (label = "Max RAM (MiB)", value = 4096) maxRamMb
```

Use the same pattern for HDF5 inputs, dataset names, axis strings, and
second-input modes.

Resolve the executable path like this:

```groovy
String resolvedExecutablePath = executablePath?.trim()
if (!resolvedExecutablePath) {
    resolvedExecutablePath = System.getenv("ILASTIK_EXECUTABLE") ?: ""
}
if (!resolvedExecutablePath) {
    throw new IllegalArgumentException(
        "Set executablePath or ILASTIK_EXECUTABLE before running this workflow")
}

def executableFile = new File(resolvedExecutablePath)
```

## Temporary ilastik Settings Override

Prediction wrappers read the executable, thread count, and RAM limit from
`IlastikOptions`. Save the requested values before the command and restore the
previous Fiji preferences in a `finally` block:

```groovy
def options = optionsService.getOptions(IlastikOptions)
def previousExecutableFile = options.executableFile
int previousNumThreads = options.numThreads
int previousMaxRamMb = options.maxRamMb

try {
    options.executableFile = executableFile
    options.numThreads = numThreads
    options.maxRamMb = maxRamMb
    options.save()

    // run ilastik command here
}
finally {
    options.executableFile = previousExecutableFile
    options.numThreads = previousNumThreads
    options.maxRamMb = previousMaxRamMb
    options.save()
}
```

## HDF5 Commands

### Export HDF5

```groovy
def dataset = datasetIOService.open(inputFile.absolutePath)

command.run(ExportCommand, true,
    "input", dataset,
    "exportPath", outputFile,
    "datasetName", datasetName,
    "compressionLevel", compressionLevel
).get()
```

### List HDF5 Datasets

```groovy
def listModule = command.run(ListDatasetsCommand, true,
    "file", outputFile
).get()
def table = listModule.getOutput("datasets")
```

### Import HDF5

```groovy
def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = inputFile
importCommand.datasetName = datasetName
importCommand.axisOrder = axisOrder
importCommand.run()

def importedDataset = datasetService.create(importCommand.output)
datasetIOService.save(importedDataset, outputFile.absolutePath)
```

## Pixel Classification Command

```groovy
def dataset = datasetIOService.open(inputFile.absolutePath)

def future = command.run(PixelClassificationCommand, true,
    "projectFileName", projectFile,
    "inputImage", dataset,
    "pixelClassificationType", outputType
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, outputFile.absolutePath)
```

## Autocontext Command

```groovy
def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = inputFile
importCommand.datasetName = datasetName
importCommand.axisOrder = axisOrder
importCommand.run()

def dataset = datasetService.create(importCommand.output)

def future = command.run(AutocontextCommand, true,
    "projectFileName", projectFile,
    "inputImage", dataset,
    "AutocontextPredictionType", outputType
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, outputFile.absolutePath)
```

## Object Classification Command

```groovy
def rawDataset = datasetIOService.open(inputFile.absolutePath)
def secondDataset = datasetIOService.open(secondInputFile.absolutePath)

def future = command.run(ObjectClassificationCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", secondInputType,
    "objectExportSource", outputType
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, outputFile.absolutePath)
```

## Multicut Command

```groovy
def rawImport = new ImportCommand()
rawImport.setContext(context)
rawImport.select = rawFile
rawImport.datasetName = rawDatasetName
rawImport.axisOrder = rawAxisOrder
rawImport.run()

def boundaryImport = new ImportCommand()
boundaryImport.setContext(context)
boundaryImport.select = boundaryFile
boundaryImport.datasetName = boundaryDatasetName
boundaryImport.axisOrder = boundaryAxisOrder
boundaryImport.run()

def rawDataset = datasetService.create(rawImport.output)
def boundaryDataset = datasetService.create(boundaryImport.output)

def future = command.run(MulticutCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "boundaryPredictionImage", boundaryDataset
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, outputFile.absolutePath)
```

## Tracking Command

```groovy
def rawImport = new ImportCommand()
rawImport.setContext(context)
rawImport.select = rawFile
rawImport.datasetName = rawDatasetName
rawImport.axisOrder = rawAxisOrder
rawImport.run()

def secondImport = new ImportCommand()
secondImport.setContext(context)
secondImport.select = secondInputFile
secondImport.datasetName = secondInputDatasetName
secondImport.axisOrder = secondInputAxisOrder
secondImport.run()

def rawDataset = datasetService.create(rawImport.output)
def secondDataset = datasetService.create(secondImport.output)

def future = command.run(TrackingCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", secondInputType
)

def module = future.get()
def predictions = module.getOutput("predictions")
def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, outputFile.absolutePath)
```

## Preconditions

- `ilastik4ij` must be installed in Fiji.
- Prediction wrappers require a trained `.ilp` project and either
  `executablePath` or `ILASTIK_EXECUTABLE`.
- `Export HDF5` requires a readable input image and an `.h5` output path.
- `Import HDF5` requires the correct dataset name and axis order.
- Pixel Classification requires one raw image.
- Autocontext requires one raw HDF5 dataset.
- Object Classification requires one raw image and one matching probability or
  segmentation image.
- Multicut requires one raw HDF5 dataset and one matching
  boundary-probability HDF5 dataset.
- Tracking requires one raw HDF5 dataset and one matching probability or
  segmentation HDF5 dataset.
- The image dimensionality and channel layout must match the `.ilp` project.
- Some sample `.ilp` bundles reference sibling files under `inputdata/`.
  Preserve that directory layout when reusing such bundles.
- The committed Object Classification workflow defaults to the probabilities
  output written by the committed Pixel Classification workflow.

## Parameters

### `ExportCommand`

| Field | Type | Meaning |
|------|------|---------|
| `input` | `Dataset` | Image to export. |
| `exportPath` | `File` | Output `.h5` file. |
| `datasetName` | `String` | Dataset path inside the HDF5 file. |
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
| `executableFile` | `File` | Path to the ilastik executable, for example `run_ilastik.sh`. The committed workflows derive it from `executablePath` or `ILASTIK_EXECUTABLE`. |
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
| `secondInputType` | `String` | Supported values from plugin source: `Probabilities` and `Segmentation`. The committed workflow defaults to `Probabilities`. |
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
| `secondInputType` | `String` | Supported values from plugin source: `Probabilities` and `Segmentation`. The committed workflow defaults to `Probabilities`. |
| `predictions` | `ImgPlus` output | Tracking result returned by the command. |

## Standard Helpers

These are standard Fiji / SCIFIO calls. They are not ilastik-specific.

| Purpose | Groovy call |
|---------|-------------|
| Open a dataset from disk | `datasetIOService.open(path)` |
| Run the export command | `command.run(ExportCommand, true, ...)` |
| Run the dataset listing command | `command.run(ListDatasetsCommand, true, ...)` |
| Import one HDF5 dataset | `new ImportCommand()`, `setContext(context)`, then `run()` |
| Resolve executable from parameter or environment | `executablePath?.trim()` or `System.getenv("ILASTIK_EXECUTABLE")` |
| Temporarily override ilastik executable settings | `optionsService.getOptions(IlastikOptions)`, then `options.save()` in `try` / `finally` |
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
- No claim that all supported command choices are validated in every workflow
  combination. Use the committed defaults when you need the exact validated
  path.

Use `OVERVIEW.md`, `UI_GUIDE.md`, and the `UI_WORKFLOW_*.md` files for the
documented wrapper dialogs.
