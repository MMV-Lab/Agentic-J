/**
 * TrackMate — Automated Particle Tracking Workflow
 * Groovy script for Fiji Script Editor (Language: Groovy)
 *
 * PURPOSE:
 *   Fully automated single-particle tracking pipeline on the active Fiji image:
 *     1. Validate image dimensions (Z vs T check)
 *     2. Detect spots using the LoG detector
 *     3. Filter spots by quality
 *     4. Link spots into tracks using the Simple LAP tracker (or full LAP)
 *     5. Filter tracks by number of spots
 *     6. Log summary statistics (spot count, track count, mean speed)
 *     7. Export spot, edge, and track features to CSV files
 *     8. Save the full TrackMate session as an XML file
 *     9. (Optional) Display overlay on the image
 *
 * INPUTS:
 *   Active image: A 2D+T (or 3D+T) grayscale timelapse image open in Fiji.
 *   The image MUST have more than 1 time frame. If it loads as a Z-stack
 *   with 1 frame, set Image > Properties first or adjust SWAP_Z_T below.
 *
 *   Test image: File > Open Samples > Tracks for TrackMate (807K)
 *
 * OUTPUTS:
 *   <title>-spots.csv        : per-spot measurements (position, intensity, etc.)
 *   <title>-tracks.csv       : per-track statistics (speed, duration, displacement)
 *   <title>-edges.csv        : per-edge velocity and displacement
 *   <title>-session.xml      : full TrackMate session (reload with Plugins > Tracking > Load a TrackMate file)
 *   Log window               : summary statistics
 *
 * REQUIREMENTS:
 *   Fiji with TrackMate (included in core Fiji — no extra update site needed)
 *
 * PARAMETERS TO ADJUST (see section below):
 *   DETECTOR_RADIUS         — expected object radius in physical units (µm or px)
 *   QUALITY_THRESHOLD       — minimum quality to keep a detected spot
 *   LINKING_MAX_DISTANCE    — max distance (physical) for frame-to-frame linking
 *   GAP_CLOSING             — enable/disable gap closing for missed detections
 *   GAP_MAX_DISTANCE        — max distance for gap-closing links
 *   MAX_FRAME_GAP           — max number of frames a gap can span
 *   MIN_TRACK_SPOTS         — minimum spots per track (removes stub tracks)
 *   ALLOW_SPLITS            — enable split events (cell divisions) — uses full LAP tracker
 *   ALLOW_MERGES            — enable merge events — uses full LAP tracker
 *   TARGET_CHANNEL          — channel index to detect on (1-based)
 *   SHOW_OVERLAY            — render track overlay on the image after tracking
 *   SWAP_Z_T               — swap Z and T dimensions if image loaded as Z-stack
 */

// ── Imports ────────────────────────────────────────────────────────────────────
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.SelectionModel

import fiji.plugin.trackmate.detection.LogDetectorFactory

import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.LAPUtils

import fiji.plugin.trackmate.features.FeatureFilter
import fiji.plugin.trackmate.visualization.hyperstack.HyperStackDisplayer

import fiji.plugin.trackmate.io.TmXmlWriter
import fiji.plugin.trackmate.io.TmXmlReader
import fiji.plugin.trackmate.visualization.table.TrackTableView
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.io.FileInfo
import ij.io.FileSaver

import java.io.File
import java.io.FileWriter
import java.io.PrintWriter

// ─────────────────────────────────────────────────────────────────────────────
//  PARAMETERS  ← adjust for your data
// ─────────────────────────────────────────────────────────────────────────────

// Detector parameters
int    TARGET_CHANNEL           = 1         // channel to detect on (1-based); use 1 for single-channel
double DETECTOR_RADIUS          = 2.5       // expected object radius in physical units (µm or px if uncalibrated)
                                            // set this to match your object size — inspect image first
double QUALITY_THRESHOLD        = 30.0      // spots below this quality are discarded
                                            // set to 0 to keep all, then decide after seeing the distribution
boolean DO_SUBPIXEL             = true      // sub-pixel localisation (recommended: true)
boolean DO_MEDIAN               = false     // apply 3×3 median pre-filter (helps with speckle noise)

