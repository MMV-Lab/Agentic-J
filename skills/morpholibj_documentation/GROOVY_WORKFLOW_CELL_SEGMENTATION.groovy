/**
 * MorphoLibJ — Distance-Transform Watershed Cell Segmentation
 *
 * PURPOSE:
 *   Segments individual cells (or similar round objects) in a 2D fluorescence
 *   or brightfield image using a four-step pipeline:
 *     Step 1  Threshold image to binary
 *     Step 2  Compute Chamfer distance transform on binary mask
 *     Step 3  Detect regional maxima of the distance map (one per cell)
 *     Step 4  Marker-controlled watershed on the inverted distance map
 *   Then counts the segmented cells and — if a ground-truth label image is open
 *   — quantifies segmentation accuracy with Jaccard / Dice coefficients.
 *
 * INPUTS:
 *   Automatic  :  any open 8-bit or 16-bit grayscale image (bright objects, dark background)
 *   Demo       :  if no image is open, the built-in Fiji "Blobs (25K)" sample is used
 *   Ground truth (optional):  a second open image whose title starts with "gt-"
 *                             (e.g. "gt-labels") — used for Label Overlap comparison
 *
 * OUTPUTS:
 *   <title>-binary       : thresholded binary image
 *   <title>-dist         : 32-bit Chamfer distance map
 *   <title>-maxima-lbl   : labeled regional maxima (one integer per cell centre)
 *   <title>-labels       : final segmented label image
 *   <title>-overlay      : RGB colour overlay of segmentation on original
 *   ResultsTable         : area / perimeter / circularity for each cell
 *   Log window           : cell count and (if GT available) overlap metrics
 *
 * REQUIREMENTS:
 *   Fiji with MorphoLibJ (IJPB-plugins update site)
 *   Tested with MorphoLibJ v1.4.x / Fiji 2.x
 *
 * PARAMETERS TO ADJUST:
 *   THRESHOLD_METHOD   — auto-threshold algorithm (see full list in the dialog
 *                        Plugins > Segmentation > Auto Threshold)
 *   GAUSSIAN_SIGMA     — pre-blur radius in px; set 0.0 to skip
 *   MIN_CELL_AREA_PX   — discard objects smaller than this (pixels²)
 *   CONNECTIVITY       — 4 (orthogonal, rounder shapes) or 8 (diagonal too)
 *   CHAMFER_WEIGHTS    — distance-map weight set (see table in GROOVY_API.md §E2)
 *   CLOSING_RADIUS     — radius for morphological closing to fill holes
 *   DIST_BLUR_SIGMA    — blur applied to distance map to prevent over-segmentation
 */

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.measure.ResultsTable

// ─────────────────────────────────────────────────────────────────────────────
//  PARAMETERS  ← adjust for your data
// ─────────────────────────────────────────────────────────────────────────────
String  THRESHOLD_METHOD  = "Otsu"              // e.g. "Otsu", "Triangle", "Default", "Li"
double  GAUSSIAN_SIGMA    = 0.5                 // pre-smoothing sigma (px); 0.0 = skip
int     MIN_CELL_AREA_PX  = 20                  // px²; tune to remove debris
int     CONNECTIVITY      = 4                   // 4 = orthogonal only; 8 = includes diagonals
String  CHAMFER_WEIGHTS   = "Borgefors (3,4)"   // or "Chessknight (5,7,11)" for higher accuracy
int     CLOSING_RADIUS    = 4                   // radius for morphological closing to fill holes
double  DIST_BLUR_SIGMA   = 4.0                 // blur applied to distance map to prevent over-segmentation
// ─────────────────────────────────────────────────────────────────────────────

// ── 0. Get or load image ─────────────────────────────────────────────────────
ImagePlus imp = WindowManager.getCurrentImage()
if (imp == null) {
    IJ.log("[Cell Seg] No image open — loading Fiji Blobs sample.")
    IJ.run("Blobs (25K)")
    imp = WindowManager.getCurrentImage()
    if (imp == null) {
        IJ.error("Could not load sample image. Please open an image first.")
        return
    }
}
String originalTitle = imp.getTitle()
int dotIndex = originalTitle.lastIndexOf('.')
String title = (dotIndex > 0) ? originalTitle.substring(0, dotIndex) : originalTitle
String saveDir  = imp.getOriginalFileInfo()?.directory ?: IJ.getDirectory("imagej")
IJ.log("─── MorphoLibJ Cell Segmentation starting: " + imp.getTitle())

// ── 1. Prepare a working copy ─────────────────────────────────────────────────
// Duplicate the image to avoid modifying the original data
IJ.run(imp, "Duplicate...", "title=[${title}-work]")
ImagePlus workImp = WindowManager.getImage("${title}-work")
if (workImp == null) {
    IJ.error("Duplicate failed. Aborting.")
    return
}

