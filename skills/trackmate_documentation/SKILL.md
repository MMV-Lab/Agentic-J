---
name: trackmate_documentation
description: TrackMate is a Fiji/ImageJ plugin for single-particle tracking (SPT). It detects objects in 2D/3D timelapses and links them into tracks over time. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---

# TrackMate — SKILL SUMMARY (LLM Reference Card)

- Works: 2D+T, 3D+T, grayscale fluorescence or label images
- Detects: round spots (LoG/DoG), thresholded objects, label-image objects, or manually placed spots
- Tracks: Brownian motion (LAP), directed motion (Kalman), or shape-based overlap
- Included in core Fiji — no extra update site for basic use
- Launched via: **Plugins ▶ Tracking ▶ TrackMate**

---

## Scripting — The Only Pattern You Need

TrackMate does NOT use `IJ.run()` strings or `command.run()`.
It uses its own Java object API directly via Groovy imports.

### Three mandatory classes

```groovy
import fiji.plugin.trackmate.Model        // data container
import fiji.plugin.trackmate.Settings     // configuration
import fiji.plugin.trackmate.TrackMate    // execution engine
```

### Minimal complete Groovy script

```groovy
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.detection.LogDetectorFactory
import fiji.plugin.trackmate.tracking.sparselap.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.features.FeatureFilter
import ij.IJ

def imp = IJ.getImage()
def model = new Model()
model.setLogger(Logger.IJ_LOGGER)

def settings = new Settings(imp)
settings.detectorFactory = new LogDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'           : 1,
    'RADIUS'                   : 2.5,   // physical units (µm or px)
    'THRESHOLD'                : 0.0,
    'DO_SUBPIXEL_LOCALIZATION' : true,
    'DO_MEDIAN_FILTERING'      : false,
]
settings.initialSpotFilterValue = 1.0   // REQUIRED — prevents slow feature computation on noise
settings.addAllAnalyzers()              // REQUIRED in scripts — the GUI adds these automatically
settings.addSpotFilter(new FeatureFilter('QUALITY', 30.0, true))

settings.trackerFactory = new SimpleSparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 10.0
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 10.0
settings.trackerSettings['MAX_FRAME_GAP']            = 2

settings.addTrackFilter(new FeatureFilter('NUMBER_SPOTS', 3.0, true))

def trackmate = new TrackMate(model, settings)
if (!trackmate.checkInput() || !trackmate.process()) {
    IJ.log("ERROR: " + trackmate.getErrorMessage()); return
}

IJ.log("Tracks: " + model.getTrackModel().nTracks(true))
```

---

## Detector Settings Quick Reference

### LoG / DoG (`LogDetectorFactory` / `DogDetectorFactory`)
```groovy
settings.detectorFactory = new LogDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'           : 1,      // int, 1-based channel
    'RADIUS'                   : 2.5,    // double, physical units
    'THRESHOLD'                : 0.0,    // double, 0 = detect all
    'DO_SUBPIXEL_LOCALIZATION' : true,   // boolean
    'DO_MEDIAN_FILTERING'      : false,  // boolean
]
```

### Label Image (`LabelImageDetectorFactory`) — v7+
```groovy
settings.detectorFactory = new LabelImageDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'   : 2,      // channel containing integer labels
    'SIMPLIFY_CONTOURS': true,
]
```

### Threshold (`ThresholdDetectorFactory`) — v7+
```groovy
settings.detectorFactory = new ThresholdDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'      : 1,
    'INTENSITY_THRESHOLD' : 500.0,
    'SIMPLIFY_CONTOURS'   : true,
]
```

---

## Tracker Settings Quick Reference

### Simple LAP (no splits/merges) — most common
```groovy
settings.trackerFactory = new SimpleSparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 10.0
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 10.0
settings.trackerSettings['MAX_FRAME_GAP']            = 2
```

### Full LAP (splits, merges, gap closing)
```groovy
import fiji.plugin.trackmate.tracking.sparselap.SparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.LAPUtils
settings.trackerFactory = new SparseLAPTrackerFactory()
settings.trackerSettings = LAPUtils.getDefaultLAPSettingsMap()  // ALWAYS start from defaults
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 10.0
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 10.0
settings.trackerSettings['MAX_FRAME_GAP']            = 2
settings.trackerSettings['ALLOW_TRACK_SPLITTING']    = true
settings.trackerSettings['SPLITTING_MAX_DISTANCE']   = 10.0
settings.trackerSettings['ALLOW_TRACK_MERGING']      = false
```

---

## Accessing Results

