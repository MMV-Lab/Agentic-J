---
name: neuronj_documentation
description: NeuronJ is an ImageJ plugin for semi-GUI-based 2D neurite/neuron tracing and measurement of elongated grayscale structures. Use this skill for launching the NeuronJ tracing GUI, choosing tracing parameters, saving or exporting NeuronJ data files (NDF), and post-processing existing NDF tracings into CSV tables or ImageJ ROI files. For headless neurite/neuron tracing, SWC reconstruction analysis, morphometry, Sholl analysis, or batch automation, use the SNT skill instead.
---

# NeuronJ - Documentation Index

Install NeuronJ through the ImageScience update site when it provides `NeuronJ_.jar`, or place the official `NeuronJ_.jar` in Fiji's `plugins/` folder alongside `imagescience.jar`, then restart Fiji.

NeuronJ is primarily a semi-GUI-based 2D tracing tool. The validated automation path in this repo post-processes saved `.ndf` tracing files; it does not run NeuronJ's path-search UI in headless mode. For headless neurite/neuron tracing, SWC reconstruction analysis, morphometry, Sholl analysis, or batch automation, use `snt_documentation` instead.

## Minimal Runnable Snippet

Export vertices, tracing lengths, and ROI files from an existing NeuronJ `.ndf` file:

```bash
/opt/Fiji.app/fiji-linux-x64 --headless --run \
  /app/skills/neuronj_documentation/GROOVY_WORKFLOW_NDF_EXPORT.groovy \
  "inputNdfFile=\"/data/neuronj_validation/neurites.ndf\",outputDir=\"/data/neuronj_validation/ndf_export\",quitWhenDone=true"
```

The workflow writes `neurites_vertices.csv`, `neurites_tracing_summary.csv`, and optional `rois/N*.roi` files. Use fresh output paths; existing outputs are treated as errors unless `overwriteOutputs=true` is supplied.

## Command Quick Reference

| Mode | Status | Entry point | Main outputs |
|------|--------|-------------|--------------|
| NDF post-processing | Container-validated | `--headless --run GROOVY_WORKFLOW_NDF_EXPORT.groovy "inputNdfFile=\"...\",outputDir=\"...\""` | Vertex CSV, tracing summary CSV, optional ImageJ `.roi` files |
| Interactive tracing | Official GUI entry point | `Plugins > NeuronJ`; in an installed interactive Fiji session, `IJ.run("NeuronJ", "")` | NeuronJ toolbar attached to one image loaded through the toolbar |
| Manual export | Official GUI entry point | NeuronJ toolbar `Export tracings` | Single or per-tracing tab/comma text files, or per-tracing segmented-line ROI files |
| Manual measurement | Official GUI entry point | NeuronJ toolbar `Measure tracings` | Group, tracing, and vertex measurement result windows |

## Critical Pitfalls

1. **`imagescience.jar` is not enough.** Confirm that `NeuronJ_.jar` is present in Fiji's `plugins/` folder before expecting `Plugins > NeuronJ` to exist.
2. **NeuronJ is not a headless tracing engine.** The plugin source rejects batch mode, and this repo does not provide a validated `IJ.run()` path for automated tracing.
3. **The active ImageJ image is ignored on launch.** Load the tracing image through NeuronJ's own load button; NeuronJ handles only one attached image at a time.
4. **Input is limited to 2D 8-bit grayscale or indexed-color images.** Use SNT instead for multichannel, 3D, SWC export, or hierarchical reconstruction work.
5. **NDF geometry is not full measurement context.** NDF files store tracing vertices and settings; intensity measurements require the original image, and calibration for NeuronJ 1.1.0+ comes from `Image > Properties`.

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Suggested path leaves the neurite in dim regions | Trace shorter spans, press Shift for temporary straight-line mode, or adjust Hessian smoothing scale and cost weight factor |
| Cursor snaps to a nearby wrong structure | Reduce Snap window size, or hold Ctrl to temporarily disable snapping |
| Path recomputation is slow | Reduce Path-search window size and add more anchor clicks |
| Sharp bends are rounded off | Lower Tracing smoothing range and, if needed, lower Tracing subsampling factor |
| Structures are dark on a bright background | Set Neurite appearance to `Dark` in the Parameters dialog |

## Files

| File | What it covers |
|------|----------------|
| `OVERVIEW.md` | Plugin scope, inputs, outputs, installation, limitations, citation, and source links |
| `GROOVY_SCRIPT_API.md` | Automation boundary, NDF format notes, workflow parameters, and excluded commands |
| `GROOVY_WORKFLOW_NDF_EXPORT.groovy` | Runnable Fiji script for exporting `.ndf` tracings to CSV and ROI files |
| `UI_GUIDE.md` | Verified menu path, toolbar functions, dialogs, parameters, shortcuts, and outputs |
| `UI_WORKFLOW_2D_TRACING_AND_EXPORT.md` | End-to-end manual workflow for tracing, measuring, saving, and exporting 2D neurites |