if (workImp.getType() == ImagePlus.COLOR_RGB) {
    IJ.log("[Step 0] Splitting RGB channels and combining them into a single binary mask.")
    ij.plugin.ChannelSplitter splitter = new ij.plugin.ChannelSplitter()
    ImagePlus[] channels = splitter.split(workImp)
    
    ImagePlus combinedBinary = null
    ij.plugin.ImageCalculator ic = new ij.plugin.ImageCalculator()
    
    for (int i = 0; i < channels.length; i++) {
        ImagePlus ch = channels[i]
        if (GAUSSIAN_SIGMA > 0.0) {
            IJ.run(ch, "Gaussian Blur...", "sigma=${GAUSSIAN_SIGMA}")
        }
        IJ.setAutoThreshold(ch, THRESHOLD_METHOD + " dark")
        IJ.run(ch, "Convert to Mask", "")
        IJ.run(ch, "Fill Holes", "")
        
        if (combinedBinary == null) {
            combinedBinary = ch
        } else {
            combinedBinary = ic.run("OR create", combinedBinary, ch)
        }
    }
    workImp.close()
    workImp = combinedBinary
    workImp.setTitle("${title}-work")
    workImp.show()
} else {
    if (workImp.getType() == ImagePlus.GRAY16 || workImp.getType() == ImagePlus.GRAY32) {
        IJ.log("[Step 0] Converting to 8-bit.")
        IJ.run(workImp, "8-bit", "")
    }
    
    if (GAUSSIAN_SIGMA > 0.0) {
        IJ.log("[Step 0] Applying Gaussian blur (σ=${GAUSSIAN_SIGMA}).")
        IJ.run(workImp, "Gaussian Blur...", "sigma=${GAUSSIAN_SIGMA}")
    }
    
    // ── STEP 1: Threshold to binary ───────────────────────────────────────────────
    IJ.log("[Step 1] Thresholding with method: ${THRESHOLD_METHOD} (bright objects on dark background)")
    IJ.setAutoThreshold(workImp, THRESHOLD_METHOD + " dark")
    IJ.run(workImp, "Convert to Mask", "")
    IJ.run(workImp, "Fill Holes", "")
}

// Apply morphological closing to fix any remaining small holes
IJ.log("[Step 1.5] Applying morphological closing to fix small holes.")
IJ.run(workImp, "Morphological Filters", "operation=Closing element=Disk radius=${CLOSING_RADIUS}")
ImagePlus closedImp = WindowManager.getCurrentImage()
if (closedImp != null && closedImp != workImp) {
    workImp.close()
    workImp = closedImp
}

workImp.setTitle("${title}-binary")
ImagePlus binaryImp = workImp
IJ.log("[Step 1] Binary image created: " + binaryImp.getTitle())

// ── STEP 2: Chamfer distance transform ───────────────────────────────────────
IJ.log("[Step 2] Computing Chamfer distance map (weights: ${CHAMFER_WEIGHTS}).")
IJ.run(binaryImp, "Chamfer Distance Map", "distances=[${CHAMFER_WEIGHTS}] output=[32 bits] normalize")
ImagePlus distImp = WindowManager.getCurrentImage()
if (distImp == null || distImp == binaryImp) {
    IJ.error("Chamfer Distance Map failed. Aborting.")
    return
}

// Add a slight blur to the distance map to merge multiple peaks inside a single cell
IJ.log("[Step 2.5] Blurring distance map to reduce over-segmentation.")
IJ.run(distImp, "Gaussian Blur...", "sigma=${DIST_BLUR_SIGMA}")

distImp.setTitle("${title}-dist")
IJ.log("[Step 2] Distance map created: " + distImp.getTitle())

// ── STEP 3: Detect regional maxima ────────────────────────────────────────────
IJ.log("[Step 3] Detecting regional maxima (connectivity=${CONNECTIVITY}).")
IJ.run(distImp, "Regional Min & Max", "operation=[Regional Maxima] connectivity=${CONNECTIVITY}")
ImagePlus maximaBinaryImp = WindowManager.getCurrentImage()
if (maximaBinaryImp == null || maximaBinaryImp == distImp) {
    IJ.error("Regional Maxima detection failed. Aborting.")
    return
}
maximaBinaryImp.setTitle("${title}-maxima-binary")

IJ.log("[Step 3] Labeling maxima as seeds.")
IJ.run(maximaBinaryImp, "Connected Components Labeling", "connectivity=${CONNECTIVITY} type=[16 bits]")
ImagePlus maximaLblImp = WindowManager.getCurrentImage()
if (maximaLblImp == null || maximaLblImp == maximaBinaryImp) {
    IJ.error("Connected Components Labeling failed. Aborting.")
    return
}
maximaLblImp.setTitle("${title}-maxima-lbl")
maximaBinaryImp.close()

// ── STEP 4: Marker-controlled watershed ───────────────────────────────────────
IJ.log("[Step 4] Inverting distance map for watershed landscape.")
IJ.run(distImp, "Duplicate...", "title=[${title}-dist-inv]")
ImagePlus distInvImp = WindowManager.getImage("${title}-dist-inv")
if (distInvImp == null) {
    IJ.error("Duplicate of distance map failed. Aborting.")
    return
}
distInvImp.resetDisplayRange()
IJ.run(distInvImp, "Invert", "")

