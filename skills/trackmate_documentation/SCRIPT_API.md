# TrackMate — SCRIPTING API REFERENCE (Groovy)

All patterns in this document are verified from:
- The official TrackMate manual (Jean-Yves Tinevez, 2016 PDF)
- https://imagej.net/plugins/trackmate/scripting/scripting
- https://imagej.net/plugins/trackmate/scripting/trackmate-detectors-trackers-keys

> Unlike StarDist or MorphoLibJ, **TrackMate is not driven by `IJ.run()` strings
> or the SciJava `command.run()` API.** It exposes its own Java object API directly.
> In Groovy scripts, you import the TrackMate Java classes and construct objects yourself.

---

## THE THREE CORE CLASSES

```groovy
import fiji.plugin.trackmate.Model        // data container
import fiji.plugin.trackmate.Settings     // configuration
import fiji.plugin.trackmate.TrackMate    // execution engine
```

### Minimal complete example

```groovy
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.detection.LogDetectorFactory
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.features.FeatureFilter
import ij.IJ

// 1. Get image
def imp = IJ.getImage()

// 2. Create model and set logger
def model = new Model()
model.setLogger(Logger.IJ_LOGGER)

// 3. Create settings, attach to image
def settings = new Settings(imp)

// 4. Configure detector
settings.detectorFactory = new LogDetectorFactory()
settings.detectorSettings = [
    'DO_SUBPIXEL_LOCALIZATION' : true,
    'RADIUS'                   : 2.5,     // physical units (µm if calibrated)
    'TARGET_CHANNEL'           : 1,
    'THRESHOLD'                : 0.0,     // 0 = keep all; filter below
    'DO_MEDIAN_FILTERING'      : false,
]

// 5. Configure tracker
settings.trackerFactory = new SimpleSparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE'] = 10.0

// 6. Optional: add a quality filter before feature computation
settings.initialSpotFilterValue = 1.0   // discard spots with quality < 1

// 7. Add spot feature analyzers (needed for MEAN_INTENSITY, SNR, etc.)
settings.addAllAnalyzers()              // adds all known analyzers (simplest approach)

// 8. Add a spot filter (post-detection)
settings.addSpotFilter(new FeatureFilter('QUALITY', 30.0, true))  // above 30

// 9. Run TrackMate
def trackmate = new TrackMate(model, settings)
if (!trackmate.checkInput()) {
    IJ.log("ERROR: " + trackmate.getErrorMessage())
    return
}
if (!trackmate.process()) {
    IJ.log("ERROR: " + trackmate.getErrorMessage())
    return
}

// 10. Log results
IJ.log("Tracks found: " + model.getTrackModel().nTracks(true))
```

---

## COMPLETE IMPORTS LIST

```groovy
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.SelectionModel
import fiji.plugin.trackmate.Spot

// Detectors (core Fiji — no extra update site needed)
import fiji.plugin.trackmate.detection.LogDetectorFactory
import fiji.plugin.trackmate.detection.DogDetectorFactory
import fiji.plugin.trackmate.detection.MaskDetectorFactory
import fiji.plugin.trackmate.detection.ThresholdDetectorFactory
import fiji.plugin.trackmate.detection.LabelImageDetectorFactory

// Trackers (core Fiji) — jaqaman package required in v8+ (sparselap package removed)
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.LAPUtils
import fiji.plugin.trackmate.tracking.kalman.KalmanTrackerFactory

// Feature filters
import fiji.plugin.trackmate.features.FeatureFilter

// Feature analyzers (common ones)
import fiji.plugin.trackmate.features.track.TrackDurationAnalyzer
import fiji.plugin.trackmate.features.track.TrackSpeedStatisticsAnalyzer
import fiji.plugin.trackmate.features.track.TrackIndexAnalyzer
import fiji.plugin.trackmate.features.spot.SpotIntensityAnalyzerFactory
import fiji.plugin.trackmate.features.spot.SpotContrastAndSNRAnalyzerFactory

// Display
import fiji.plugin.trackmate.visualization.hyperstack.HyperStackDisplayer

// IO
import fiji.plugin.trackmate.io.TmXmlWriter
import fiji.plugin.trackmate.io.TmXmlReader
import fiji.plugin.trackmate.action.ExportStatsToIJAction

import ij.IJ
import java.io.File
```

