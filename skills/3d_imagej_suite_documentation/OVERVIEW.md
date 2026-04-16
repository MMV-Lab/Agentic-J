# 3D ImageJ Suite — Overview

3D ImageJ Suite is a large Fiji plugin collection maintained by the `mcib3d`
project. It adds 3D filtering, binary morphology, seeded and unseeded
segmentation, geometry and intensity measurements, spatial analysis, and 3D ROI
management under the `Plugins > 3DSuite` menu tree.

## Installation

Enable the `Tboudier` update site in Fiji:

1. `Help > Update...`
2. `Manage update sites`
3. Enable `3D ImageJ Suite`
4. Apply changes and restart Fiji

The official project pages used for this skill are:

- `https://imagej.net/plugins/3d-imagej-suite`
- `https://mcib3d.frama.io/3d-suite-imagej/`

## Covered in This Skill

This skill documents the parts of the suite that have a reliable scripting path
for this repo:

- a default threshold-based segment-and-measure workflow
- automatic-seed 3D watershed segmentation
- automatic-seed 3D spot segmentation
- 3D nuclei segmentation
- per-object volume measurements
- per-object intensity measurements against a separate signal stack
- 3D Manager V4 macro extensions for object import and per-object queries

## Runnable Workflows

Core workflows:

- `GROOVY_WORKFLOW_3D_SEGMENT_AND_MEASURE.groovy`
- `GROOVY_WORKFLOW_3D_WATERSHED.groovy`
- `GROOVY_WORKFLOW_3D_SPOT_SEGMENTATION.groovy`
- `GROOVY_WORKFLOW_3D_NUCLEI_SEGMENTATION.groovy`

Utility workflows:

- `GROOVY_WORKFLOW_3D_MEASURE_LABEL_IMAGE.groovy`
- `GROOVY_WORKFLOW_3D_FAST_FILTER.groovy`

## Main Menu Families

The installed plugin registers these menu groups under `Plugins > 3DSuite`:

- `Filters`
- `Binary`
- `Segmentation`
- `Analysis`
- `Relationship`
- `Spatial`
- `Tools`
- `3D Manager`
- `3D Manager V4 (beta)`
- `3D Manager V4 Macros`

## Automation Guidance

Use the Groovy API when you need predictable batch execution:

- `FastFilters3D.filterIntImageStack(...)` or `filterFloatImageStack(...)`
- `ImageHandler.thresholdAboveInclusive(...)`
- `ImageLabeller.getLabels(...)` or `getLabelsFloat(...)`
- `Watershed3D(...)` with a seed image from `MaximumLocal`
- `Segment3DSpots(...)`
- `Segment3DNuclei(...)`
- `SimpleMeasure.getResultsTable("Volume")`
- `SimpleMeasure.getMeasuresStats(signalImp)`

Use the macro extension path when you already have a labelled object image and
need per-object queries inside a macro:

- `run("3D Manager V4 Macros")`
- `Ext.Manager3DV4_ImportImage()`
- `Ext.Manager3DV4_NbObjects(nb)`
- `Ext.Manager3DV4_Measure(...)`

Keep the V4 manager on a display-backed Fiji session. In this repo's container
the macro loader touches the 3D viewer during initialization, so it is not a
true headless entry point.

## Explicit Exclusions

The following areas are not documented as script-ready in this skill:

- macro parameter strings for `3D Simple Segmentation`
- macro parameter strings for `3D Watershed`
- macro parameter strings for `3D Spot Segmentation`
- macro parameter strings for `3D Nuclei Segmentation`
- legacy `Ext.Manager3D_*` macro calls from the older manager

These features remain available in the GUI and in the official docs, but they
are outside the validated automation surface captured here.
