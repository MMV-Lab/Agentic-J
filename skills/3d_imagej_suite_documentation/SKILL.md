---
name: 3d_imagej_suite_documentation
description: 3D ImageJ Suite is a Fiji/ImageJ plugin collection for 3D filtering, segmentation, measurement, and ROI management. This skill keeps a compact validated workflow set for this repo: a default threshold-based segment-and-measure pipeline, 3D watershed, automatic-seed 3D spot segmentation, 3D nuclei segmentation, label-image measurement, and the installed 3D Manager V4 macro extensions. Read the files listed at the end of this SKILL for exact Groovy calls, menu paths, and scope limits.
---

## Primary Use Case in This Skill Set

3D object segmentation and measurement from a grayscale stack:

```text
3D TIFF stack
  -> mean smoothing
  -> threshold to binary
  -> connected-component labels
  -> volume and intensity tables
```

Additional validated workflow files cover:

- filter-only execution
- watershed with automatic seeds
- automatic-seed spot segmentation
- nuclei segmentation
- measurement of an existing label image

## Verified Automation Boundary

- Container-validated:
  - `IJ.run(..., "3D Fast Filters", ...)`
  - `mcib3d.image3d.processing.FastFilters3D`
  - `mcib3d.image3d.ImageHandler`
  - `mcib3d.image3d.ImageLabeller`
  - `mcib3d.image3d.regionGrowing.Watershed3D`
  - `mcib3d.image3d.segment.Segment3DSpots`
  - `mcib3d.image3d.segment.Segment3DNuclei`
  - `mcib_plugins.analysis.SimpleMeasure`
- Installed in Fiji and source-grounded:
  - `run("3D Manager V4 Macros")` with `Ext.Manager3DV4_*`
- Official-doc workflow surface:
  - `3D Intensity Measure`
  - `3D Volume`

## Scope Limits

- This skill does not document macro parameter strings for `3D Simple Segmentation`, `3D Watershed`, `3D Spot Segmentation`, or `3D Nuclei Segmentation`.
- `3D Manager V4 Macros` is not documented as a headless automation path in this skill. In this repo's container it initializes the 3D viewer during startup, so the extension is display-dependent.
- This skill uses the V4 macro extension names from the installed `MacroV4.ijm` file. The older `Ext.Manager3D_*` macro names remain in legacy docs but are not the default automation path documented here.

## File Index

| File | Contents |
|------|----------|
| `OVERVIEW.md` | Plugin surface summary, install path, covered workflow families, and explicit exclusions |
| `SCRIPT_API.md` | Exact validated Groovy API calls, the validated `IJ.run` string for 3D Fast Filters, and 3D Manager V4 macro examples |
| `GROOVY_WORKFLOW_3D_SEGMENT_AND_MEASURE.groovy` | Default runnable Fiji workflow for smoothing, thresholding, 3D labeling, and CSV export |
| `GROOVY_WORKFLOW_3D_WATERSHED.groovy` | Runnable Fiji workflow for automatic-seed 3D watershed segmentation |
| `GROOVY_WORKFLOW_3D_SPOT_SEGMENTATION.groovy` | Runnable Fiji workflow for automatic-seed 3D spot segmentation |
| `GROOVY_WORKFLOW_3D_NUCLEI_SEGMENTATION.groovy` | Runnable Fiji workflow for 3D nuclei segmentation |
| `GROOVY_WORKFLOW_3D_MEASURE_LABEL_IMAGE.groovy` | Utility workflow for volume and intensity measurements from an existing label stack |
| `GROOVY_WORKFLOW_3D_FAST_FILTER.groovy` | Utility workflow for 3D Fast Filters with a saved TIFF output |
| `UI_GUIDE.md` | Verified menu paths and the documented controls for the parts of 3D Suite used in this skill |
| `UI_WORKFLOW_3D_SEGMENT_AND_MEASURE.md` | Manual step-by-step workflow for segmenting and measuring bright 3D objects |