// Tracker parameters
double LINKING_MAX_DISTANCE     = 10.0      // max distance for frame-to-frame linking (same physical units)
                                            // estimate: measure typical displacement between frames × 1.5
boolean GAP_CLOSING             = true      // enable gap closing (bridging missed detections)
double  GAP_MAX_DISTANCE        = 10.0      // max distance for gap-closing links
int     MAX_FRAME_GAP           = 2         // max number of frames a gap can span

boolean ALLOW_SPLITS            = false     // enable split events (cell division) — activates full LAP tracker
double  SPLITTING_MAX_DISTANCE  = 10.0      // max distance for splitting links
boolean ALLOW_MERGES            = false     // enable merge events — activates full LAP tracker
double  MERGING_MAX_DISTANCE    = 10.0      // max distance for merging links

// Track filter
int MIN_TRACK_SPOTS             = 3         // remove tracks with fewer spots (stub tracks from noise)

// Output and display
boolean SHOW_OVERLAY            = true      // render track overlay on the image
boolean SWAP_Z_T               = false      // additional forced swap flag (normally auto-handled below)

// Hardcoded project IO
final String PROJECT_OUTPUT_DIR = '/app/data/projects/trackmate_groovy_workflow_test/data/'
final String FORCED_TITLE       = 'trackmate_sample_project_local'
final String SAMPLE_URL         = 'https://imagej.net/images/trackmate/FakeTracks.tif'
final String SAMPLE_CACHE_PATH  = '/app/data/projects/trackmate_groovy_workflow_test/raw_images/FakeTracks.tif'

// ─────────────────────────────────────────────────────────────────────────────

// ── 0. IO/sample handling and image preparation ───────────────────────────────
ImagePlus sourceImp = null
try {
    sourceImp = WindowManager.getImage(FORCED_TITLE)
} catch (Exception ignored) {
    sourceImp = null
}

if (sourceImp == null) {
    try {
        sourceImp = IJ.getImage()
    } catch (Exception ignored) {
        sourceImp = null
    }
}

if (sourceImp == null) {
    File cacheFile = new File(SAMPLE_CACHE_PATH)
    File cacheParent = cacheFile.getParentFile()
    if (cacheParent != null && !cacheParent.exists()) cacheParent.mkdirs()

    // 1) Try local cache first.
    if (cacheFile.exists() && cacheFile.isFile()) {
        IJ.log('[Setup] No image open. Opening cached TrackMate sample: ' + cacheFile.getAbsolutePath())
        sourceImp = IJ.openImage(cacheFile.getAbsolutePath())
        if (sourceImp == null) {
            IJ.log('[Setup] WARNING: Cache exists but could not be opened: ' + cacheFile.getAbsolutePath())
        }
    }

    // 2) If cache missing/unreadable, try URL and cache it on success.
    if (sourceImp == null) {
        IJ.log('[Setup] No usable cache. Opening TrackMate sample from URL: ' + SAMPLE_URL)
        println('[Setup] No image open. Opening TrackMate sample from URL.')
        sourceImp = IJ.openImage(SAMPLE_URL)
        if (sourceImp != null) {
            try {
                boolean cacheSaved = new FileSaver(sourceImp).saveAsTiff(cacheFile.getAbsolutePath())
                if (cacheSaved) {
                    IJ.log('[Setup] Cached sample image at: ' + cacheFile.getAbsolutePath())
                } else {
                    IJ.log('[Setup] WARNING: URL sample opened, but cache save failed: ' + cacheFile.getAbsolutePath())
                }
            } catch (Exception e) {
                IJ.log('[Setup] WARNING: URL sample opened, but cache save threw error: ' + e.getMessage())
            }
        }
    }

    // 3) If URL fails, try Fiji built-in sample command (if available).
    if (sourceImp == null) {
        IJ.log('[Setup] URL open failed. Trying built-in sample loader: Tracks for TrackMate (807K)')
        int beforeCount = WindowManager.getImageCount()
        try {
            IJ.run('Tracks for TrackMate (807K)')
        } catch (Exception ignored) {
            // Keep null and try alternate built-in command below.
        }
        int afterCount = WindowManager.getImageCount()

        // Optional robustness: fallback command name used by some installations.
        if (afterCount <= beforeCount) {
            IJ.log('[Setup] Primary built-in sample command did not open an image. Trying: Tracks for TrackMate')
            beforeCount = afterCount
            try {
                IJ.run('Tracks for TrackMate')
            } catch (Exception ignored) {
                // Keep null and report below.
            }
            afterCount = WindowManager.getImageCount()
        }

        if (afterCount > beforeCount) {
            sourceImp = WindowManager.getCurrentImage()
            if (sourceImp != null) {
                IJ.log('[Setup] Built-in sample loader succeeded.')
                // Cache this built-in sample for future offline runs.
                try {
                    boolean cacheSaved = new FileSaver(sourceImp).saveAsTiff(cacheFile.getAbsolutePath())
                    if (cacheSaved) {
                        IJ.log('[Setup] Cached built-in sample at: ' + cacheFile.getAbsolutePath())
                    } else {
                        IJ.log('[Setup] WARNING: Built-in sample opened, but cache save failed: ' + cacheFile.getAbsolutePath())
                    }
                } catch (Exception e) {
                    IJ.log('[Setup] WARNING: Built-in sample opened, but cache save threw error: ' + e.getMessage())
                }
            }
        }
    }

    if (sourceImp == null) {
        IJ.log('[Setup] ERROR: Could not open TrackMate sample from cache, URL, or built-in loader.')
        println('FAILURE: Could not open TrackMate sample image (cache+URL+built-in failed).')
        return
    }

    sourceImp.show()
}