---

## SETTINGS CONFIGURATION

### Attaching to an image

```groovy
// Preferred: Settings constructor takes an ImagePlus
def settings = new Settings(imp)

// Alternative: create empty, then call setFrom()
def settings = new Settings()
settings.setFrom(imp)
```

### `settings.initialSpotFilterValue`

Always set this before calling `trackmate.process()` in scripts.
It discards spots below this quality threshold before feature computation, which prevents
computing features on thousands of noise spots and dramatically speeds up processing.

```groovy
settings.initialSpotFilterValue = 1.0   // recommended: 1.0 or slightly above noise level
```

---

## DETECTOR SETTINGS

### LoG Detector (`LogDetectorFactory`) and DoG Detector (`DogDetectorFactory`)

Both detectors use the same keys:

| Key | Groovy type | Description |
|-----|------------|-------------|
| `TARGET_CHANNEL` | `int` | Channel index, 1-based |
| `RADIUS` | `double` | Expected object radius in physical units (µm) |
| `THRESHOLD` | `double` | Minimum quality; use 0 to detect everything |
| `DO_SUBPIXEL_LOCALIZATION` | `boolean` | Sub-pixel position refinement (recommended: `true`) |
| `DO_MEDIAN_FILTERING` | `boolean` | Apply 3×3 median pre-filter; helps with speckle noise |

```groovy
settings.detectorFactory = new LogDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'           : 1,
    'RADIUS'                   : 2.5,
    'THRESHOLD'                : 0.0,
    'DO_SUBPIXEL_LOCALIZATION' : true,
    'DO_MEDIAN_FILTERING'      : false,
]
```

> Use `DogDetectorFactory` as a drop-in replacement for larger images where speed matters.

### Threshold Detector (`ThresholdDetectorFactory`)

| Key | Type | Description |
|-----|------|-------------|
| `TARGET_CHANNEL` | `int` | Channel with signal |
| `INTENSITY_THRESHOLD` | `double` | Pixel value cutoff |
| `SIMPLIFY_CONTOURS` | `boolean` | Smooth polygon contours |

```groovy
settings.detectorFactory = new ThresholdDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'      : 1,
    'INTENSITY_THRESHOLD' : 500.0,
    'SIMPLIFY_CONTOURS'   : true,
]
```

### Mask Detector (`MaskDetectorFactory`)

| Key | Type | Description |
|-----|------|-------------|
| `TARGET_CHANNEL` | `int` | Channel containing binary mask (pixels > 0 = object) |
| `SIMPLIFY_CONTOURS` | `boolean` | Smooth polygon contours |

### Label Image Detector (`LabelImageDetectorFactory`)

| Key | Type | Description |
|-----|------|-------------|
| `TARGET_CHANNEL` | `int` | Channel containing integer labels (each object = unique integer) |
| `SIMPLIFY_CONTOURS` | `boolean` | Smooth polygon contours |

---

## TRACKER SETTINGS

### Simple LAP Tracker (`SimpleSparseLAPTrackerFactory`)

Suitable for Brownian motion without splits or merges. Fewest parameters.

```groovy
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory

settings.trackerFactory = new SimpleSparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 10.0   // µm
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 10.0   // µm
settings.trackerSettings['MAX_FRAME_GAP']            = 2      // frames
```

| Key | Type | Description |
|-----|------|-------------|
| `LINKING_MAX_DISTANCE` | `double` | Max distance for frame-to-frame linking |
| `GAP_CLOSING_MAX_DISTANCE` | `double` | Max distance for gap-closing links |
| `MAX_FRAME_GAP` | `int` | Max number of frames a track can skip (gap closing) |

### Full LAP Tracker (`SparseLAPTrackerFactory`)

