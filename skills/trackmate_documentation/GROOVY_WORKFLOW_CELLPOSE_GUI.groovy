/*
 * 04_run_track_and_visualize_gui.groovy
 *
 * PURPOSE
 * - Run a complete TrackMate + Cellpose tracking workflow in Fiji GUI mode on a time-lapse movie.
 * - Detect cells with TrackMate-Cellpose, link detections into tracks, export results,
 *   capture Cellpose mask images, rebuild them into a label-stack TIFF, and display track overlays.
 *
 * REQUIRED FIJI PLUGINS
 * - TrackMate
 * - TrackMate-Cellpose extension
 *
 * INPUT MOVIE (hardcoded)
 * - /app/data/projects/cell_tracking_test/raw_images/P31-crop.tif
 *
 * OUTPUTS (hardcoded)
 * - CSV tracks table:
 *   /app/data/projects/cell_tracking_test/data/tracks_cellpose_cyto3.csv
 * - TrackMate XML session:
 *   /app/data/projects/cell_tracking_test/data/session_cellpose_cyto3.xml
 * - Copied Cellpose mask PNG folder:
 *   /app/data/projects/cell_tracking_test/processed_images/cellpose_temp_exports_cyto3/
 * - Reconstructed label-stack TIFF:
 *   /app/data/projects/cell_tracking_test/processed_images/cellpose_labels_cyto3.tif
 *
 * KEY PARAMETERS
 * - Cellpose model: cyto3
 * - GPU usage: true
 * - Cell diameter guess: 30 px (explicit guess; no auto-estimation in this script)
 * - Linking distance: 40 px
 * - Gap-closing distance: 40 px
 * - Max frame gap: 2
 * - Minimum track length filter: 3 spots
 *
 * HOW TO RUN (Fiji GUI)
 * 1) Open Fiji.
 * 2) Run this Groovy script (Script Editor -> Run).
 * 3) The script opens the hardcoded movie path, runs TrackMate processing,
 *    writes CSV/XML, and shows HyperStack + TrackScheme visualizations if successful.
 *
 * TROUBLESHOOTING
 * - "Input movie missing": verify the hardcoded image path exists.
 * - Cellpose launch issues: verify TrackMate-Cellpose is installed and Python path is valid
 *   (/opt/conda/envs/cellpose/bin/python in this script).
 * - No tracks produced: check image contrast/segmentation settings (diameter/model/channels)
 *   and tracker distances.
 * - TrackScheme not displayed: this can be optional; overlay display may still work.
 */

import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.SelectionModel
import fiji.plugin.trackmate.SpotCollection
import fiji.plugin.trackmate.cellpose.CellposeDetectorFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.features.FeatureFilter
import fiji.plugin.trackmate.io.TmXmlWriter
import fiji.plugin.trackmate.visualization.hyperstack.HyperStackDisplayer
import fiji.plugin.trackmate.visualization.trackscheme.TrackScheme
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings
import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.ImageStack
import ij.process.ImageProcessor
import ij.process.ShortProcessor
import java.io.File
import java.io.FileWriter
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.regex.Pattern

// ── PARAMETERS (hardcoded workflow configuration) ───────────────────────────
def imagePath           = '/app/data/projects/cell_tracking_test/raw_images/P31-crop.tif'
def imageName           = ''
def targetChannel       = '1'
def optionalChannel     = '0'
def cellDiameter        = 30.0d
def cellposeModel       = 'cyto3'
def customModelPath     = ''
def useGpu              = true
def simplifyContours    = true

def linkingDist          = 40.0d
def gapClosingDist      = 40.0d
def maxFrameGap         = Integer.valueOf(2)
def minTrackLength      = 3.0d

final String outputDirPath       = '/app/data/projects/cell_tracking_test/data/'
final String csvPath             = '/app/data/projects/cell_tracking_test/data/tracks_cellpose_cyto3.csv'
final String xmlPath             = '/app/data/projects/cell_tracking_test/data/session_cellpose_cyto3.xml'
final String tempRootPath        = '/tmp'
final String tempPrefix          = 'TrackMate-cellpose_'
final String exportDirPath       = '/app/data/projects/cell_tracking_test/processed_images/cellpose_temp_exports_cyto3/'
final String outputLabelTiffPath = '/app/data/projects/cell_tracking_test/processed_images/cellpose_labels_cyto3.tif'

boolean overallSuccess = false
boolean workflowSuccess = false