// NEVER alter original image: work on duplicate
ImagePlus imp = sourceImp.duplicate()
if (imp == null) {
    IJ.log('[Setup] ERROR: Could not duplicate source image.')
    println('FAILURE: Image duplication failed.')
    return
}
imp.setCalibration(sourceImp.getCalibration())
imp.setTitle(FORCED_TITLE)
imp.show()

// Ensure timelapse dimensions are valid (auto Z/T reassignment + optional forced swap)
int c = imp.getNChannels()
int z = imp.getNSlices()
int t = imp.getNFrames()
if (t == 1 && z > 1) {
    IJ.log('[Setup] Auto-fixing Z/T confusion: slices=' + z + ' -> frames=' + z)
    imp.setDimensions(c, 1, z)
    imp.setOpenAsHyperStack(true)
}
if (SWAP_Z_T) {
    int[] dims = imp.getDimensions() // [w,h,c,z,t]
    IJ.log('[Setup] SWAP_Z_T enabled. Swapping Z and T: slices=' + dims[3] + ' frames=' + dims[4])
    imp.setDimensions(dims[2], dims[4], dims[3])
    imp.setOpenAsHyperStack(true)
}

// Force output directory
File outDir = new File(PROJECT_OUTPUT_DIR)
if (!outDir.exists()) outDir.mkdirs()
if (!outDir.exists() || !outDir.isDirectory()) {
    IJ.log('[Setup] ERROR: Could not create output directory: ' + PROJECT_OUTPUT_DIR)
    println('FAILURE: Cannot create output directory.')
    return
}
String saveDir = outDir.getAbsolutePath() + File.separator

// Ensure ImagePlus file info points to project-local output directory
FileInfo fi = imp.getOriginalFileInfo()
if (fi == null) fi = new FileInfo()
fi.directory = saveDir
fi.fileName = FORCED_TITLE + '.tif'
imp.setFileInfo(fi)

try {
    if (imp.getWindow() != null) {
        WindowManager.setCurrentWindow(imp.getWindow())
        IJ.selectWindow(imp.getTitle())
    }
} catch (Exception e) {
    IJ.log('[Setup] WARNING: Could not force active window focus: ' + e.getMessage())
}

String title = imp.getTitle().replaceAll(/\.[^.]+$/, '')

IJ.log('═══════════════════════════════════════════════')
IJ.log(' TrackMate Tracking Workflow — Groovy script')
IJ.log(' Image  : ' + imp.getTitle())
IJ.log(' Frames : ' + imp.getNFrames() + '   Slices: ' + imp.getNSlices())
IJ.log(' Detector radius: ' + DETECTOR_RADIUS + '   Linking dist: ' + LINKING_MAX_DISTANCE)
IJ.log(' Output dir (forced): ' + saveDir)
IJ.log('═══════════════════════════════════════════════')
println('[Setup] Active image: ' + imp.getTitle())
println('[Setup] Output dir: ' + saveDir)

