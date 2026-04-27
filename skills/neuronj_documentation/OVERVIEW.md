# NeuronJ - Overview

NeuronJ is an ImageJ plugin by Erik Meijering for semi-automatic tracing and analysis of elongated 2D image structures, especially neuronal processes. It combines a dedicated toolbar, local cursor snapping, Hessian-based path costs, interactive path fixing, labeling, measurement, and export of saved tracings.

## Typical Use Cases

| Use case | Fit |
|----------|-----|
| Trace neurites in 2D grayscale fluorescence images | Good fit |
| Measure neurite lengths and image values along tracings | Good fit when the source image and calibration are available |
| Save reusable 2D tracing data | Good fit through `.ndf` files |
| Export polyline ROIs for later ImageJ use | Good fit through the NeuronJ export dialog or the NDF workflow |
| Reconstruct multichannel or 3D neurons | Use SNT instead |
| Export SWC reconstructions or hierarchical trees | Use SNT instead |

## Input Requirements

| Input | Requirement |
|-------|-------------|
| Image dimensionality | 2D only |
| Image type | 8-bit grayscale or indexed color |
| Loading route | Load through the NeuronJ toolbar after launching NeuronJ |
| Active ImageJ image | Not used automatically by NeuronJ |
| Calibration | Set in `Image > Properties` before measuring if calibrated lengths are needed |
| Existing tracing data | `.ndf` files saved by NeuronJ |

## Output Types

| Output | Produced by | Notes |
|--------|-------------|-------|
| `.ndf` data file | NeuronJ save command | Stores tracing vertices, algorithm parameters, type names, cluster names, labels, and type colors |
| Text coordinates | NeuronJ export command | Single combined file or one file per tracing; tab- or comma-delimited |
| `.roi` files | NeuronJ export command or checked-in NDF workflow | One segmented-line ROI per tracing |
| Measurement result windows | NeuronJ measure command | Group, tracing, and vertex measurements |
| Snapshot RGB image | NeuronJ snapshot command | Burns image and/or tracings into a display copy |
| CSV tables | `GROOVY_WORKFLOW_NDF_EXPORT.groovy` | Headless export from existing `.ndf` files |

## Automation Level

NeuronJ tracing itself is GUI-only. The plugin source requires a live ImageJ instance and refuses batch mode, so this skill does not provide a scripted path for making new traces.

The supported automation path is file-based:

- Run NeuronJ interactively to create or edit tracings.
- Save a `.ndf` file.
- Use `GROOVY_WORKFLOW_NDF_EXPORT.groovy` to export vertices, lengths, and ROI files in a reproducible headless step.

## Installation

For Fiji, enable the ImageScience update site when it provides NeuronJ. If a runtime contains `imagescience.jar` but does not expose `Plugins > NeuronJ`, install the official `NeuronJ_.jar` manually into the Fiji `plugins/` folder and restart Fiji.

For ImageJ 1.x, the official NeuronJ page provides `NeuronJ_.jar` and `imagescience.jar`; both belong in the `plugins/` folder.

## Known Limitations

- NeuronJ handles only one attached image at a time.
- It does not work with an image that was merely open before launch; use the NeuronJ load button.
- It is limited to 2D 8-bit grayscale or indexed-color images.
- It does not export SWC and does not model parent-child hierarchy between paths.
- Tracing quality depends on contrast and on local path choices; low-contrast regions may need manual straight-line tracing.
- The NDF workflow can compute geometry from saved vertices, but it cannot reproduce image-intensity measurements without the original image.
- Some Fiji runtimes may include the ImageScience library without the NeuronJ plugin jar; verify both components.

## Citation and Links

Primary plugin and documentation:

- ImageJ plugin page: <https://imagej.net/plugins/neuronj>
- NeuronJ website and downloads: <https://imagescience.org/meijering/software/neuronj/>
- NeuronJ manual: <https://imagescience.org/meijering/software/neuronj/manual/>
- Release notes: <https://imagescience.org/meijering/software/neuronj/releases/>
- Source code: <https://github.com/imagescience/NeuronJ>

Citation requested by the NeuronJ website:

- E. Meijering, M. Jacob, J.-C. F. Sarria, P. Steiner, H. Hirling, M. Unser. "Design and Validation of a Tool for Neurite Tracing and Analysis in Fluorescence Microscopy Images." Cytometry Part A 58(2), April 2004, 167-176.
