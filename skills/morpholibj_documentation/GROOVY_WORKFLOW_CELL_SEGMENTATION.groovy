/**
 * MorphoLibJ — Distance-Transform Watershed Cell Segmentation  (MorphoLibJ 1.6.5)
 * ============================================================================
 *
 * Separates touching/round objects (nuclei, cells, particles) in a 2D image and
 * measures them, using the classic four-step pipeline:
 *
 *     Threshold → Chamfer Distance Map → Extended Maxima (markers)
 *               → Marker-controlled Watershed → clean up → count → measure
 *
 * DESIGNED TO RUN UNATTENDED — there are NO dialog pop-ups and NO user clicks:
 *   • every MorphoLibJ IJ.run() call is given a complete, non-empty option string
 *     (an empty "" string would make the plugin's dialog appear and block);
 *   • binary "black background" behaviour is pinned with Prefs.blackBackground;
 *   • label cleanup/counting uses the inra.ijpb Java API, which never shows a dialog;
 *   • new output windows are captured by an image-ID diff, never by a fragile
 *     getCurrentImage() guess.
 *
 * INPUTS
 *   • Uses the active image if one is open; otherwise loads the Fiji "Blobs (25K)" sample.
 *   • Optional ground truth: an open label image whose title starts with "gt-"
 *     (e.g. "gt-labels") triggers a Label Overlap (Jaccard/Dice) comparison.
 *
 * OUTPUTS  (all shown as windows; CSV/TIF written next to the source image when possible)
 *   <title>-binary    8-bit binary mask
 *   <title>-dist      32-bit Chamfer distance map
 *   <title>-labels    final 16-bit label image (one integer per object)
 *   <title>-overlay   RGB colour view of the labels
 *   ResultsTable      area / perimeter / circularity / … per object  (-> <title>-measurements.csv)
 *   Log               object count and (if GT present) overlap metrics
 *
 * Verified on Fiji ImageJ 2.16.0/1.54p with MorphoLibJ 1.6.5.
 */

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.Prefs
import ij.measure.ResultsTable
import inra.ijpb.label.LabelImages

// ─────────────────────────────────────────────────────────────────────────────
//  PARAMETERS — tune for your data
// ─────────────────────────────────────────────────────────────────────────────
String THRESHOLD_METHOD = "Otsu"             // "Otsu" "Default" "Li" "Triangle" "Huang" …
double GAUSSIAN_SIGMA   = 1.0                 // pre-smoothing of the input (px); 0 = skip
String CHAMFER_WEIGHTS  = "Borgefors (3,4)"  // or "Chessknight (5,7,11)" (more accurate)
double DIST_BLUR_SIGMA  = 2.0                 // blur of the distance map (px) — fewer spurious maxima
int    MAXIMA_DYNAMIC   = 2                   // Extended Maxima tolerance (normalized dist): higher → fewer seeds
int    CONNECTIVITY     = 4                   // 4 = orthogonal (rounder), 8 = include diagonals
int    MIN_OBJECT_AREA  = 20                  // discard labels smaller than this (px²)
String OVERLAY_COLORMAP = "Golden angle"     // Labels-To-RGB colormap
// ─────────────────────────────────────────────────────────────────────────────

Prefs.blackBackground = true                 // deterministic binary: foreground = 255

/** Close an image without triggering a "Save changes?" dialog. */
def safeClose = { ImagePlus imp -> if (imp != null) { imp.changes = false; imp.close() } }

/** Run a closure that creates one new image window and return that ImagePlus (or null). */
def grabNewImage = { Closure action ->
    def before = (WindowManager.getIDList() ?: new int[0]) as Set
    action()
    def after  = (WindowManager.getIDList() ?: new int[0]) as List
    def freshId = after.reverse().find { !before.contains(it) }
    return freshId != null ? WindowManager.getImage(freshId) : null
}

// ── 0. Acquire image ─────────────────────────────────────────────────────────
ImagePlus src = WindowManager.getCurrentImage()
if (src == null) {
    IJ.log("[CellSeg] No image open — loading the Fiji 'Blobs (25K)' sample.")
    IJ.run("Blobs (25K)")
    src = WindowManager.getCurrentImage()
}
if (src == null) { IJ.error("No image available."); return }