Extends the Simple LAP tracker with splits and merges.

```groovy
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory

settings.trackerFactory = new SparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()  // preferred over LAPUtils.getDefaultLAPSettingsMap()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 10.0
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 10.0
settings.trackerSettings['MAX_FRAME_GAP']            = 2
settings.trackerSettings['ALLOW_TRACK_SPLITTING']    = true
settings.trackerSettings['SPLITTING_MAX_DISTANCE']   = 10.0
settings.trackerSettings['ALLOW_TRACK_MERGING']      = false
settings.trackerSettings['MERGING_MAX_DISTANCE']     = 10.0
```

| Key | Type | Description |
|-----|------|-------------|
| `LINKING_MAX_DISTANCE` | `double` | Max distance for frame-to-frame linking |
| `GAP_CLOSING_MAX_DISTANCE` | `double` | Max distance for gap closing |
| `MAX_FRAME_GAP` | `int` | Max frames to bridge in gap closing |
| `ALLOW_TRACK_SPLITTING` | `boolean` | Enable split events (cell divisions) |
| `SPLITTING_MAX_DISTANCE` | `double` | Max distance for splitting links |
| `ALLOW_TRACK_MERGING` | `boolean` | Enable merge events |
| `MERGING_MAX_DISTANCE` | `double` | Max distance for merging links |

### Kalman Tracker (`KalmanTrackerFactory`)

For objects with linear/directed motion.

```groovy
settings.trackerFactory = new KalmanTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['KALMAN_SEARCH_RADIUS'] = 10.0   // search radius (µm)
settings.trackerSettings['MAX_FRAME_GAP']        = 2      // frames
settings.trackerSettings['INITIAL_SEARCH_RADIUS']= 10.0   // radius to start new tracks
```

---

## FEATURE ANALYZERS

Feature analyzers compute numerical properties for spots, edges, and tracks.
**In scripting, they must be added explicitly — the GUI adds them all automatically.**

### Simplest approach: add all known analyzers

```groovy
settings.addAllAnalyzers()    // adds all spot, edge, and track analyzers
```

This is the safe default for scripts that need any feature. It is slightly slower than
adding only the needed analyzers.

### Adding specific analyzers

```groovy
// Spot analyzers
import fiji.plugin.trackmate.features.spot.SpotIntensityAnalyzerFactory
import fiji.plugin.trackmate.features.spot.SpotContrastAndSNRAnalyzerFactory
settings.addSpotAnalyzerFactory(new SpotIntensityAnalyzerFactory())
settings.addSpotAnalyzerFactory(new SpotContrastAndSNRAnalyzerFactory())
// Note: SNR analyzer requires IntensityAnalyzer to run first

// Track analyzers
import fiji.plugin.trackmate.features.track.TrackDurationAnalyzer
import fiji.plugin.trackmate.features.track.TrackSpeedStatisticsAnalyzer
settings.addTrackAnalyzer(new TrackDurationAnalyzer())
settings.addTrackAnalyzer(new TrackSpeedStatisticsAnalyzer())
```

---

## FEATURE FILTERS

Filters discard spots or tracks whose feature value does not meet the threshold.

```groovy
import fiji.plugin.trackmate.features.FeatureFilter

// FeatureFilter(featureName, threshold, isAbove)
//   isAbove = true  → keep spots where feature > threshold
//   isAbove = false → keep spots where feature < threshold

// Spot filter: keep spots with quality above 30
settings.addSpotFilter(new FeatureFilter('QUALITY', 30.0, true))

// Track filter: keep tracks with more than 5 spots
settings.addTrackFilter(new FeatureFilter('NUMBER_SPOTS', 5.0, true))

// Track filter: remove immobile tracks (displacement < 10 µm)
settings.addTrackFilter(new FeatureFilter('TRACK_DISPLACEMENT', 10.0, true))
```

---

## ACCESSING RESULTS

### Track IDs

```groovy
// true = only filtered (visible) tracks
def trackIDs = model.getTrackModel().trackIDs(true)
IJ.log("Number of tracks: " + trackIDs.size())
```

