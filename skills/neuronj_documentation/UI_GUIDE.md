# NeuronJ - UI Guide

## Launch and Installation

| Item | Value |
|------|-------|
| Menu path | `Plugins > NeuronJ` |
| About path | `Help > About Plugins > NeuronJ...` |
| Required jars | `NeuronJ_.jar` and `imagescience.jar` |
| Primary UI | NeuronJ toolbar, which temporarily replaces the ImageJ toolbar |

Only one NeuronJ instance can run at a time. Quit NeuronJ to restore the normal ImageJ toolbar.

## Input Handling

Use the NeuronJ toolbar's load button to open either:

- an image file: `.tif`, `.tiff`, `.gif`, or `.jpg`
- an existing NeuronJ data file: `.ndf`

NeuronJ accepts only 2D 8-bit grayscale or indexed-color images. If an image has a matching same-folder, same-base-name `.ndf` file, NeuronJ loads the saved tracings and settings automatically.

When the current image window is active, the left and right arrow keys move to the previous or next compatible image in the same folder.

## Toolbar Functions

| Function | Purpose |
|----------|---------|
| Erase tracings | Remove all tracings while retaining parameters, type names, cluster names, and type colors |
| Load image/tracings | Attach NeuronJ to an image or load a saved `.ndf` tracing file |
| Save tracings | Save current tracings and settings as `.ndf` |
| Export tracings | Export vertex coordinates as text, or export each tracing as an ImageJ segmented-line ROI |
| Add tracings | Semi-automatic tracing mode with click-to-fix path segments |
| Delete tracings | Remove one highlighted tracing |
| Move vertices | Drag individual tracing control points |
| Measure tracings | Open group, tracing, and vertex measurement options |
| Label tracings | Assign tracing type, cluster, and label; rename types/clusters and recolor types |
| Set parameters | Adjust appearance, Hessian/path-search settings, smoothing, subsampling, line width, and save behavior |
| Make snapshot | Create an RGB image containing the image and/or drawn tracings |

## Tracing Controls

| Control | Effect |
|---------|--------|
| Left click | Start a tracing or fix the currently suggested path |
| Double click, Tab, or Space | Finish the current tracing |
| Shift | Temporarily switch to manual straight-line tracing |
| Ctrl | Temporarily disable local cursor snapping |
| `+` / `-` | Zoom in or out when the image window is active |

## Parameters Dialog

| Parameter | Meaning |
|-----------|---------|
| Neurite appearance | Bright-on-dark or dark-on-bright structures |
| Hessian smoothing scale | Scale for second-order structure estimation |
| Cost weight factor | Weighting between eigenvalue and eigenvector path costs |
| Snap window size | Local cursor snapping search size; `1 x 1` effectively disables snapping |
| Path-search window size | Maximum region searched for the optimal path after each click |
| Tracing smoothing range | Uniform smoothing half-range applied to raw path positions |
| Tracing subsampling factor | Frequency for keeping points along smoothed paths |
| Line width | Pixel width used for drawing tracings |
| Activate image window when mouse enters | Helps key bindings work without manual focus changes |
| Use image name in result window titles | Names snapshots and measurement windows from the image basename |
| Automatically save tracings | Saves `.ndf` when closing or changing the attached image |
| Show log messages | Opens a separate NeuronJ log window |

## Measurement Dialog

| Option | Meaning |
|--------|---------|
| Tracing type | Measure all types or one named type |
| Cluster | Measure all clusters or one named cluster |
| Display group measurements | Count and summarize selected tracings |
| Display tracing measurements | Report length and intensity statistics for each tracing |
| Display vertex measurements | Report vertex coordinates and image value at each vertex |
| Calibrate measurements | Use `Image > Properties` pixel size and calibration table |
| Interpolate value measurements | Sample additional image values between vertices |
| Clear previous measurements | Replace previous result-window contents |
| Maximum decimal places | Rounding precision for reported values |

## Export Formats

| Export option | Output |
|---------------|--------|
| Tab-delimited text, single file | All tracings in one `.txt` file |
| Tab-delimited text, separate files | One `.txt` file per tracing plus an overview file |
| Comma-delimited text, single file | All tracings in one `.txt` file |
| Comma-delimited text, separate files | One `.txt` file per tracing plus an overview file |
| Segmented line selection files | One `.roi` file per tracing plus an overview file |

ImageJ segmented-line ROI vertices are displayed relative to ImageJ's coordinate convention. NeuronJ draws paths visually through pixel centers, so zoomed ROI overlays can appear shifted by the expected half-pixel convention.
