---
name: ilastik_documentation
description: ilastik4ij integrates ilastik with Fiji. It exports/imports HDF5 and runs trained ilastik workflows from Fiji when an ilastik executable and compatible `.ilp` project are configured. This skill covers committed Groovy workflows for HDF5 export/import, dataset listing, Pixel Classification, Autocontext, Object Classification, Multicut, and Tracking, plus the documented UI commands under `Plugins > ilastik`. Read the files listed at the end of this SKILL for commands, GUI walkthroughs, sample workflows, and scope limits.
---

The plugin appears under `Plugins > ilastik` after enabling the `ilastik` update
site and restarting Fiji.
Use it when you need ilastik-compatible HDF5 transfer, HDF5 dataset
inspection, or a Fiji-side workflow for a pre-trained ilastik Pixel
Classification, Autocontext, Object Classification, Multicut, or Tracking
project.

## Automation Boundary

- The Groovy files in this skill cover `Export HDF5`, `Import HDF5`,
  `List HDF5 Datasets`, `Run Pixel Classification Prediction`,
  `Run Autocontext Prediction`, `Run Object Classification Prediction`,
  `Run Multicut`, and `Run Tracking`.
- Prediction wrappers require a configured ilastik executable, a compatible
  pre-trained `.ilp` project, and input images whose dimensions and channels
  match that project.
- Some external sample projects expect a sibling `inputdata/` directory next to
  the `.ilp` file. Keep those referenced files in place when reusing such
  bundles.
- Do not invent additional command names or parameter keys. Use the plugin
  docs or source before extending this skill.

## File Index

| File | When to read it |
|------|-----------------|
| `OVERVIEW.md` | Read for the plugin's capability map, committed workflow coverage, and compatibility boundary. |
| `GROOVY_API.md` | Read for the Groovy command path used by this skill, its parameters, and helper calls. |
| `GROOVY_WORKFLOW_EXPORT_HDF5.groovy` | Read or run when you need a minimal TIFF-to-HDF5 export workflow for ilastik. |
| `GROOVY_WORKFLOW_IMPORT_HDF5.groovy` | Read or run when you need to import one HDF5 dataset into Fiji with an explicit dataset name and axis order. |
| `GROOVY_WORKFLOW_PIXEL_CLASSIFICATION.groovy` | Read or run when you need a headless Fiji workflow that configures ilastik and applies a trained Pixel Classification project. |
| `GROOVY_WORKFLOW_AUTOCONTEXT.groovy` | Read or run when you need a headless Fiji workflow that applies a trained Autocontext project and saves the returned probabilities or segmentation. |
| `GROOVY_WORKFLOW_OBJECT_CLASSIFICATION.groovy` | Read or run when you need a headless Fiji workflow that applies a trained Object Classification project to a raw image plus a probability map. |
| `GROOVY_WORKFLOW_MULTICUT.groovy` | Read or run when you need a headless Fiji workflow that applies a trained Multicut project to a raw image plus a boundary-probability image. |
| `GROOVY_WORKFLOW_TRACKING.groovy` | Read or run when you need a headless Fiji workflow that applies a trained Tracking project to a raw time series plus a matching probability or segmentation input. |
| `UI_GUIDE.md` | Read for menu paths, configuration steps, HDF5 tools, and the documented prediction wrappers. |
| `UI_WORKFLOW_PIXEL_CLASSIFICATION.md` | Read for the manual workflow to configure ilastik and run a pre-trained pixel-classification project from Fiji. |
| `UI_WORKFLOW_AUTOCONTEXT.md` | Read for the manual workflow to run a pre-trained Autocontext project from Fiji. |
| `UI_WORKFLOW_OBJECT_CLASSIFICATION.md` | Read for the manual workflow to run a pre-trained object-classification project from Fiji. |
| `UI_WORKFLOW_MULTICUT.md` | Read for the manual workflow to run a pre-trained Multicut project from Fiji. |
| `UI_WORKFLOW_TRACKING.md` | Read for the manual workflow to run a pre-trained Tracking project from Fiji. |
| `SKILL.md` | Read this file first for the scope and the automation boundary. |