### Iterating spots in a track

```groovy
for (def id in trackIDs) {
    def spots = model.getTrackModel().trackSpots(id)
    for (def spot in spots) {
        double x    = spot.getFeature('POSITION_X')
        double y    = spot.getFeature('POSITION_Y')
        double z    = spot.getFeature('POSITION_Z')
        double t    = spot.getFeature('POSITION_T')   // in physical time units
        int    frame= spot.getFeature('FRAME').intValue()
        double q    = spot.getFeature('QUALITY')
        double mean = spot.getFeature('MEAN_INTENSITY')
        double snr  = spot.getFeature('SNR')
        IJ.log("Track " + id + " spot: x=" + x + " y=" + y + " frame=" + frame)
    }
}
```

### Common spot feature keys

| Key | Description | Units |
|-----|-------------|-------|
| `POSITION_X` | X coordinate | Physical (µm) |
| `POSITION_Y` | Y coordinate | Physical (µm) |
| `POSITION_Z` | Z coordinate | Physical (µm) |
| `POSITION_T` | Time coordinate | Physical (s or min) |
| `FRAME` | Frame index (0-based integer) | — |
| `QUALITY` | Detection quality score | — |
| `RADIUS` | Spot radius | Physical (µm) |
| `MEAN_INTENSITY` | Mean pixel intensity in spot | intensity units |
| `MAX_INTENSITY` | Max pixel intensity | intensity units |
| `MIN_INTENSITY` | Min pixel intensity | intensity units |
| `MEDIAN_INTENSITY` | Median pixel intensity | intensity units |
| `TOTAL_INTENSITY` | Sum of all pixel intensities | intensity units |
| `SNR` | Signal-to-noise ratio | — |
| `CONTRAST` | Contrast (needs SpotContrastAndSNRAnalyzer) | — |

### Track features (from the FeatureModel)

```groovy
def fm = model.getFeatureModel()
for (def id in trackIDs) {
    double duration     = fm.getTrackFeature(id, 'TRACK_DURATION')
    double displacement = fm.getTrackFeature(id, 'TRACK_DISPLACEMENT')
    double meanSpeed    = fm.getTrackFeature(id, 'TRACK_MEAN_SPEED')
    int    nSpots       = fm.getTrackFeature(id, 'NUMBER_SPOTS').intValue()
    IJ.log("Track " + id + ": duration=" + duration + " displacement=" + displacement)
}
```

### Common track feature keys

| Key | Description |
|-----|-------------|
| `TRACK_DURATION` | Total duration (physical time units) |
| `TRACK_DISPLACEMENT` | Straight-line distance first→last spot |
| `TRACK_MEAN_SPEED` | Mean instantaneous speed |
| `TRACK_MAX_SPEED` | Maximum instantaneous speed |
| `TRACK_MIN_SPEED` | Minimum instantaneous speed |
| `TRACK_MEDIAN_SPEED` | Median speed |
| `TRACK_STD_SPEED` | Standard deviation of speed |
| `NUMBER_SPOTS` | Total number of spots in track |
| `NUMBER_GAPS` | Number of gap-closed frames |
| `NUMBER_SPLITS` | Number of split events |
| `NUMBER_MERGES` | Number of merge events |
| `TRACK_INDEX` | Unique track index (0-based) |

### Edge features

```groovy
def fm = model.getFeatureModel()
for (def id in trackIDs) {
    for (def edge in model.getTrackModel().trackEdges(id)) {
        double velocity    = fm.getEdgeFeature(edge, 'VELOCITY')
        double displacement= fm.getEdgeFeature(edge, 'DISPLACEMENT')
    }
}
```

---

## DISPLAYING RESULTS

```groovy
import fiji.plugin.trackmate.SelectionModel
import fiji.plugin.trackmate.visualization.hyperstack.HyperStackDisplayer
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings

def selectionModel = new SelectionModel(model)
def ds = DisplaySettings.defaultStyle()   // NOT new DisplaySettings()
def displayer = new HyperStackDisplayer(model, selectionModel, imp, ds)  // 4-arg constructor in v8+
displayer.render()
displayer.refresh()
```

