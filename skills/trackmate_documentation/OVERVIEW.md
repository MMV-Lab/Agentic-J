# TrackMate — OVERVIEW

## What It Is
TrackMate is a Fiji/ImageJ plugin for automated, semi-automated, and manual
**single-particle tracking (SPT)** in fluorescence microscopy images. It follows the
classical two-step SPT scheme: detection of objects in each frame, then linking of
those objects across frames into tracks. The two steps are completely separated,
allowing independent algorithm choice and parameter tuning.

TrackMate works in 2D (XY+T) and 3D (XYZ+T). Starting with version 7, it can also
detect, store, and visualize **object contours** (polygons in 2D), enabling morphology
measurements over time.

Developed by Jean-Yves Tinevez and collaborators at Institut Pasteur / BIOP.
Distributed as part of the core Fiji distribution — **no additional update sites needed**
for basic use.

> **Core concept:** TrackMate deliberately detects as many spots as possible, including
> false ones. You then filter by quality to keep only real objects, and tune tracking
> distances for your motion type. Think of it as a wide net with adjustable mesh size.

---

## Typical Inputs and Use Cases

### 1 — Fluorescent particle tracking (cells, nuclei, vesicles)
- **Input:** 2D+T or 3D+T fluorescence image; objects are roughly spherical/round
- **Detector:** LoG or DoG
- **Goal:** Track trajectories over time; measure velocity, displacement, mean speed
- **When it works well:** Well-separated objects, good SNR, Brownian or directed motion
- **Key parameters:** `RADIUS` in physical units, `THRESHOLD` for quality filter,
  `LINKING_MAX_DISTANCE`, `GAP_CLOSING_MAX_DISTANCE`

### 2 — Cell tracking in timelapse (morphology-based, v7+)
- **Input:** 2D+T timelapse; cells are large objects with visible shape
- **Detector:** ThresholdDetector, LabelImageDetector, StarDistDetector, or MorphoLibJDetector
- **Goal:** Follow individual cells; extract area, circularity, intensity per cell over time
- **When it works well:** Cells with clear boundaries, moderate density, consistent labelling

### 3 — Cell lineage analysis (division tracking)
- **Input:** 2D+T or 3D+T timelapse with dividing cells
- **Tracker:** SparseLAPTracker with `ALLOW_TRACK_SPLITTING = true`
- **Goal:** Reconstruct full lineage tree; identify mother/daughter relationships
- **Visualization:** TrackScheme window displays the lineage graph and allows manual editing

### 4 — Manual or semi-automatic annotation
- **Entry point:** Plugins ▶ Tracking ▶ Manual tracking with TrackMate
- **Goal:** Manually add spots frame-by-frame; link them with keyboard shortcuts;
  use the semi-automatic tracker to propagate detection forward from a seed spot
- **When to use:** When automatic detection is unreliable; sparse or irregular objects

### 5 — Tracking from a pre-existing segmentation (v7+)
- **Input:** Timelapse image + label image (each object = unique integer value) as a channel
- **Detector:** LabelImageDetector — reads object contours directly from integer labels
- **Goal:** Combine any external segmentation result (StarDist, cellpose, ilastik, etc.)
  with TrackMate's tracking and analysis pipeline without re-detecting

### 6 — Batch / headless scripting
- **Input:** Directory of timelapse TIFFs
- **Approach:** Groovy script using the TrackMate Java API directly
- **Goal:** Fully automated detect → filter → track → export for many images
- **Output:** Per-image XML session files + CSV tables of spot/track features

---

## Core Architecture (3 classes)

### `Model` — the data container
Holds all computed results: the set of detected spots, the edges (links between spots),
and the tracks (connected chains). Created empty, populated by the `TrackMate` engine.
In scripting: `def model = new Model()`

### `Settings` — the configuration
Holds all parameters: source image, detector, tracker, feature analyzers, filters.
In scripting: `def settings = new Settings(); settings.setFrom(imp)`

### `TrackMate` — the execution engine
Reads the `Settings`, runs detection and tracking, and populates the `Model`.
In scripting: `def trackmate = new TrackMate(model, settings)`
Then: `trackmate.checkInput()` then `trackmate.process()`

---

## Data Objects

| Object | Description | Physical units |
|--------|-------------|---------------|
| **Spot** | Detected object at one (x, y, z, t); has radius and quality | μm, calibrated |
| **Edge** | Directed link between two spots in consecutive or nearby frames | — |
| **Track** | Connected chain of spots/edges = one object's trajectory | — |