// Validate: need more than 1 frame
if (imp.getNFrames() <= 1) {
    IJ.log('[Setup] ERROR: Image has only 1 frame after Z/T checks.')
    IJ.error('Image has only 1 time frame. TrackMate needs a timelapse.')
    println('FAILURE: Input is not a timelapse.')
    return
}

// ── 1. Create the Model ────────────────────────────────────────────────────────
// Model is the data container. It starts empty; TrackMate.process() fills it.
def model = new Model()
model.setLogger(Logger.IJ_LOGGER)

// ── 2. Create and configure Settings ──────────────────────────────────────────
def settings = new Settings(imp)

// ── 3. Configure the LoG detector ─────────────────────────────────────────────
settings.detectorFactory = new LogDetectorFactory()
settings.detectorSettings = [
    'TARGET_CHANNEL'           : (TARGET_CHANNEL as int),
    'RADIUS'                   : (DETECTOR_RADIUS as double),
    'THRESHOLD'                : (0.0d as double),           // detect everything first; quality filter below
    'DO_SUBPIXEL_LOCALIZATION' : (DO_SUBPIXEL as boolean),
    'DO_MEDIAN_FILTERING'      : (DO_MEDIAN as boolean),
]

// Set initial quality filter threshold — discards obvious noise before feature computation
// This avoids computing features on thousands of trash spots (important for performance)
settings.initialSpotFilterValue = (1.0d as double)           // discard spots below quality 1

// ── 4. Add feature analyzers ──────────────────────────────────────────────────
// In scripting, analyzers must be added explicitly.
// addAllAnalyzers() adds all known spot, edge, and track analyzers.
// This is the safe default; it computes everything but is slightly slower.
settings.addAllAnalyzers()

// ── 5. Add spot quality filter ────────────────────────────────────────────────
// FeatureFilter(featureKey, threshold, isAbove)
// isAbove = true → keep spots where feature > threshold
settings.addSpotFilter(new FeatureFilter('QUALITY', QUALITY_THRESHOLD, true))

// ── 6. Configure the tracker ──────────────────────────────────────────────────
if (ALLOW_SPLITS || ALLOW_MERGES) {
    // Full LAP tracker — supports splits and merges
    IJ.log('[Tracker] Using full SparseLAPTracker (splits=' + ALLOW_SPLITS + ' merges=' + ALLOW_MERGES + ')')
    settings.trackerFactory = new SparseLAPTrackerFactory()
    settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
    settings.trackerSettings['LINKING_MAX_DISTANCE']     = (LINKING_MAX_DISTANCE as double)
    settings.trackerSettings['ALLOW_GAP_CLOSING']        = (GAP_CLOSING as boolean)
    settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = (GAP_MAX_DISTANCE as double)
    settings.trackerSettings['MAX_FRAME_GAP']            = (MAX_FRAME_GAP as int)
    settings.trackerSettings['ALLOW_TRACK_SPLITTING']    = (ALLOW_SPLITS as boolean)
    settings.trackerSettings['SPLITTING_MAX_DISTANCE']   = (SPLITTING_MAX_DISTANCE as double)
    settings.trackerSettings['ALLOW_TRACK_MERGING']      = (ALLOW_MERGES as boolean)
    settings.trackerSettings['MERGING_MAX_DISTANCE']     = (MERGING_MAX_DISTANCE as double)
} else {
    // Simple LAP tracker — Brownian motion, no splits/merges
    IJ.log('[Tracker] Using SimpleSparseLAPTracker')
    settings.trackerFactory = new SimpleSparseLAPTrackerFactory()
    settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
    settings.trackerSettings['LINKING_MAX_DISTANCE']     = (LINKING_MAX_DISTANCE as double)
    settings.trackerSettings['ALLOW_GAP_CLOSING']        = (GAP_CLOSING as boolean)
    settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = (GAP_MAX_DISTANCE as double)
    settings.trackerSettings['MAX_FRAME_GAP']            = (MAX_FRAME_GAP as int)
}