String original = src.getTitle()
int dot = original.lastIndexOf('.')
String title = (dot > 0) ? original.substring(0, dot) : original
String saveDir = src.getOriginalFileInfo()?.directory ?: IJ.getDirectory("imagej")
IJ.log("═══ MorphoLibJ cell segmentation: " + original)

// ── 1. Binary mask (popup-free thresholding) ─────────────────────────────────
ImagePlus work = grabNewImage { IJ.run(src, "Duplicate...", "title=[${title}-binary]") }
if (work == null) { IJ.error("Duplicate failed."); return }

if (work.getType() == ImagePlus.COLOR_RGB) {
    IJ.run(work, "8-bit", "")                // luminance
} else if (work.getBitDepth() != 8) {
    IJ.run(work, "8-bit", "")
}

// Inverting LUT (e.g. the Fiji "Blobs" sample) reverses the meaning of bright/dark:
// the objects have HIGH pixel values but display dark, so a "dark"-background threshold
// + Convert to Mask comes out INVERTED and the watershed would segment the background.
// Apply a normal grayscale LUT so pixel values and display agree before thresholding.
if (work.getProcessor().isInvertedLut()) {
    IJ.log("[1] Inverting LUT detected — applying a normal grayscale LUT before thresholding.")
    IJ.run(work, "Grays", "")
}

if (GAUSSIAN_SIGMA > 0.0) IJ.run(work, "Gaussian Blur...", "sigma=${GAUSSIAN_SIGMA}")

IJ.setAutoThreshold(work, THRESHOLD_METHOD + " dark")   // objects = bright (high values)
IJ.run(work, "Convert to Mask", "")
IJ.run(work, "Fill Holes (Binary/Gray)", "")            // MorphoLibJ, no dialog
ImagePlus binary = work
IJ.log("[1] Binary mask ready: " + binary.getTitle())

// ── 2. Chamfer distance map (+ smoothing) ────────────────────────────────────
ImagePlus dist = grabNewImage {
    IJ.run(binary, "Chamfer Distance Map", "distances=[${CHAMFER_WEIGHTS}] output=[32 bits] normalize")
}
if (dist == null) { IJ.error("Chamfer Distance Map produced no image."); return }
dist.setTitle("${title}-dist")
if (DIST_BLUR_SIGMA > 0.0) IJ.run(dist, "Gaussian Blur...", "sigma=${DIST_BLUR_SIGMA}")
IJ.log("[2] Distance map ready (max dist = " + String.format("%.2f", dist.getStatistics().max) + ").")

// ── 3. Seeds: extended maxima → labelled markers ─────────────────────────────
ImagePlus maxima = grabNewImage {
    IJ.run(dist, "Extended Min & Max",
        "operation=[Extended Maxima] dynamic=${MAXIMA_DYNAMIC} connectivity=${CONNECTIVITY}")
}
if (maxima == null) { IJ.error("Extended Maxima produced no image."); return }
maxima.setTitle("${title}-maxima")

ImagePlus markers = grabNewImage {
    IJ.run(maxima, "Connected Components Labeling", "connectivity=${CONNECTIVITY} type=[16 bits]")
}
if (markers == null) { IJ.error("Connected Components Labeling produced no image."); return }
markers.setTitle("${title}-markers")
int nSeeds = LabelImages.findAllLabels(markers).length
IJ.log("[3] Seeds detected: " + nSeeds)

// ── 4. Marker-controlled watershed on the INVERTED distance map ──────────────
ImagePlus distInv = grabNewImage { IJ.run(dist, "Duplicate...", "title=[${title}-distInv]") }
distInv.resetDisplayRange()
IJ.run(distInv, "Invert", "")                // flood from object centres (= minima of -dist)

