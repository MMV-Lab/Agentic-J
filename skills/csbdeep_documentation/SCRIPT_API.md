# CSBDeep Script API

This file documents the SciJava command surface used by the base CSBDeep Fiji plugin.

## Automation Surface

Use `CommandService` with the command classes from `de.csbdresden.csbdeep.commands`.

Do not invent an `IJ.run(...)` string for the base CARE commands in this skill.

When launching a `#@` script via `fiji-linux-x64 --headless --run ...`, quote file and string values inside the parameter list, for example `inputFile='/data/example_1.tif'`.

## Container-Validated Boundary

In this repo's current Fiji container:

- `NetTribolium` resolves its fixed demo model URL, runs inference, returns a non-null `output` dataset, and saves successfully as a TIFF.
- `GenericNetwork` runs end-to-end with `modelUrl = http://csbdeep.bioimagecomputing.com/model-tribolium.zip`, returns a non-null `output` dataset, and saves successfully as a TIFF.
- `fiji-linux-x64 --headless --run ...` works for CSBDeep scripts in this container when file and string arguments are quoted inside the parameter list.

The parameter names below are source-grounded and were accepted by the current runtime during successful container validation.

## Generic Restoration Command

### Class

```groovy
import de.csbdresden.csbdeep.commands.GenericNetwork
```

### Minimal Groovy Pattern

```groovy
#@ CommandService command
#@ DatasetIOService datasetIO

import de.csbdresden.csbdeep.commands.GenericNetwork

def input = datasetIO.open("/data/example_1.tif")

def module = command.run(GenericNetwork, false,
    "input",              input,
    "modelFile",          new File("/path/to/model.zip"),
    "nTiles",             8,
    "blockMultiple",      32,
    "overlap",            32,
    "batchSize",          1,
    "normalizeInput",     true,
    "percentileBottom",   3.0f,
    "percentileTop",      99.8f,
    "clip",               false,
    "showProgressDialog", false
).get()

def output = module.getOutput("output")
```

### Parameters

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `input` | `Dataset` | required | Open with `DatasetIOService` or `ij.scifio().datasetIO()` |
| `normalizeInput` | `boolean` | `true` | Enable percentile normalization before inference |
| `percentileBottom` | `float` | `3.0` | Lower normalization percentile |
| `percentileTop` | `float` | `99.8` | Upper normalization percentile |
| `clip` | `boolean` | `false` | Clip normalized values into the output range |
| `nTiles` | `int` | `8` | Number of tiles used by `DefaultTiling` |
| `blockMultiple` | `int` | `32` | Tile dimensions must be multiples of this value |
| `overlap` | `int` | `32` | Tile overlap |
| `batchSize` | `int` | `1` | Batch size for model execution |
| `modelFile` | `File` | unset | Local exported model ZIP |
| `modelUrl` | `String` | unset | Remote model ZIP URL |
| `showProgressDialog` | `boolean` | `true` | Disable in batch or headless automation |
| `output` | `Dataset` | output | Returned as module output |

### Model Source Rules

- Supply exactly one of `modelFile` or `modelUrl`.
- `modelFile` must point to an exported CSBDeep / CARE model ZIP.
- `modelUrl` must resolve to a compatible ZIP; the plugin caches model contents under `/opt/Fiji.app/models`.

## Isotropic Reconstruction Command

### Class

```groovy
import de.csbdresden.csbdeep.commands.GenericIsotropicNetwork
```

### Additional Parameter

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `scale` | `float` | `10.2` | Z-axis scale factor used for IsoNet pre-upsampling |

`GenericIsotropicNetwork` inherits the `GenericNetwork` parameters and uses a specialized input/output processor that rotates the volume around Z, runs two predictions, and merges them back into one isotropic output dataset.

## Demo Wrapper Commands

These commands wrap `GenericNetwork` or `GenericIsotropicNetwork` with a fixed model URL and a reduced parameter surface.

| Class | Menu path | Fixed model URL | Wrapper parameters |
|-------|-----------|-----------------|-------------------|
| `NetTribolium` | `Plugins > CSBDeep > Demo > 3D Denoising - Tribolium` | `http://csbdeep.bioimagecomputing.com/model-tribolium.zip` | `input`, `nTiles`, `showProgressDialog` |
| `NetPlanaria` | `Plugins > CSBDeep > Demo > 3D Denoising - Planaria` | `http://csbdeep.bioimagecomputing.com/model-planaria.zip` | `input`, `nTiles`, `showProgressDialog` |
| `NetTubulin` | `Plugins > CSBDeep > Demo > Deconvolution - Microtubules` | `http://csbdeep.bioimagecomputing.com/model-tubulin.zip` | `input`, `nTiles`, `batchSize`, `showProgressDialog` |
| `NetProject` | `Plugins > CSBDeep > Demo > Surface Projection - Flywing` | `http://csbdeep.bioimagecomputing.com/model-project.zip` | `input`, `nTiles`, `showProgressDialog` |
| `NetIso` | `Plugins > CSBDeep > Demo > Isotropic Reconstruction - Retina` | `http://csbdeep.bioimagecomputing.com/model-iso.zip` | `input`, `nTiles`, `scale`, `batchSize`, `showProgressDialog` |

### Wrapper Defaults Applied Internally

| Class | Internal call |
|-------|---------------|
| `NetTribolium` / `NetPlanaria` | `GenericNetwork` with `blockMultiple = 8` |
| `NetTubulin` | `GenericNetwork` with `blockMultiple = 8` and user-set `batchSize` |
| `NetProject` | `GenericNetwork` with `blockMultiple = 16` |
| `NetIso` | `GenericIsotropicNetwork` with `blockMultiple = 8` |

## Source-Grounded Input Constraints

- `NetProject` explicitly validates for a 3D grayscale `X-Y-Z` image before it calls `GenericNetwork`.
- `NetTribolium`, `NetPlanaria`, and `NetTubulin` are exercised in upstream tests with XY and XYZ inputs.
- `GenericNetwork` itself is model-driven: the accepted tensor layout depends on the exported model ZIP and the plugin's TF input mapping.

## Output Handling

- `GenericNetwork` returns `output` as a `Dataset`.
- `GenericIsotropicNetwork` also returns a single merged `Dataset`.
- Save the result with `DatasetIOService.save(output, "/path/to/out.tif")`.

## Standard Helper Calls

These calls are standard ImageJ / SciJava helpers, not CSBDeep-specific commands.

| Purpose | Call |
|---------|------|
| Open a dataset from disk | `datasetIO.open(path)` or `ij.scifio().datasetIO().open(path)` |
| Run the command | `command.run(GenericNetwork, false, ...)` |
| Wait for completion | `.get()` on the returned future |
| Read the output | `module.getOutput("output")` |
| Save result | `datasetIO.save(output, path)` |

## Explicitly Excluded

- No `IJ.run("Run your network", "...")` macro syntax is claimed here.
- No N2V or DenoiSeg command surface is documented here.
- No blanket claim is made that every third-party CSBDeep-family workflow in this repo will behave identically to the validated `NetTribolium` and `GenericNetwork` cases above.
