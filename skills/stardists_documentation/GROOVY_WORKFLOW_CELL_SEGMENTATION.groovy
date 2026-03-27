/**
 * StarDist — Cell Segmentation, Counting, and Comparison
 * Groovy script for Fiji Script Editor (Language: Groovy)
 *
 * PURPOSE:
 *   Applies StarDist 2D to the currently open image to:
 *     1. Segment cells/nuclei using a built-in or custom model
 *     2. Count detected cells
 *     3. Measure shape and intensity properties per cell
 *     4. (Optional) Compare result against a ground-truth label image using
 *        Label Overlap Measures — requires MorphoLibJ to be installed
 *     5. Save label image, measurements CSV, and RGB overlay PNG
 *
 * INPUTS:
 *   Active image  : the currently open 2D grayscale image in Fiji.
 *                   Open a fluorescence nuclei image before running.
 *                   A public test dataset is available at:
 *                   https://data.broadinstitute.org/bbbc/BBBC008/
 *   Ground truth (optional):
 *                   A second open image whose title starts with "gt-"
 *                   (e.g. "gt-labels") — used for Label Overlap comparison.
 *                   Requires MorphoLibJ (Plugins > MorphoLibJ must exist).
 *
 * OUTPUTS:
 *   <title>-labels.tif       : integer label image (one value per detected cell)
 *   <title>-overlay.png      : RGB colour overlay of outlines on original image
 *   <title>-measurements.csv : per-cell properties from ROI Manager measurements
 *   <title>-overlap.csv      : overlap metrics vs ground truth (if GT image open)
 *   Log window               : cell count and key result metrics
 *
 * REQUIREMENTS:
 *   - Fiji with StarDist, CSBDeep, and TensorFlow update sites enabled
 *     (Help > Update... > Manage update sites > tick all three > Apply > Restart)
 *   - (Optional) MorphoLibJ for Label Overlap comparison
 *
 * PARAMETERS TO ADJUST (see section below):
 *   MODEL_CHOICE       — built-in or custom model selection string
 *   MODEL_FILE         — path to .zip file (custom models only; leave "" otherwise)
 *   NORMALIZE_INPUT    — true recommended for nearly all images
 *   PERCENTILE_BOTTOM  — lower clip for normalisation (default 1.0)
 *   PERCENTILE_TOP     — upper clip for normalisation (default 99.8)
 *   PROB_THRESH        — detection probability threshold (raise to reduce FP)
 *   NMS_THRESH         — NMS overlap threshold (lower to separate touching cells)
 *   N_TILES            — increase if Fiji throws an out-of-memory error
 *   EXCLUDE_BOUNDARY   — suppress detections within this many px of image edge
 */

// ── SciJava service injection ──────────────────────────────────────────────────
// These #@ lines inject Fiji services; they must be at the top of the file.
#@ CommandService command
#@ UIService uiService

// ── Imports ────────────────────────────────────────────────────────────────────
import de.csbdresden.stardist.StarDist2D
import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.plugin.frame.RoiManager
import ij.measure.ResultsTable
import ij.measure.Measurements

// ─────────────────────────────────────────────────────────────────────────────
//  PARAMETERS  ← adjust for your data
// ─────────────────────────────────────────────────────────────────────────────

// Model selection — choose ONE of these strings (exact match required):
//   "Versatile (fluorescent nuclei)"    → fluorescence DAPI/Hoechst images
//   "DSB 2018 (from StarDist 2D paper)" → alternative fluorescence model
//   "Versatile (H&E nuclei)"            → brightfield H&E histology images
//   "Model (.zip) from File"            → custom model: set MODEL_FILE below
//   "Model (.zip) from URL"             → custom model from URL: set MODEL_FILE
String  MODEL_CHOICE        = "Versatile (fluorescent nuclei)"
String  MODEL_FILE          = ""        // path to .zip for custom models; else leave ""

boolean NORMALIZE_INPUT     = true      // strongly recommended; only disable if pre-normalised
double  PERCENTILE_BOTTOM   = 1.0       // lower clip percentile for normalisation
double  PERCENTILE_TOP      = 99.8      // upper clip percentile for normalisation

double  PROB_THRESH         = 0.5       // probability threshold (0–1)
                                        // raise (e.g. 0.7) to get fewer, more confident detections
                                        // lower (e.g. 0.3) to detect more, possibly including FP
double  NMS_THRESH          = 0.4       // non-maximum suppression overlap threshold (0–1)
                                        // lower (e.g. 0.2) to separate touching cells better

int     N_TILES             = 1         // increase for large images: 4 (2×2), 9 (3×3), 16 (4×4)
int     EXCLUDE_BOUNDARY    = 2         // px from image border where detections are suppressed
                                        // set to 0 to keep cells at the image edge