ImagePlus labelsRaw = grabNewImage {
    IJ.run("Marker-controlled Watershed",
        "input=[${distInv.getTitle()}] marker=[${markers.getTitle()}] " +
        "mask=[${binary.getTitle()}] compactness=0 calculate" + (CONNECTIVITY == 8 ? " use" : ""))
}
if (labelsRaw == null) { IJ.error("Marker-controlled Watershed produced no image."); return }
IJ.log("[4] Watershed labels (raw): " + LabelImages.findAllLabels(labelsRaw).length)

// tidy intermediate windows (no save prompts)
safeClose(maxima); safeClose(markers); safeClose(distInv)

// ── 5. Clean up via the Java API (no dialogs, deterministic) ─────────────────
LabelImages.removeBorderLabels(labelsRaw)                     // drop objects on the image edge
ImagePlus labels = LabelImages.sizeOpening(labelsRaw, MIN_OBJECT_AREA)  // drop debris -> new ImagePlus
LabelImages.remapLabels(labels)                              // renumber 1..N
safeClose(labelsRaw)
labels.setTitle("${title}-labels")
labels.show()

int[] labelValues = LabelImages.findAllLabels(labels)
int count = labelValues.length
IJ.log("─── OBJECT COUNT: " + count)

// ── 6. Colour overlay ────────────────────────────────────────────────────────
ImagePlus overlay = grabNewImage {
    IJ.run(labels, "Labels To RGB", "colormap=[${OVERLAY_COLORMAP}] background=Black shuffle")
}
if (overlay != null) overlay.setTitle("${title}-overlay")

// ── 7. Shape measurements ────────────────────────────────────────────────────
IJ.run(labels, "Analyze Regions",
    "area perimeter circularity equivalent_ellipse ellipse_elong. " +
    "convexity max._feret_diameter geodesic_diameter")
def measWin = WindowManager.getWindow("${labels.getTitle()}-Morphometry")
ResultsTable rt = (measWin instanceof ij.text.TextWindow) ? measWin.getResultsTable() : null
if (rt != null && rt.size() > 0) {
    IJ.log("[7] Measured " + rt.size() + " regions.")
    try { rt.save(saveDir + title + "-measurements.csv"); IJ.log("    saved " + title + "-measurements.csv") }
    catch (Exception e) { IJ.log("    WARNING: could not save CSV: " + e.getMessage()) }
} else {
    IJ.log("[7] WARNING: measurement table not found.")
}

// ── 8. Optional ground-truth comparison ──────────────────────────────────────
String gt = (WindowManager.getImageTitles() as List).find { it.startsWith("gt-") }
if (gt != null) {
    IJ.log("─── Comparing against ground truth: " + gt)
    IJ.run("Label Overlap Measures",
        "source=[${labels.getTitle()}] target=[${gt}] overlap jaccard dice volume")
    def ovWin = WindowManager.getWindow("${labels.getTitle()}-all-labels-overlap-measurements")
    ResultsTable ov = (ovWin instanceof ij.text.TextWindow) ? ovWin.getResultsTable() : null
    if (ov != null && ov.size() > 0) {
        IJ.log("    Jaccard = " + ov.getValue("JaccardIndex", 0) + "  Dice = " + ov.getValue("DiceCoefficient", 0))
        try { ov.save(saveDir + title + "-overlap.csv") } catch (Exception e) {}
    }
} else {
    IJ.log("─── No ground-truth image (open one whose title starts with 'gt-') — skipping overlap.")
}

// ── 9. Save the label image ──────────────────────────────────────────────────
try { IJ.saveAsTiff(labels, saveDir + title + "-labels.tif"); IJ.log("[9] Saved " + title + "-labels.tif") }
catch (Exception e) { IJ.log("[9] WARNING: could not save labels: " + e.getMessage()) }

// Mark output windows as "saved" so the user can close them without a save prompt.
[binary, dist, labels, overlay].each { if (it != null) it.changes = false }

IJ.log("═══════════════════════════════════════")
IJ.log(" DONE — input: " + original)
IJ.log("        objects: " + count)
IJ.log("        labels : " + labels.getTitle())
IJ.log("        overlay: " + (overlay != null ? overlay.getTitle() : "n/a"))
IJ.log("═══════════════════════════════════════")
