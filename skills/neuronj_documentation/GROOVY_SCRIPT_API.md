# NeuronJ - Groovy and NDF Automation Reference

NeuronJ is an ImageJ 1.x plugin whose core tracing workflow is GUI-driven. The repo-supported automation surface is saved-file processing of NeuronJ data files (`.ndf`), not automated creation of new traces.

## Installation Checks

NeuronJ requires two components:

| Component | Purpose |
|-----------|---------|
| `NeuronJ_.jar` | Registers the NeuronJ plugin entry point |
| `imagescience.jar` | Provides the ImageScience library used by NeuronJ and related plugins |

The official plugin configuration entry is:

```text
Plugins, "NeuronJ", NeuronJ_
Help>About Plugins, "NeuronJ...", NeuronJ_Website
```

Confirm installation in a Fiji runtime with:

```bash
find /opt/Fiji.app/plugins /opt/Fiji.app/jars \( -iname '*NeuronJ*' -o -iname '*imagescience*' \)
```

`imagescience.jar` alone does not register the NeuronJ menu item.

## Interactive Launch Boundary

Use NeuronJ from an interactive Fiji session:

```groovy
import ij.IJ
IJ.run("NeuronJ", "")
```

Preconditions:

| Requirement | Details |
|-------------|---------|
| Display | Required. NeuronJ installs a temporary toolbar and handles mouse/key events. |
| Installed jar | `NeuronJ_.jar` must be in the ImageJ/Fiji plugin discovery path. |
| Image loading | Load the image through the NeuronJ toolbar, not by relying on the currently active ImageJ image. |
| Input image | 2D 8-bit grayscale or indexed-color image. |

This skill does not claim a headless `IJ.run("NeuronJ", "")` tracing path. The plugin source checks for batch mode and reports that NeuronJ does not work there.

## Container-Validated NDF Workflow

Run the checked-in workflow from Fiji:

```bash
/opt/Fiji.app/fiji-linux-x64 --headless --run \
  /app/skills/neuronj_documentation/GROOVY_WORKFLOW_NDF_EXPORT.groovy \
  "inputNdfFile=\"/data/neuronj_validation/neurites.ndf\",outputDir=\"/data/neuronj_validation/ndf_export\",quitWhenDone=true"
```

The workflow parses an existing `.ndf` file and writes:

| Output | Contents |
|--------|----------|
| `neurites_vertices.csv` | One row per saved NDF vertex with tracing ID, type, cluster, segment, pixel coordinates, calibrated coordinates, and cumulative length |
| `neurites_tracing_summary.csv` | One row per tracing with segment count, vertex count, pixel length, calibrated length, type, cluster, and label |
| `rois/N*.roi` | Optional ImageJ segmented-line ROI per tracing, using NeuronJ's export convention of skipping duplicate segment-join points |

Existing output files are rejected by default. Set `overwriteOutputs=true` only when replacing prior exports is intentional.
Single-vertex or otherwise zero-length tracings are retained in the CSV exports. ROI export is skipped for tracings with fewer than two vertices because ImageJ polyline ROIs require at least two points.

When launching through `--run`, quote file and string values inside the argument string with double quotes as shown above.

## Workflow Parameters

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `inputNdfFile` | `File` | `/data/neuronj_validation/neurites.ndf` | Saved NeuronJ data file |
| `outputDir` | `File` directory | `/data/neuronj_validation/ndf_export` | Destination for tables and optional ROI files |
| `vertexCsvName` | `String` | `neurites_vertices.csv` | Vertex-level CSV filename |
| `summaryCsvName` | `String` | `neurites_tracing_summary.csv` | Tracing-level CSV filename |
| `pixelWidth` | `Double` | `1.0` | Width of one pixel in the desired measurement unit |
| `pixelHeight` | `Double` | `1.0` | Height of one pixel in the desired measurement unit |
| `lengthUnit` | `String` | `pixel` | Unit label written to CSV outputs |
| `useLegacyCalibration` | `Boolean` | `true` | For NDF versions before 1.1.0, use pixel size and unit stored in the NDF |
| `exportRois` | `Boolean` | `true` | Write one `.roi` file per tracing |
| `overwriteOutputs` | `Boolean` | `false` | Replace existing CSV and ROI outputs instead of failing |
| `quitWhenDone` | `Boolean` | `false` | Exit Fiji after the workflow completes |

For NeuronJ 1.1.0 and later, image calibration is not stored in the NDF file. Pass `pixelWidth`, `pixelHeight`, and `lengthUnit` explicitly when calibrated length matters.

## NDF Structure

The parser supports the NeuronJ data structure written by the plugin source:

1. Header and NDF version.
2. Algorithm parameters: appearance for version 1.4.0+, Hessian smoothing scale, cost weight factor, snap window size, path-search window size, tracing smoothing range, tracing subsampling factor, and line width for version 1.1.0+.
3. Eleven tracing type names and color indices.
4. Eleven cluster names.
5. Repeated tracing blocks with tracing ID, type index, cluster index, label, and one or more segment blocks.
6. Segment blocks containing alternating integer `x` and `y` pixel coordinates.

Tracing length is computed as the sum of Euclidean distances between successive vertices. Calibrated length uses `pixelWidth` and `pixelHeight`; pixel length uses unit pixel spacing.

## Excluded and Unverified Surfaces

| Surface | Status |
|---------|--------|
| Automated NeuronJ tracing from two endpoints | Excluded; no validated public API or macro command is documented for the path-search interaction |
| Headless `IJ.run("NeuronJ", "")` | Excluded; NeuronJ is GUI-only and rejects batch mode |
| Programmatic measurement of intensities from NDF alone | Excluded; NDF does not contain the source image pixels |
| SWC export from NeuronJ | Unsupported by NeuronJ; use SNT for SWC workflows |
| SNT NDF import/conversion | Officially described by ImageJ docs, but not used as this skill's checked-in automation path |
