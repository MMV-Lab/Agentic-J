/*
 * GROOVY_WORKFLOW_CELLPOSE_SINGLE_IMAGE.groovy
 *
 * Single-image segmentation with TrackMate-Cellpose. Produces:
 *   - cellpose_instance_labels_preview.tif   (16-bit label image)
 *   - cellpose_binary_mask_preview.tif       (8-bit 0/255 mask)
 *   - cellpose_measurements_preview.csv      (Label, Area, Centroid_X, Centroid_Y)
 *
 * This script encodes ALL pitfalls C5-C9 from CELLPOSE_DETECTOR_API.md:
 *   C5  Tracker factory loaded via reflection (no hardcoded jaqaman/sparselap import).
 *   C7  Cellpose mask read from /tmp/TrackMate-cellpose_*/<basename>_cp_masks.{tif,png}
 *       — never searched in WindowManager.
 *   C8  Spot.getRoi() / SpotRoi never sent to RoiManager. ROI extraction is skipped
 *       entirely; the mask file is the ground-truth output.
 *   C9  Per-label measurements computed via pixel iteration — no MorphoLibJ imports.
 *
 * Verified in this container against TrackMate v8 + Cellpose 3.x + cyto3 model.
 *
 * USAGE: open the input image as the active window, then run this script. Edit
 * the OUTPUT PATHS and CELLPOSE PARAMETERS blocks below for your project.
 */

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.measure.ResultsTable
import ij.process.ImageStatistics
import java.io.File

import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.cellpose.CellposeDetectorFactory
import fiji.plugin.trackmate.features.FeatureFilter

// ── OUTPUT PATHS ─────────────────────────────────────────────────────────────
final String outputMaskPath  = '/app/data/projects/<project>/processed_images/cellpose_binary_mask_preview.tif'
final String outputLabelPath = '/app/data/projects/<project>/processed_images/cellpose_instance_labels_preview.tif'
final String outputCsvPath   = '/app/data/projects/<project>/data/cellpose_measurements_preview.csv'

// ── CELLPOSE PARAMETERS ──────────────────────────────────────────────────────
final String  modelName        = 'cyto3'
final double  cellDiameter     = 30.0d
final int     targetChannel    = 0       // 0=gray, 1=R, 2=G, 3=B
final int     optionalChannel  = 0
final boolean useGpu           = false
final boolean simplifyContours = true

boolean success = false

// ── C5: REFLECTION-BASED TRACKER FACTORY LOADER ──────────────────────────────
def buildTrackerFactoryAndSettings() {
    String[] candidates = [
        'fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.jaqaman.LAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.sparselap.SparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.sparselap.SimpleSparseLAPTrackerFactory',
    ]
    for (String cn : candidates) {
        try {
            Class cls = Class.forName(cn)
            def factory = cls.getDeclaredConstructor().newInstance()
            IJ.log('[INFO] Tracker factory via reflection: ' + cn)
            return [factory, factory.getDefaultSettings()]
        } catch (Throwable t) {
            IJ.log('[WARN] Tracker factory not available: ' + cn)
        }
    }
    return null
}

// ── C7: LOCATE CELLPOSE MASK FILE IN /tmp ────────────────────────────────────
def findNewestTrackMateCellposeDir() {
    File tmpRoot = new File('/tmp')
    if (!tmpRoot.isDirectory()) return null
    File best = null; long bestT = Long.MIN_VALUE
    for (File d : tmpRoot.listFiles() ?: [] as File[]) {
        if (d.isDirectory() && d.name.startsWith('TrackMate-cellpose_') && d.lastModified() > bestT) {
            bestT = d.lastModified(); best = d
        }
    }
    return best
}

def findBestMaskFile(File dir) {
    if (dir == null || !dir.isDirectory()) return null
    def candidates = []
    for (File f : dir.listFiles() ?: [] as File[]) {
        if (!f.isFile()) continue
        String n = f.name.toLowerCase()
        boolean likely = (n.endsWith('_masks.tif') || n.endsWith('_masks.tiff') ||
                          n.endsWith('_masks.png') || n.contains('_cp_masks') ||
                          n.contains('cp_masks'))
        if (likely) candidates << f
    }
    if (candidates.isEmpty()) return null
    candidates.sort { -it.lastModified() }
    return candidates[0]
}

// ── C9: PER-LABEL MEASUREMENTS WITHOUT MorphoLibJ ────────────────────────────
def computeAreaCentroidTable(ImagePlus labelImp) {
    int w = labelImp.getWidth(), h = labelImp.getHeight()
    def ip = labelImp.getProcessor()
    Map<Integer, double[]> acc = new LinkedHashMap<>()
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            int lbl = (int) ip.getPixelValue(x, y)
            if (lbl <= 0) continue
            double[] v = acc.get(lbl)
            if (v == null) { v = [0d, 0d, 0d] as double[]; acc.put(lbl, v) }
            v[0] += 1d; v[1] += x; v[2] += y
        }
    }
    def rt = new ResultsTable()
    def cal = labelImp.getCalibration()
    double pw = (cal != null && cal.pixelWidth > 0) ? cal.pixelWidth : 1.0d
    double ph = (cal != null && cal.pixelHeight > 0) ? cal.pixelHeight : 1.0d
    acc.each { lbl, v ->
        rt.incrementCounter()
        rt.addValue('Label', lbl)
        rt.addValue('Area', v[0] * pw * ph)
        rt.addValue('Centroid_X', (v[1] / v[0]) * pw)
        rt.addValue('Centroid_Y', (v[2] / v[0]) * ph)
    }
    return rt
}