```groovy
// Iterate all visible tracks and their spots
def trackIDs = model.getTrackModel().trackIDs(true)   // true = filtered tracks only
def fm = model.getFeatureModel()

for (def id in trackIDs) {
    double speed  = fm.getTrackFeature(id, 'TRACK_MEAN_SPEED')
    int    nSpots = fm.getTrackFeature(id, 'NUMBER_SPOTS').intValue()

    for (def spot in model.getTrackModel().trackSpots(id)) {
        double x     = spot.getFeature('POSITION_X')
        double y     = spot.getFeature('POSITION_Y')
        int    frame = spot.getFeature('FRAME').intValue()
        double mean  = spot.getFeature('MEAN_INTENSITY')
    }
}
```

---

## Key Spot Features

| Key | Description |
|-----|-------------|
| `POSITION_X/Y/Z` | Coordinates in physical units |
| `POSITION_T` | Time in physical units |
| `FRAME` | Frame index (0-based integer) |
| `QUALITY` | Detection quality score |
| `RADIUS` | Radius in physical units |
| `MEAN_INTENSITY` | Mean pixel intensity |
| `SNR` | Signal-to-noise ratio |

## Key Track Features (from `model.getFeatureModel()`)

| Key | Description |
|-----|-------------|
| `TRACK_DURATION` | Duration in physical time units |
| `TRACK_DISPLACEMENT` | Straight-line distance first→last spot |
| `TRACK_MEAN_SPEED` | Mean instantaneous speed |
| `NUMBER_SPOTS` | Spots in track |
| `NUMBER_GAPS` | Gap-closed frames |
| `NUMBER_SPLITS` | Split events |

---

## 7 Critical Pitfalls

### Pitfall 1 — `settings.addAllAnalyzers()` REQUIRED in scripts
The GUI adds analyzers automatically. Scripts do not. Without this, MEAN_INTENSITY,
SNR, TRACK_MEAN_SPEED, etc. will all be null.

### Pitfall 2 — `settings.initialSpotFilterValue` REQUIRED
```groovy
settings.initialSpotFilterValue = 1.0   // ALWAYS set before process()
```
Without this, TrackMate computes features on all raw detections including noise,
which can be extremely slow on dense images.

### Pitfall 3 — `checkInput()` before `process()`
Always call both. `checkInput()` catches configuration errors before running.

### Pitfall 4 — distances are in physical units, not pixels
If your image is calibrated (pixel = 0.5 µm), then `RADIUS = 2.5` means 2.5 µm.
For uncalibrated images (1 pixel = 1 unit), it means 2.5 pixels.

### Pitfall 5 — Z vs T axis confusion
If `imp.getNFrames() == 1`, TrackMate has a single time point and won't track.
Fix: `imp.setDimensions(nChannels, 1, nSlices)` to reclassify slices as frames.

### Pitfall 6 — SparseLAPTracker requires default map
```groovy
// WRONG — builds from scratch, missing required internal keys:
settings.trackerSettings = ['LINKING_MAX_DISTANCE': 10.0]

// CORRECT — start from defaults, then override:
settings.trackerSettings = LAPUtils.getDefaultLAPSettingsMap()
settings.trackerSettings['LINKING_MAX_DISTANCE'] = 10.0
```

### Pitfall 7 — `trackIDs(true)` vs `trackIDs(false)`
`true` = filtered (visible) tracks only (what you normally want for analysis).
`false` = all tracks including those hidden by filters.

---

## Parameter Tuning Guide

| Observation | Fix |
|-------------|-----|
| Too many false-positive spots | Raise `QUALITY_THRESHOLD` |
| Real spots being missed | Lower `QUALITY_THRESHOLD`; reduce `RADIUS` |
| Tracks broken into short fragments | Raise `LINKING_MAX_DISTANCE`; enable gap closing |
| Tracks crossing and swapping identity | Lower `LINKING_MAX_DISTANCE` |
| Too many short stub tracks | Raise `MIN_TRACK_SPOTS` filter |
| Dividing cells tracked as two separate objects | Enable `ALLOW_TRACK_SPLITTING` with full LAP tracker |

---

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin description, use cases, core architecture, detector/tracker tables, installation, limitations |
| `UI_GUIDE.md` | Complete GUI panel reference — every control in the TrackMate wizard explained |
| `UI_WORKFLOW_PARTICLE_TRACKING.md` | **GUI walkthrough**: automated tracking from open image to CSV export |
| `SCRIPT_API.md` | Full Groovy scripting API with all detector/tracker keys, feature access, CSV export, XML save/load |
| `GROOVY_WORKFLOW_PARTICLE_TRACKING.groovy` | **Executable Groovy script**: detect → filter → track → export CSV + XML |
| `SKILL.md` | This file — LLM quick-reference card |
