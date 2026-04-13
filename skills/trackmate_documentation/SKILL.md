---
name: trackmate_documentation
description: TrackMate is a Fiji/ImageJ plugin for single-particle tracking (SPT) and cell segmentation tracking in fluorescence microscopy. It detects and segments objects in 2D/3D timelapses — using built-in detectors (LoG, DoG, Threshold, LabelImage) or deep-learning models (Cellpose, StarDist) — and links them into tracks over time. Use this skill for scripting TrackMate workflows in Groovy, understanding the GUI, integrating Cellpose segmentation, and exporting tracking results to CSV or XML.
---

# TrackMate — Documentation Index

TrackMate is bundled with Fiji (core detectors and trackers). Cellpose and StarDist integration require additional update sites. All scripting uses the TrackMate Java API directly — not `IJ.run()`.

## Files

| File | What it covers |
|------|---------------|
| `SCRIPT_API.md` | Complete Groovy scripting reference: detector/tracker settings keys, feature access, CSV/XML export, all imports |
| `GROOVY_WORKFLOW_PARTICLE_TRACKING.groovy` | Ready-to-run script: LoG detection → filtering → LAP tracking → CSV + XML + overlay |
| `CELLPOSE_DETECTOR_API.md` | Cellpose integration: all detector settings keys, available models, backend setup, and pitfalls |
| `GROOVY_WORKFLOW_CELLPOSE.groovy` | Ready-to-run script: Cellpose backend auto-detection → segmentation → tracking → CSV + XML + label TIFF export |
| `UI_GUIDE.md` | GUI reference: every panel and control in the TrackMate wizard explained |
| `UI_WORKFLOW_PARTICLE_TRACKING.md` | GUI walkthrough: step-by-step from open image to exported CSV |