try {
    new File(outputMaskPath).parentFile.mkdirs()
    new File(outputCsvPath).parentFile.mkdirs()

    ImagePlus imp = WindowManager.getCurrentImage()
    if (imp == null) { IJ.log('[ERROR] No active image.'); println('FINAL STATUS: FAILURE'); return }

    def imp2 = imp.duplicate()
    imp2.setTitle(imp.getTitle() + '_cellpose_input_dup')
    if (imp2.getBitDepth() != 8) IJ.run(imp2, '8-bit', '')

    // Optional: invert if image is bright-on-dark and you want Cellpose to see dark cells.
    // Heuristic mirrors the threshold direction rule from PROJECT STATE.
    def stats = imp2.getStatistics()
    boolean cellsAreDark = stats.median <= (stats.min + stats.max) / 2.0d
    if (!cellsAreDark) {
        IJ.log('[INFO] Image is bright-on-dark; inverting for dark-cell Cellpose configuration.')
        IJ.run(imp2, 'Invert', '')
    }

    def model = new Model()
    model.setLogger(Logger.IJ_LOGGER)

    def settings = new Settings(imp2)
    settings.detectorFactory = new CellposeDetectorFactory()
    settings.detectorSettings = [
        'CONDA_ENV'              : 'base',
        'CELLPOSE_MODEL'         : modelName,
        'CELLPOSE_MODEL_FILEPATH': '',
        'PRETRAINED_OR_CUSTOM'   : 'CELLPOSE_MODEL',
        'TARGET_CHANNEL'         : String.valueOf(targetChannel),
        'OPTIONAL_CHANNEL_2'     : String.valueOf(optionalChannel),
        'CELL_DIAMETER'          : (double) cellDiameter,
        'USE_GPU'                : useGpu,
        'SIMPLIFY_CONTOURS'      : simplifyContours,
    ]

    // C5 — set tracker via reflection so the script survives package renames.
    def trackerBundle = buildTrackerFactoryAndSettings()
    if (trackerBundle == null) {
        IJ.log('[ERROR] No compatible TrackMate tracker factory found.')
        println('FINAL STATUS: FAILURE'); return
    }
    settings.trackerFactory  = trackerBundle[0]
    settings.trackerSettings = trackerBundle[1]

    settings.initialSpotFilterValue = 0.0d
    settings.addAllAnalyzers()
    settings.addSpotFilter(new FeatureFilter('QUALITY', 0.0d, true))

    def trackmate = new TrackMate(model, settings)
    if (!trackmate.checkInput()) { IJ.log('[ERROR] checkInput: ' + trackmate.getErrorMessage()); println('FINAL STATUS: FAILURE'); return }
    if (!trackmate.process())    { IJ.log('[ERROR] process: '    + trackmate.getErrorMessage()); println('FINAL STATUS: FAILURE'); return }

    IJ.log('[INFO] TrackMate-Cellpose detections: ' + model.getSpots().getNSpots(true))

    // C7 — find and open the mask file written by Cellpose.
    File cpDir = findNewestTrackMateCellposeDir()
    if (cpDir == null) {
        IJ.log('[ERROR] No TrackMate-cellpose_* directory in /tmp; Cellpose probably did not write outputs.')
        println('FINAL STATUS: FAILURE'); return
    }
    File maskFile = findBestMaskFile(cpDir)
    if (maskFile == null) {
        IJ.log('[ERROR] No *_cp_masks.{tif,png} file in ' + cpDir.getAbsolutePath())
        println('FINAL STATUS: FAILURE'); return
    }
    IJ.log('[INFO] Opening Cellpose mask: ' + maskFile.getAbsolutePath())

    ImagePlus labelImp = IJ.openImage(maskFile.getAbsolutePath()).duplicate()
    labelImp.setTitle('cellpose_instance_labels_preview')
    if (labelImp.getBitDepth() != 16) IJ.run(labelImp, '16-bit', '')
    labelImp.setCalibration(imp.getCalibration())

    ImagePlus maskImp = labelImp.duplicate()
    maskImp.setTitle('cellpose_binary_mask_preview')
    IJ.setThreshold(maskImp, 1, 65535)
    IJ.run(maskImp, 'Convert to Mask', '')
    maskImp.setCalibration(imp.getCalibration())

    IJ.saveAsTiff(maskImp,  outputMaskPath)
    IJ.saveAsTiff(labelImp, outputLabelPath)

    // C9 — measurements via pixel iteration; no MorphoLibJ import.
    ResultsTable out = computeAreaCentroidTable(labelImp)
    out.save(outputCsvPath)

    IJ.log('[INFO] Wrote: ' + outputMaskPath)
    IJ.log('[INFO] Wrote: ' + outputLabelPath)
    IJ.log('[INFO] Wrote: ' + outputCsvPath)

    labelImp.show(); maskImp.show(); imp2.show()
    success = true

} catch (Exception e) {
    IJ.log('[ERROR] Unhandled exception: ' + e.getMessage())
    e.printStackTrace()
}

println(success ? 'FINAL STATUS: SUCCESS' : 'FINAL STATUS: FAILURE')
