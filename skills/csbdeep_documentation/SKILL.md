---
name: csbdeep_documentation
description: CSBDeep is the Fiji/ImageJ plugin family for running CARE-style TensorFlow SavedModels from the `Plugins > CSBDeep` menu. Use this skill for the base CSBDeep commands `Run your network`, `Run your IsoNet`, and the built-in demo wrappers. This skill documents the SciJava `command.run(...)` surface, the Fiji menu paths, and the current model-loading limitation observed in this repo's container. Related plugins `StarDist`, `N2V`, and `DenoiSeg` are separate workflows and are not covered here beyond scope notes.
---

Install from the Fiji update site `CSBDeep`, then restart Fiji. If model execution fails, inspect `Edit > Options > TensorFlow...` before assuming the command syntax is wrong.

Use CSBDeep when you have a compatible exported model ZIP or you want to run one of the built-in CARE demo models from the `Plugins > CSBDeep` menu. The base automation surface is SciJava `command.run(...)`, not `IJ.run(...)`.

## Minimal runnable snippet

```groovy
#@ CommandService command
#@ DatasetIOService datasetIO

import de.csbdresden.csbdeep.commands.GenericNetwork

def input = datasetIO.open("/data/example_1.tif")

def module = command.run(GenericNetwork, false,
    "input",             input,
    "modelFile",         new File("/path/to/model.zip"),
    "nTiles",            8,
    "blockMultiple",     32,
    "overlap",           32,
    "batchSize",         1,
    "normalizeInput",    true,
    "percentileBottom",  3.0f,
    "percentileTop",     99.8f,
    "clip",              false,
    "showProgressDialog", false
).get()

def output = module.getOutput("output")
```

## Command Quick Reference

| Mode | SciJava class | Menu path | Key inputs | Output |
|------|---------------|-----------|------------|--------|
| Generic restoration | `GenericNetwork` | `Plugins > CSBDeep > Run your network` | `input`, exactly one of `modelFile` / `modelUrl`, tiling + normalization parameters | `output` `Dataset` |
| Isotropic Z restoration | `GenericIsotropicNetwork` | `Plugins > CSBDeep > Run your IsoNet` | same as `GenericNetwork` plus `scale` | `output` `Dataset` |
| Demo: Tribolium | `NetTribolium` | `Plugins > CSBDeep > Demo > 3D Denoising - Tribolium` | `input`, `nTiles`, `showProgressDialog` | `output` `Dataset` |
| Demo: Planaria | `NetPlanaria` | `Plugins > CSBDeep > Demo > 3D Denoising - Planaria` | `input`, `nTiles`, `showProgressDialog` | `output` `Dataset` |
| Demo: Microtubules | `NetTubulin` | `Plugins > CSBDeep > Demo > Deconvolution - Microtubules` | `input`, `nTiles`, `batchSize`, `showProgressDialog` | `output` `Dataset` |
| Demo: Flywing projection | `NetProject` | `Plugins > CSBDeep > Demo > Surface Projection - Flywing` | `input`, `nTiles`, `showProgressDialog` | `output` `Dataset` |
| Demo: Retina IsoNet | `NetIso` | `Plugins > CSBDeep > Demo > Isotropic Reconstruction - Retina` | `input`, `nTiles`, `scale`, `batchSize`, `showProgressDialog` | `output` `Dataset` |

## Validation Boundary

Container-validated in this repo:

- `command.run(NetTribolium, false, ...)` accepts a `Dataset`, resolves the demo model URL, and returns a non-null `output` dataset that saves successfully as a TIFF.
- `command.run(GenericNetwork, false, ...)` runs end-to-end with `modelUrl = http://csbdeep.bioimagecomputing.com/model-tribolium.zip` and returns a non-null `output` dataset that saves successfully as a TIFF.
- `fiji-linux-x64 --headless --run ...` also works for scripted CSBDeep execution in this container when file and string arguments are quoted inside the parameter list.

Official-doc and source-grounded:

- Installation from the `CSBDeep` update site.
- Menu paths under `Plugins > CSBDeep`.
- Demo wrapper commands and their fixed model URLs.
- `GenericNetwork` / `GenericIsotropicNetwork` parameter names and defaults.

Explicitly excluded or out of scope:

- `StarDist`, `N2V`, and `DenoiSeg` workflows.
- Any `IJ.run("CSBDeep ...")` macro string for the base CARE commands.
- Broad launcher-warning cleanup unrelated to CSBDeep output generation.

## 5 Critical Pitfalls

1. `Run your network` is a SciJava command class. Do not invent an `IJ.run(...)` option string for it.
2. `GenericNetwork` needs exactly one model source: `modelFile` or `modelUrl`. Supplying neither or both leaves the command without a valid model.
3. The command expects a `Dataset` input. In scripts, open files with `DatasetIOService` or `ij.scifio().datasetIO()`, not with `IJ.openImage()` unless you convert to `Dataset`.
4. In `fiji-linux-x64 --headless --run ...`, quote file and string arguments inside the parameter list, for example `inputFile='/data/example_1.tif'`. Unquoted paths are parsed as expressions and fail before CSBDeep runs.
5. `NetProject` is stricter than the other demo wrappers: it validates for a 3D grayscale X-Y-Z image before running. Use `Run your IsoNet` or the generic command for other model families instead of forcing the projection demo onto the wrong input shape.

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Out-of-memory or very slow inference | Increase `nTiles`; for models that expose it, lower `batchSize` |
| Visible seams between tiles | Increase `overlap` |
| Output looks flattened or over-clipped | Widen the percentile range or disable `clip` |
| Input is already intensity-normalized | Set `normalizeInput = false` |
| Z axis is much coarser than X/Y | Use `GenericIsotropicNetwork` or `NetIso` and set `scale` to the Z anisotropy factor |

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin scope, use cases, installation, limitations, and links |
| `SCRIPT_API.md` | Verified command classes, parameters, outputs, and demo wrapper mappings |
| `GROOVY_WORKFLOW_RUN_YOUR_NETWORK.groovy` | Parameterized Groovy workflow for a local model ZIP or model URL |
| `GROOVY_WORKFLOW_TRIBOLIUM_DEMO.groovy` | Minimal Groovy workflow for the built-in Tribolium demo wrapper |
| `UI_GUIDE.md` | Verified menu paths and dialog-level guidance for the base CSBDeep plugin |
| `UI_WORKFLOW_RUN_YOUR_NETWORK.md` | End-to-end manual workflow for applying an exported model ZIP in Fiji |
| `SKILL.md` | This quick-reference card |