String  ROI_POSITION        = "Automatic"  // "Automatic" for 2D; "Stack" or "Hyperstack" for timelapse
// ─────────────────────────────────────────────────────────────────────────────

// ── 0. Get the active image ────────────────────────────────────────────────────
ImagePlus imp = IJ.getImage()
if (imp == null) {
    IJ.error("No image is open.\nPlease open a 2D fluorescence image first.")
    return
}

String title   = imp.getTitle().replaceAll(/\.[^.]+$/, "")  // strip file extension
String saveDir = (imp.getOriginalFileInfo()?.directory) ?: IJ.getDirectory("imagej")

IJ.log("═══════════════════════════════════════════════")
IJ.log(" StarDist Cell Segmentation — Groovy workflow")
IJ.log(" Image  : " + imp.getTitle())
IJ.log(" Model  : " + MODEL_CHOICE)
IJ.log(" probThresh = " + PROB_THRESH + "   nmsThresh = " + NMS_THRESH)
IJ.log("═══════════════════════════════════════════════")

// ── 1. Validate image ─────────────────────────────────────────────────────────
// StarDist 2D requires a single-channel 2D grayscale image.
if (imp.getNChannels() > 1) {
    IJ.log("[Prep] WARNING: Image has " + imp.getNChannels() + " channels.")
    IJ.log("[Prep] StarDist requires a single channel. Extracting channel 1.")
    IJ.run(imp, "Slice Keeper", "first=1 last=1 increment=1")
    imp = IJ.getImage()
}
if (imp.getType() == ImagePlus.COLOR_RGB) {
    IJ.log("[Prep] Converting RGB to 8-bit grayscale.")
    IJ.run(imp, "8-bit", "")
}

IJ.log("[Prep] Image ready: " + imp.getWidth() + "×" + imp.getHeight() +
       " px, " + imp.getBitDepth() + "-bit")

// ── 2. Clear the ROI Manager before running ───────────────────────────────────
// This prevents detections from a previous run accumulating in the manager.
RoiManager rm = RoiManager.getInstance()
if (rm != null) {
    rm.reset()
} else {
    rm = new RoiManager()
}
IJ.run("Clear Results", "")

// ── 3. Run StarDist 2D ────────────────────────────────────────────────────────
// command.run() is the SciJava API call.
// false = do not show a blocking progress dialog.
// .get() blocks the script until inference is fully complete.
// All boolean parameters MUST be Groovy booleans (true/false), NOT strings.
IJ.log("[StarDist] Running inference...")
def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         MODEL_CHOICE,
    "modelFile",           MODEL_FILE,
    "normalizeInput",      NORMALIZE_INPUT,
    "percentileBottom",    PERCENTILE_BOTTOM,
    "percentileTop",       PERCENTILE_TOP,
    "probThresh",          PROB_THRESH,
    "nmsThresh",           NMS_THRESH,
    "outputType",          "Both",          // always request both; gives label + ROI Manager
    "nTiles",              N_TILES,
    "excludeBoundary",     EXCLUDE_BOUNDARY,
    "roiPosition",         ROI_POSITION,
    "verbose",             false,
    "showCsbdeepProgress", false,
    "showProbAndDist",     false
).get()

IJ.log("[StarDist] Inference complete.")

// ── 4. Retrieve the label image ───────────────────────────────────────────────
// getOutput("label") returns a SciJava Dataset — NOT an ImagePlus.
// It must be shown via uiService.show() before IJ.getImage() can retrieve it.
def labelDataset = res.getOutput("label")
if (labelDataset == null) {
    IJ.error("StarDist returned no label output.\nCheck the model and image type.")
    return
}
uiService.show(labelDataset)            // registers the Dataset as a visible ImagePlus
ImagePlus labelImp = IJ.getImage()      // now retrieve as ImagePlus
labelImp.setTitle(title + "-labels")
IJ.log("[Output] Label image: " + labelImp.getTitle())

// ── 5. Count detected cells ───────────────────────────────────────────────────
// Primary method: ROI Manager count (excludes boundary ROIs as per EXCLUDE_BOUNDARY)
rm = RoiManager.getInstance()
int cellCount
if (rm != null && rm.getCount() > 0) {
    cellCount = rm.getCount()
} else {
    // Fallback: label image maximum = highest label integer = cell count
    def stats = labelImp.getStatistics(Measurements.MIN_MAX)
    cellCount = (int) stats.max
    IJ.log("[Count] ROI Manager empty — using label image maximum as count.")
}
IJ.log("─── CELL COUNT: " + cellCount + " cells detected.")