// ── 7. Add track filter ───────────────────────────────────────────────────────
// Remove very short tracks (usually noise or false detections)
settings.addTrackFilter(new FeatureFilter('NUMBER_SPOTS', MIN_TRACK_SPOTS as double, true))

// ── 8. Run TrackMate ──────────────────────────────────────────────────────────
IJ.log('[TrackMate] Running detection and tracking...')
def trackmate = new TrackMate(model, settings)

// checkInput() validates configuration before running anything
if (!trackmate.checkInput()) {
    IJ.error('Configuration error: ' + trackmate.getErrorMessage())
    println('FAILURE: TrackMate configuration error.')
    return
}

// process() runs: detection → initial filter → feature computation → spot filter → tracking → track filter
if (!trackmate.process()) {
    IJ.error('Processing error: ' + trackmate.getErrorMessage())
    println('FAILURE: TrackMate processing error.')
    return
}

IJ.log('[TrackMate] Processing complete.')

// ── 9. Summary statistics ─────────────────────────────────────────────────────
def tm = model.getTrackModel()
def fm = model.getFeatureModel()
def trackIDs = tm.trackIDs(true)   // true = only filtered (visible) tracks

int totalSpots = 0
double totalMeanSpeed = 0.0

for (def id in trackIDs) {
    totalSpots += tm.trackSpots(id).size()
    def speed = fm.getTrackFeature(id, 'TRACK_MEAN_SPEED')
    if (speed != null) totalMeanSpeed += speed
}

double avgMeanSpeed = trackIDs.size() > 0 ? totalMeanSpeed / trackIDs.size() : 0.0

IJ.log('─── RESULTS ──────────────────────────────────')
IJ.log(' Total visible tracks : ' + trackIDs.size())
IJ.log(' Total spots tracked  : ' + totalSpots)
IJ.log(' Avg track mean speed : ' + String.format('%.3f', avgMeanSpeed) +
       ' ' + model.getSpaceUnits() + '/' + model.getTimeUnits())
IJ.log('──────────────────────────────────────────────')

// ── 10. Export results to CSV ─────────────────────────────────────────────────
IJ.log('[Export] Writing CSV files...')
boolean exportedTrackCsv = false
try {
    def sm = new SelectionModel(model)
    def ds = DisplaySettings.defaultStyle()
    def tableView = new TrackTableView(model, sm, ds)

    // Spot table: one row per detected spot
    def spotsFile = new File(saveDir + title + '-spots.csv')
    tableView.getSpotTable().exportToCsv(spotsFile)
    IJ.log('[Export] Spots: ' + spotsFile.getAbsolutePath())

    // Track table: one row per track
    def tracksFile = new File(saveDir + title + '-tracks.csv')
    tableView.getTrackTable().exportToCsv(tracksFile)
    IJ.log('[Export] Tracks: ' + tracksFile.getAbsolutePath())
    exportedTrackCsv = tracksFile.exists()

} catch (Exception e) {
    IJ.log('[Export] WARNING: TrackTableView export failed: ' + e.getMessage())
    IJ.log('[Export] Falling back to manual CSV export...')

    // Fallback: manual CSV for spots and tracks
    try {
        def spotsCsvFile = new File(saveDir + title + '-spots-manual.csv')
        def pwSpots = new PrintWriter(new FileWriter(spotsCsvFile))
        pwSpots.println('TRACK_ID,SPOT_ID,FRAME,X,Y,Z,QUALITY,MEAN_INTENSITY')
        for (def id in trackIDs) {
            for (def spot in tm.trackSpots(id)) {
                pwSpots.println(id + ',' +
                    spot.ID() + ',' +
                    spot.getFeature('FRAME').intValue() + ',' +
                    String.format('%.4f', spot.getFeature('POSITION_X')) + ',' +
                    String.format('%.4f', spot.getFeature('POSITION_Y')) + ',' +
                    String.format('%.4f', spot.getFeature('POSITION_Z')) + ',' +
                    String.format('%.4f', spot.getFeature('QUALITY')) + ',' +
                    String.format('%.4f', spot.getFeature('MEAN_INTENSITY')))
            }
        }
        pwSpots.close()
        IJ.log('[Export] Fallback spots CSV: ' + spotsCsvFile.getAbsolutePath())

        def tracksCsvFile = new File(saveDir + title + '-tracks-manual.csv')
        def pwTracks = new PrintWriter(new FileWriter(tracksCsvFile))
        pwTracks.println('TRACK_ID,NUMBER_SPOTS,TRACK_DURATION,TRACK_DISPLACEMENT,TRACK_MEAN_SPEED')
        for (def id in trackIDs) {
            def nSpots = fm.getTrackFeature(id, 'NUMBER_SPOTS')
            def duration = fm.getTrackFeature(id, 'TRACK_DURATION')
            def disp = fm.getTrackFeature(id, 'TRACK_DISPLACEMENT')
            def meanSpeed = fm.getTrackFeature(id, 'TRACK_MEAN_SPEED')
            pwTracks.println(id + ',' +
                (nSpots != null ? String.format('%.0f', nSpots) : '') + ',' +
                (duration != null ? String.format('%.6f', duration) : '') + ',' +
                (disp != null ? String.format('%.6f', disp) : '') + ',' +
                (meanSpeed != null ? String.format('%.6f', meanSpeed) : ''))
        }
        pwTracks.close()
        IJ.log('[Export] Fallback tracks CSV: ' + tracksCsvFile.getAbsolutePath())

    } catch (Exception e2) {
        IJ.log('[Export] WARNING: Manual CSV export also failed: ' + e2.getMessage())
    }
}