---

## SAVING TO XML

```groovy
import fiji.plugin.trackmate.io.TmXmlWriter
import java.io.File

def xmlFile = new File("/path/to/output/session.xml")
def writer = new TmXmlWriter(xmlFile)
writer.appendLog("Written by script")
writer.appendModel(model)
writer.appendSettings(settings)
writer.writeToFile()
IJ.log("Saved: " + xmlFile.getAbsolutePath())
```

## LOADING FROM XML

```groovy
import fiji.plugin.trackmate.io.TmXmlReader
import fiji.plugin.trackmate.providers.*
import java.io.File

def xmlFile = new File("/path/to/session.xml")
def reader = new TmXmlReader(xmlFile)
if (!reader.isReadingOk()) {
    IJ.log("ERROR: " + reader.getErrorMessage())
    return
}
def model = reader.getModel()
// Re-build settings (needed for re-running)
def settings = new Settings()
reader.readSettings(settings,
    new DetectorProvider(),
    new TrackerProvider(),
    new SpotAnalyzerProvider(),
    new EdgeAnalyzerProvider(),
    new TrackAnalyzerProvider()
)
def imp = settings.imp
imp.show()
```

---

## EXPORTING TO CSV (v7+ API)

```groovy
import fiji.plugin.trackmate.visualization.table.TrackTableView
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings

def sm = new SelectionModel(model)
def ds = DisplaySettings.defaultStyle()   // NOT new DisplaySettings()
def tableView = new TrackTableView(model, sm, ds)
tableView.getSpotTable().exportToCsv(new File("/path/to/spots.csv"))
tableView.getTrackTable().exportToCsv(new File("/path/to/tracks.csv"))
```

---

## KNOWN PITFALLS

1. **Feature analyzers are not automatic.** Unlike the GUI, scripts do not add analyzers
   by default. Call `settings.addAllAnalyzers()` or add specific analyzers before running,
   or features like `MEAN_INTENSITY`, `SNR`, `TRACK_MEAN_SPEED` will be null.

2. **`settings.initialSpotFilterValue` must be set.** If left at 0, TrackMate computes
   features on all detected spots including noise, which can be extremely slow on dense images.
   Set to a small positive value (e.g. 1.0) before calling `trackmate.process()`.

3. **Always call `checkInput()` before `process()`.** `checkInput()` validates the
   configuration (image not null, detector settings valid, etc.). Skipping it and calling
   `process()` directly can produce silent failures or confusing errors.

4. **Calibration units.** All distances (RADIUS, LINKING_MAX_DISTANCE, etc.) use
   **physical units** (µm if pixel size is in µm), not pixels. For uncalibrated images
   (1 px = 1 px), the "physical" unit is effectively pixels.

5. **Z vs T axis.** If `imp.getNFrames() == 1`, TrackMate sees a single time point and
   will not track. Check `imp.getDimensions()` — the order is [x, y, c, z, t]. If z and t
   are swapped, use `imp.setDimensions(nChannels, nSlices, nFrames)` to fix it.

6. **SparseLAPTracker default settings map.** When using `SparseLAPTrackerFactory`,
   always start with `settings.trackerFactory.getDefaultSettings()` and override only the
   keys you need. Do not build the settings map from scratch — it requires many internal
   keys (penalty structures, etc.) that the default map already contains correctly.

7. **Tracker package changed in v8+.** All tracker classes moved from
   `fiji.plugin.trackmate.tracking.sparselap` to `fiji.plugin.trackmate.tracking.jaqaman`.
   `SimpleSparseLAPTrackerFactory` still exists — it was moved, not removed.

7. **`trackIDs(true)` vs `trackIDs(false)`.** The `true` argument returns only **filtered**
   (visible) tracks — the ones that passed the track filters. `false` returns all tracks
   including hidden ones. Use `true` for analysis results.