// ── 6. Measure cell properties ────────────────────────────────────────────────
// Measures area, intensity, shape descriptors for every ROI.
// Redirecting to imp ensures intensity values come from the original image.
IJ.log("[Measure] Measuring cell properties...")
if (rm != null && rm.getCount() > 0) {
    IJ.run("Set Measurements...",
           "area mean min center perimeter shape redirect=None decimal=3")
    rm.deselect()                       // deselect to ensure all ROIs are measured
    rm.runCommand(imp, "Measure")       // run measurement on the original image
    ResultsTable rt = ResultsTable.getResultsTable()
    if (rt != null && rt.size() > 0) {
        IJ.log("[Measure] Measured " + rt.size() + " cells.")
        String csvPath = saveDir + title + "-measurements.csv"
        try {
            rt.save(csvPath)
            IJ.log("[Measure] Saved: " + csvPath)
        } catch (Exception e) {
            IJ.log("[Measure] WARNING: Could not save CSV: " + e.getMessage())
        }
    } else {
        IJ.log("[Measure] WARNING: Results table is empty.")
    }
} else {
    IJ.log("[Measure] WARNING: ROI Manager is empty — no measurements taken.")
    IJ.log("[Measure] Try re-running with a lower probThresh value.")
}

// ── 7. Create RGB colour overlay for visual inspection ────────────────────────
// Flattens the ROI outlines onto the original image as a PNG.
IJ.log("[Overlay] Creating RGB overlay...")
try {
    rm = RoiManager.getInstance()
    if (rm != null && rm.getCount() > 0) {
        imp.show()
        rm.deselect()
        rm.runCommand(imp, "Show All")
        IJ.run(imp, "Flatten", "")      // burns ROI overlays into a new RGB image
        ImagePlus overlayImp = IJ.getImage()
        overlayImp.setTitle(title + "-overlay")
        String overlayPath = saveDir + title + "-overlay.png"
        IJ.saveAs(overlayImp, "PNG", overlayPath)
        IJ.log("[Overlay] Saved: " + overlayPath)
    } else {
        IJ.log("[Overlay] Skipped — no ROIs in manager.")
    }
} catch (Exception e) {
    IJ.log("[Overlay] WARNING: " + e.getMessage())
}

// ── 8. Compare against ground truth (optional, requires MorphoLibJ) ───────────
// To enable: open a label image whose title starts with "gt-" before running.
// Label Overlap Measures produces Jaccard, Dice, and per-label overlap metrics.
String[] openTitles = WindowManager.getImageTitles()
String gtTitle = openTitles.find { it.startsWith("gt-") }

if (gtTitle != null) {
    IJ.log("─── Comparing against ground truth: " + gtTitle)
    try {
        // MorphoLibJ command — requires IJPB-plugins update site
        IJ.run("Label Overlap Measures",
               "source=[" + labelImp.getTitle() + "] target=[" + gtTitle + "] overlap jaccard dice")
        // ResultsTable is named after the command
        ResultsTable overlapRt = ResultsTable.getResultsTable("Label Overlap Measures")
        if (overlapRt != null && overlapRt.size() > 0) {
            String overlapPath = saveDir + title + "-overlap.csv"
            try {
                overlapRt.save(overlapPath)
                IJ.log("[Compare] Overlap table saved: " + overlapPath)
            } catch (Exception e) {
                IJ.log("[Compare] WARNING: Could not save overlap CSV: " + e.getMessage())
            }
        } else {
            IJ.log("[Compare] WARNING: Overlap table was empty.")
        }
    } catch (Exception e) {
        IJ.log("[Compare] WARNING: Label Overlap Measures failed: " + e.getMessage())
        IJ.log("[Compare] Is MorphoLibJ installed? Plugins > MorphoLibJ must exist.")
    }
} else {
    IJ.log("─── No ground-truth image found.")
    IJ.log("    To compare: open a label image whose title starts with 'gt-'.")
    IJ.log("    Example: rename a manual annotation to 'gt-labels' and keep it open.")
}

// ── 9. Save label image ────────────────────────────────────────────────────────
try {
    String labelPath = saveDir + title + "-labels.tif"
    IJ.saveAsTiff(labelImp, labelPath)
    IJ.log("[Save] Label TIFF saved: " + labelPath)
} catch (Exception e) {
    IJ.log("[Save] WARNING: Could not save label image: " + e.getMessage())
}

// ── Summary ────────────────────────────────────────────────────────────────────
IJ.log("═══════════════════════════════════════════════")
IJ.log(" SEGMENTATION COMPLETE")
IJ.log(" Model      : " + MODEL_CHOICE)
IJ.log(" probThresh : " + PROB_THRESH + "   nmsThresh: " + NMS_THRESH)
IJ.log(" Cells found: " + cellCount)
IJ.log(" Label image: " + labelImp.getTitle())
IJ.log(" Outputs in : " + saveDir)
if (gtTitle != null)
    IJ.log(" GT compare : " + title + "-overlap.csv")
IJ.log("═══════════════════════════════════════════════")