String connFlag = (CONNECTIVITY == 8) ? "use" : ""
IJ.log("[Step 4] Running marker-controlled watershed.")
boolean watershedOk = false
try {
    IJ.run("Marker-controlled Watershed",
        ("input=[${distInvImp.getTitle()}] " +
         "marker=[${maximaLblImp.getTitle()}] " +
         "mask=[${binaryImp.getTitle()}] " +
         "calculate ${connFlag}").trim())
    watershedOk = true
} catch (RuntimeException e) {
    IJ.log("[Step 4] Primary watershed options failed: " + e.getMessage())
    IJ.log("[Step 4] Retrying with minimal legacy options.")
    IJ.run("Marker-controlled Watershed",
        ("input=[${distInvImp.getTitle()}] " +
         "marker=[${maximaLblImp.getTitle()}] " +
         "mask=[${binaryImp.getTitle()}]").trim())
    watershedOk = true
}

ImagePlus labelsImp = watershedOk ? WindowManager.getCurrentImage() : null
if (labelsImp == null) {
    IJ.error("Watershed produced no output image. Aborting.")
    return
}
labelsImp.setTitle("${title}-labels-raw")

distInvImp.close()
maximaLblImp.close()

// ── Post-processing ────────────────────────────────────────────────────────────
IJ.log("[Post] Removing border labels.")
IJ.run(labelsImp, "Remove Border Labels", "")

IJ.log("[Post] Removing labels smaller than ${MIN_CELL_AREA_PX} px².")
IJ.run(labelsImp, "Label Size Opening", "min=${MIN_CELL_AREA_PX}")

IJ.log("[Post] Remapping label indices (closing gaps).")
IJ.run(labelsImp, "Remap Labels", "")
labelsImp.setTitle("${title}-labels")

import inra.ijpb.label.LabelImages
int[] cellLabels = LabelImages.findAllLabels(labelsImp)
int   cellCount  = cellLabels.length
IJ.log("─── CELL COUNT: " + cellCount + " cells detected.")

IJ.log("[Overlay] Creating pseudo-color label view (fallback, no 'Labels to RGB' dependency).")
IJ.run(labelsImp, "Duplicate...", "title=[${title}-overlay]")
ImagePlus rgbImp = WindowManager.getImage("${title}-overlay")
if (rgbImp != null) {
    IJ.run(rgbImp, "8-bit", "")
    IJ.run(rgbImp, "Fire", "")
}

IJ.log("[Measure] Running Analyze Regions.")
IJ.run(labelsImp, "Analyze Regions", "area perimeter circularity inertia_ellipse ellipse_elong convexity max_feret")
ResultsTable rt = ResultsTable.getResultsTable()
if (rt != null && rt.size() > 0) {
    IJ.log("[Measure] Measured " + rt.size() + " regions.")
    try {
        String csvPath = saveDir + title + "-measurements.csv"
        rt.save(csvPath)
        IJ.log("[Measure] Saved: " + csvPath)
    } catch (Exception e) {
        IJ.log("[Measure] WARNING: Could not save CSV: " + e.getMessage())
    }
} else {
    IJ.log("[Measure] WARNING: ResultsTable empty — verify that labels image is active.")
}

String[] openTitles = WindowManager.getImageTitles()
String gtTitle = openTitles.find { it.startsWith("gt-") }
if (gtTitle != null) {
    IJ.log("─── Comparing segmentation against ground truth: " + gtTitle)
    IJ.run("Label Overlap Measures", "source=[${labelsImp.getTitle()}] target=[${gtTitle}] overlap jaccard dice")
    ResultsTable overlapRt = ResultsTable.getResultsTable("Label Overlap Measures")
    if (overlapRt != null && overlapRt.size() > 0) {
        try {
            String overlapPath = saveDir + title + "-overlap.csv"
            overlapRt.save(overlapPath)
            IJ.log("[Compare] Overlap metrics saved: " + overlapPath)
        } catch (Exception e) {
            IJ.log("[Compare] WARNING: Could not save overlap table: " + e.getMessage())
        }
    }
} else {
    IJ.log("─── No ground-truth image found (open an image whose title starts with 'gt-').")
    IJ.log("    Skipping Label Overlap Measures comparison.")
}

try {
    String labelPath = saveDir + title + "-labels.tif"
    IJ.saveAsTiff(labelsImp, labelPath)
    IJ.log("[Save] Label image saved: " + labelPath)
} catch (Exception e) {
    IJ.log("[Save] WARNING: Could not save label image: " + e.getMessage())
}

IJ.log("═══════════════════════════════════════")
IJ.log(" SEGMENTATION COMPLETE")
IJ.log(" Input image : " + imp.getTitle())
IJ.log(" Cells found : " + cellCount)
IJ.log(" Labels image: " + labelsImp.getTitle())
IJ.log(" Overlay     : " + (rgbImp != null ? rgbImp.getTitle() : "n/a"))
IJ.log(" Measurements: " + title + "-measurements.csv")
if (gtTitle != null)
    IJ.log(" Comparison  : " + title + "-overlap.csv")
IJ.log("═══════════════════════════════════════")