---

## Detection Algorithms

| Detector class | Input type | Notes |
|---------------|-----------|-------|
| `LogDetectorFactory` | Grayscale | LoG; best for well-separated round spots |
| `DogDetectorFactory` | Grayscale | DoG; faster LoG approximation |
| `MaskDetectorFactory` | Binary mask channel | Objects from a binary mask |
| `ThresholdDetectorFactory` | Grayscale | Segments by intensity threshold; produces contours (v7+) |
| `LabelImageDetectorFactory` | Label image channel | Objects from integer labels; preserves contours (v7+) |
| `ManualDetectorFactory` | — | Skips auto-detection; all spots placed manually |
| `StarDistDetectorFactory`* | Grayscale | Requires TrackMate-StarDist update site |
| `CellposeDetectorFactory`* | Grayscale | Requires TrackMate-Cellpose + local cellpose install |
| `MorphoLibJDetectorFactory`* | Grayscale | Requires TrackMate-MorphoLibJ + IJPB-plugins |

*Requires an extra update site subscription.

---

## Tracking Algorithms

| Tracker class | Best for |
|--------------|---------|
| `SimpleSparseLAPTrackerFactory` | Brownian motion, no splits or merges |
| `SparseLAPTrackerFactory` | Brownian motion + optional splits + merges |
| `KalmanTrackerFactory` | Linear / directed motion |
| `NearestNeighborTrackerFactory` | Simple nearest-neighbour; low density |
| `OverlapTrackerFactory` | Shape-based overlap (requires v7 contour objects) |
| `ManualTrackerFactory` | Fully manual track assignment only |

---

## Output Types

| Output | Where |
|--------|-------|
| Spot table (position, intensity, shape) | GUI: Actions → Export statistics to IJ tables |
| Track table (velocity, duration, displacement) | Same as above |
| Edge table (frame-to-frame velocity, displacement) | Same as above |
| XML session file | GUI: Save button; Script: `TmXmlWriter` |
| Track overlay on image | HyperStack Displayer (default view) |
| Lineage graph | TrackScheme window |
| CSV export in script | `TrackTableView.exportToCsv()` (v7+ API) |

---

## Installation

TrackMate is **bundled with Fiji** — no installation required for the basic detectors
(LoG, DoG, Threshold, Mask, LabelImage, Manual) and all trackers.

For extended detectors, subscribe to the corresponding update sites via
Help ▶ Update... ▶ Manage update sites:

| Extension needed | Update sites to tick |
|-----------------|---------------------|
| StarDist detector in TrackMate | `TrackMate-StarDist` + `StarDist` + `CSBDeep` + `TensorFlow` |
| Cellpose detector | `TrackMate-Cellpose` (+ install cellpose Python externally) |
| MorphoLibJ detector | `TrackMate-MorphoLibJ` + `IJPB-plugins` |
| Ilastik detector | `TrackMate-Ilastik` + `Ilastik` (+ install ilastik app) |
| Weka detector | `TrackMate-Weka` (Weka Segmentation is core Fiji) |

---

## Important Constraints and Limitations

- **Object contour detection is 2D-only.** In 3D images, shape-based detectors (v7+)
  create a spherical spot of equivalent volume rather than a true 3D contour.
- **Calibration is critical.** All parameters use **physical units** (μm, s), not pixels.
  Always verify via Image ▶ Properties before launching TrackMate.
- **Z vs T confusion.** A timelapse that loaded as a Z-stack (1 time point, N slices)
  must have its dimensions corrected before running TrackMate.
- **Feature analyzers not automatic in scripting.** The GUI adds all analyzers
  automatically; scripts must add them explicitly to `settings` to compute features
  like velocity, SNR, mean intensity.
- **`settings.initialSpotFilterValue`** — always set this to a small positive number
  (e.g. 1.0) in scripts to avoid computing features on thousands of very low-quality
  spots and slowing down processing.

---

## Citation

Primary publication: Tinevez, J-Y.; Perry, N.; Schindelin, J. et al. (2017).
"TrackMate: An open and extensible platform for single-particle tracking."
*Methods* 115: 80–90. doi:10.1016/j.ymeth.2016.09.016

Version 7 publication: Ershov, D. et al. (2022). "TrackMate 7: integrating
state-of-the-art segmentation algorithms into single-particle tracking."
*Nature Methods* 19, 829–832. doi:10.1038/s41592-022-01507-1
