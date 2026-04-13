---
name: trackmate_documentation
description: TrackMate is a Fiji/ImageJ plugin for single-particle tracking (SPT) and cell segmentation in fluorescence microscopy. It detects and segments objects in 2D/3D images and timelapses — using built-in detectors (LoG, DoG, Threshold, LabelImage) or deep-learning models (Cellpose, StarDist) — and optionally links them into tracks over time. Cellpose can be used for single-image segmentation as well as multi-frame cell tracking. Use this skill for scripting TrackMate workflows in Groovy, understanding the GUI, integrating Cellpose segmentation (single image or timelapse), and exporting results to CSV or XML.
---

# TrackMate — Documentation Index

TrackMate is bundled with Fiji (core detectors and trackers). Cellpose and StarDist integration require additional update sites. All scripting uses the TrackMate Java API directly — not `IJ.run()`.

## Files

| File | What it covers |
|------|---------------|
| `SCRIPT_API.md` | Complete Groovy scripting reference: detector/tracker settings keys, feature access, CSV/XML export, all imports |
| `GROOVY_WORKFLOW_PARTICLE_TRACKING.groovy` | Ready-to-run script: LoG detection → filtering → LAP tracking → CSV + XML + overlay |
| `CELLPOSE_DETECTOR_API.md` | Cellpose integration: all detector settings keys, available models (cyto3, nuclei, etc.), backend setup, pitfalls — covers single-image segmentation and timelapse tracking |
| `GROOVY_WORKFLOW_CELLPOSE_GENERIC.groovy` | Ready-to-run generic script: auto-detects Python/conda/micromamba backend → Cellpose segment → track → CSV + XML + label TIFF; works on any active image |
| `GROOVY_WORKFLOW_CELLPOSE_GUI.groovy` | Ready-to-run project-specific script: opens a hardcoded file, GPU-enabled Cellpose → tracking → CSV + XML + label TIFF + HyperStack overlay + TrackScheme GUI |
| `UI_GUIDE.md` | GUI reference: every panel and control in the TrackMate wizard explained |
| `UI_WORKFLOW_PARTICLE_TRACKING.md` | GUI walkthrough: step-by-step from open image to exported CSV |