// ── 11. Save XML session ──────────────────────────────────────────────────────
File xmlFile = new File(saveDir + title + '-session.xml')
try {
    def writer = new TmXmlWriter(xmlFile, Logger.IJ_LOGGER)
    writer.appendLog('Written by GROOVY_WORKFLOW_PARTICLE_TRACKING.groovy')
    writer.appendModel(model)
    writer.appendSettings(settings)
    writer.writeToFile()
    IJ.log('[Session] XML saved: ' + xmlFile.getAbsolutePath())
} catch (Exception e) {
    IJ.log('[Session] WARNING: Could not save XML: ' + e.getMessage())
}

// ── 12. Load saved session and display tracks overlay ─────────────────────────
if (SHOW_OVERLAY) {
    IJ.log('[Display] Loading saved TrackMate session for overlay rendering...')
    try {
        if (!xmlFile.exists() || !xmlFile.isFile()) {
            IJ.log('[Display] WARNING: XML file missing, cannot reload session: ' + xmlFile.getAbsolutePath())
        } else {
            def reader = new TmXmlReader(xmlFile)
            if (!reader.isReadingOk()) {
                IJ.log('[Display] WARNING: XML read failed: ' + reader.getErrorMessage())
            } else {
                def loadedModel = reader.getModel()
                if (loadedModel == null) {
                    IJ.log('[Display] WARNING: XML loaded model is null.')
                } else {
                    def sm = new SelectionModel(loadedModel)
                    def ds = DisplaySettings.defaultStyle()
                    def displayer = new HyperStackDisplayer(loadedModel, sm, imp, ds)
                    displayer.render()
                    displayer.refresh()
                    IJ.log('[Display] Overlay rendered from loaded session.')
                }
            }
        }
    } catch (Exception e) {
        IJ.log('[Display] WARNING: Could not render overlay: ' + e.getMessage())
    }
}

// ── Summary ────────────────────────────────────────────────────────────────────
IJ.log('═══════════════════════════════════════════════')
IJ.log(' TRACKING COMPLETE')
IJ.log(' Tracks        : ' + trackIDs.size())
IJ.log(' Spots tracked : ' + totalSpots)
IJ.log(' Avg speed     : ' + String.format('%.3f', avgMeanSpeed) +
       ' ' + model.getSpaceUnits() + '/' + model.getTimeUnits())
IJ.log(' Output dir    : ' + saveDir)
IJ.log('═══════════════════════════════════════════════')

println('SUCCESS: TrackMate workflow completed. Session XML: ' + xmlFile.getAbsolutePath())
imp.show()