try {
    IJ.log('[INFO] Starting TrackMate-Cellpose GUI workflow...')

    // ── IO: open input image safely (path -> named image fallback -> active image) ──
    ImagePlus imp = null

    File inFile = new File(imagePath)
    if (!inFile.exists()) {
        IJ.log('[ERROR] Input movie not found: ' + imagePath)
        println('FINAL STATUS: FAILURE - Input movie missing.')
        return
    }
    imp = IJ.openImage(imagePath)

    if (imp == null && imageName != null && !imageName.isEmpty()) {
        imp = WindowManager.getImage(imageName)
        if (imp == null) IJ.log("[WARN] Image '${imageName}' not found. Falling back to active image.")
    }
    if (imp == null) {
        try { imp = IJ.getImage() } catch (Exception ignored) { imp = null }
    }
    if (imp == null) {
        IJ.log('[ERROR] No image available. Aborting.')
        println('FINAL STATUS: FAILURE - No image open.')
        return
    }

    // Work on a duplicate to preserve the originally opened image.
    def imp2 = imp.duplicate()
    imp2.setTitle('P31-crop_trackmate_cellpose_cyto3')

    IJ.log('[INFO] Processing image: ' + imp.getTitle())
    IJ.log('[INFO] Dimensions: ' + imp.getWidth() + 'x' + imp.getHeight() + ', C=' + imp.getNChannels() + ', Z=' + imp.getNSlices() + ', T=' + imp.getNFrames())

    // If the movie was loaded as a Z stack instead of T series, reinterpret Z as time.
    if (imp2.getNFrames() == 1 && imp2.getNSlices() > 1) {
        IJ.log('[WARN] Detected Z>1 and T=1; reclassifying slices as frames for tracking.')
        imp2.setDimensions(imp2.getNChannels(), 1, imp2.getNSlices())
    }

    IJ.log('[INFO] Cell diameter auto not explicitly supported in this script; using guess CELL_DIAMETER=30.0')

    // Timestamp used later to find recent TrackMate-Cellpose temp exports.
    long startTs = System.currentTimeMillis()

    // ── TrackMate model/settings core objects ─────────────────────────────────
    def model = new Model()
    model.setLogger(Logger.IJ_LOGGER)
    def settings = new Settings(imp2)

    // ── Detector setup: TrackMate-Cellpose ────────────────────────────────────
    def cellposePath = '/opt/conda/envs/cellpose/bin/python'
    def cellposeEnvName = 'cellpose'

    settings.detectorFactory = new CellposeDetectorFactory()
    settings.detectorSettings = [
        'CELLPOSE_PYTHON_FILEPATH'       : cellposePath,
        'CELLPOSE_MODEL_NAME'            : cellposeEnvName,
        'CELLPOSE_MODEL'                 : cellposeModel,
        'CELLPOSE_CUSTOM_MODEL_FILEPATH' : customModelPath,
        'TARGET_CHANNEL'                 : targetChannel,
        'OPTIONAL_CHANNEL_2'             : optionalChannel,
        'CELL_DIAMETER'                  : (double) cellDiameter,
        'USE_GPU'                        : useGpu,
        'SIMPLIFY_CONTOURS'              : simplifyContours,
        'CELLPROB_THRESHOLD'             : 0.0d,
        'FLOW_THRESHOLD'                 : 0.4d,
    ]

    settings.initialSpotFilterValue = 0.0d
    settings.addAllAnalyzers()

    // ── Tracker setup: Sparse LAP linking + track length filter ───────────────
    settings.trackerFactory = new SparseLAPTrackerFactory()
    settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
    settings.trackerSettings['LINKING_MAX_DISTANCE'] = (double) linkingDist
    settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = (double) gapClosingDist
    settings.trackerSettings['MAX_FRAME_GAP'] = (int) maxFrameGap
    settings.addTrackFilter(new FeatureFilter('NUMBER_SPOTS', (double) minTrackLength, true))

    // ── Running TrackMate (checkInput -> process) ─────────────────────────────
    def trackmate = new TrackMate(model, settings)
    IJ.log('[INFO] Checking TrackMate input...')
    if (!trackmate.checkInput()) {
        IJ.log('[ERROR] checkInput failed: ' + trackmate.getErrorMessage())
    } else {
        IJ.log('[INFO] Running TrackMate process()...')
        if (!trackmate.process()) {
            IJ.log('[ERROR] process() failed: ' + trackmate.getErrorMessage())
        } else {
            workflowSuccess = true
            IJ.log('[INFO] TrackMate process completed.')
        }
    }

    IJ.log('[INFO] Total spots: ' + model.getSpots().getNSpots(true))
    IJ.log('[INFO] Total tracks (filtered): ' + model.getTrackModel().nTracks(true))
    IJ.log('[INFO] Total tracks (all): ' + model.getTrackModel().nTracks(false))

    // ── Exports: ensure output directory exists ────────────────────────────────
    new File(outputDirPath).mkdirs()

    // ── Exports: CSV spot/track table ─────────────────────────────────────────
    try {
        File csvFile = new File(csvPath)
        FileWriter writer = new FileWriter(csvFile)
        try {
            writer.write('TRACK_ID,FRAME,POSITION_X,POSITION_Y,POSITION_Z,RADIUS,QUALITY,MEAN_INTENSITY\n')
            int rows = 0
            if (workflowSuccess) {
                int nTracksAll = model.getTrackModel().nTracks(false)
                if (nTracksAll == 0) {
                    // No tracks: still export per-frame spots with TRACK_ID=-1.
                    SpotCollection allSpots = model.getSpots()
                    for (int frame = 0; frame < imp2.getNFrames(); frame++) {
                        def spotsAtFrame = allSpots.iterable(frame, true)
                        for (def spot in spotsAtFrame) {
                            double x = spot.getFeature('POSITION_X')
                            double y = spot.getFeature('POSITION_Y')
                            double z = (spot.getFeature('POSITION_Z') == null) ? 0.0d : spot.getFeature('POSITION_Z')
                            double r = spot.getFeature('RADIUS')
                            double q = spot.getFeature('QUALITY')
                            double mi = (spot.getFeature('MEAN_INTENSITY') == null) ? 0.0d : spot.getFeature('MEAN_INTENSITY')
                            writer.write("-1,${frame},${x},${y},${z},${r},${q},${mi}\n")
                            rows++
                        }
                    }
                } else {
                    // Tracks present: export all spots sorted by frame within each track.
                    for (def trackId in model.getTrackModel().trackIDs(true)) {
                        def spots = new ArrayList(model.getTrackModel().trackSpots(trackId))
                        spots.sort { a, b -> a.getFeature('FRAME') <=> b.getFeature('FRAME') }
                        for (def spot in spots) {
                            int frame = spot.getFeature('FRAME').intValue()
                            double x = spot.getFeature('POSITION_X')
                            double y = spot.getFeature('POSITION_Y')
                            double z = (spot.getFeature('POSITION_Z') == null) ? 0.0d : spot.getFeature('POSITION_Z')
                            double r = spot.getFeature('RADIUS')
                            double q = spot.getFeature('QUALITY')
                            double mi = (spot.getFeature('MEAN_INTENSITY') == null) ? 0.0d : spot.getFeature('MEAN_INTENSITY')
                            writer.write("${trackId},${frame},${x},${y},${z},${r},${q},${mi}\n")
                            rows++
                        }
                    }
                }
            }
            IJ.log('[INFO] CSV written: ' + csvFile.getAbsolutePath() + ' (rows=' + rows + ')')
        } finally {
            try { writer.flush() } catch (Exception ignored) {}
            try { writer.close() } catch (Exception ignored) {}
        }
    } catch (Exception e) {
        IJ.log('[ERROR] CSV export failed: ' + e.getMessage())
    }

    // ── Exports: TrackMate XML session ────────────────────────────────────────
    try {
        File xmlFile = new File(xmlPath)
        def xmlWriter = new TmXmlWriter(xmlFile, Logger.IJ_LOGGER)
        xmlWriter.appendModel(model)
        xmlWriter.appendSettings(settings)
        xmlWriter.writeToFile()
        IJ.log('[INFO] XML written: ' + xmlFile.getAbsolutePath())
    } catch (Exception e) {
        IJ.log('[ERROR] XML export failed: ' + e.getMessage())
    }

    // ── Mask capture: find TrackMate-Cellpose temp folder and copy mask PNGs ─
    File tempRoot = new File(tempRootPath)
    if (tempRoot.exists() && tempRoot.isDirectory()) {
        File[] candidates = tempRoot.listFiles()
        if (candidates == null) candidates = new File[0]
        List<File> cpDirs = candidates.findAll { File f -> f != null && f.isDirectory() && f.getName().startsWith(tempPrefix) }
        if (!cpDirs.isEmpty()) {
            List<File> recent = cpDirs.findAll { it.lastModified() >= (startTs - 5000L) }
            List<File> pool = recent.isEmpty() ? cpDirs : recent
            pool.sort { a, b -> a.lastModified() <=> b.lastModified() }
            File selectedTempDir = pool.last()

            File exportDir = new File(exportDirPath)
            if (!exportDir.exists()) exportDir.mkdirs()

            File[] tempFilesArr = selectedTempDir.listFiles()
            if (tempFilesArr == null) tempFilesArr = new File[0]
            List<File> tempFiles = tempFilesArr.toList()

            Pattern p1 = Pattern.compile('.*_cp_masks\\.png$', Pattern.CASE_INSENSITIVE)
            List<File> filesToCopy = tempFiles.findAll { File f -> f != null && f.isFile() && p1.matcher(f.getName()).matches() }

            List<File> copiedFiles = []
            for (File src : filesToCopy) {
                try {
                    File dst = new File(exportDir, src.getName())
                    Files.copy(src.toPath(), dst.toPath(), StandardCopyOption.REPLACE_EXISTING)
                    copiedFiles << dst
                } catch (Exception ignored) {}
            }

            // ── Mask reconstruction: PNG masks -> 16-bit label-stack TIFF ─────
            if (!copiedFiles.isEmpty()) {
                copiedFiles.sort { File a, File b ->
                    int ia = extractLeadingIndex(a.getName())
                    int ib = extractLeadingIndex(b.getName())
                    if (ia != ib) return ia <=> ib
                    return a.getName() <=> b.getName()
                }

                ImageStack outStack = null
                int outW = -1
                int outH = -1

                for (File mf : copiedFiles) {
                    ImagePlus mImp = IJ.openImage(mf.getAbsolutePath())
                    if (mImp == null) continue
                    ImageProcessor ip = mImp.getProcessor()
                    if (ip == null) { mImp.close(); continue }

                    if (mImp.getBitDepth() == 24 || mImp.getNChannels() > 1) {
                        IJ.run(mImp, '8-bit', '')
                        ip = mImp.getProcessor()
                    }

                    int w = ip.getWidth()
                    int h = ip.getHeight()
                    short[] pix16 = new short[w * h]
                    for (int y = 0; y < h; y++) {
                        int row = y * w
                        for (int x = 0; x < w; x++) {
                            int v = (int)Math.round(ip.getf(x, y))
                            if (v < 0) v = 0
                            if (v > 65535) v = 65535
                            pix16[row + x] = (short)(v & 0xFFFF)
                        }
                    }

                    ShortProcessor sp = new ShortProcessor(w, h, pix16, null)
                    if (outStack == null) { outW = w; outH = h; outStack = new ImageStack(w, h) }
                    if (w == outW && h == outH) outStack.addSlice(mf.getName(), sp)
                    mImp.close()
                }

                if (outStack != null && outStack.getSize() > 0) {
                    ImagePlus outImp = new ImagePlus('cellpose_labels_cyto3', outStack)
                    File outFile = new File(outputLabelTiffPath)
                    if (outFile.getParentFile() != null && !outFile.getParentFile().exists()) outFile.getParentFile().mkdirs()
                    IJ.saveAsTiff(outImp, outFile.getAbsolutePath())
                    outImp.close()
                }
            }
        }
    }

    // ── Visualization (GUI): HyperStack overlay + TrackScheme ────────────────
    if (workflowSuccess) {
        IJ.log('[INFO] Creating TrackMate GUI visualizations (overlay + TrackScheme)...')
        imp2.show()
        def selectionModel = new SelectionModel(model)

        def ds = DisplaySettings.defaultStyle()
        def displayer = new HyperStackDisplayer(model, selectionModel, imp2, ds)
        displayer.render()
        displayer.refresh()
        IJ.log('[INFO] HyperStack overlay displayed.')

        try {
            TrackScheme trackScheme = new TrackScheme(model, selectionModel)
            trackScheme.render()
            IJ.log('[INFO] TrackScheme window displayed.')
        } catch (Exception e) {
            IJ.log('[WARN] TrackScheme unavailable: ' + e.getMessage())
        }

        overallSuccess = true
    } else {
        IJ.log('[WARN] TrackMate workflow unsuccessful; skipping GUI visualizations.')
        imp2.show()
    }

    imp.close()

} catch (Exception e) {
    IJ.log('[ERROR] Unhandled exception: ' + e.getMessage())
    e.printStackTrace()
}

if (overallSuccess) {
    IJ.log('[INFO] Workflow completed successfully.')
    println('FINAL STATUS: SUCCESS')
} else {
    IJ.log('[ERROR] Workflow failed.')
    println('FINAL STATUS: FAILURE')
}

// Utility: parse leading numeric frame index from filenames like "0001_...png".
int extractLeadingIndex(String name) {
    def m = (name =~ /^(\\d+)_/)
    if (m.find()) {
        try { return Integer.parseInt(m.group(1)) } catch (Exception ignored) { return Integer.MAX_VALUE }
    }
    return Integer.MAX_VALUE
}
