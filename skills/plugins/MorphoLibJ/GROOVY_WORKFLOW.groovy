/**
 * MorphoLibJ — Complete Segmentation & Analysis Workflow
 *
 * PURPOSE:
 *   Demonstrates the full MorphoLibJ pipeline for segmenting touching objects in a
 *   fluorescence image and measuring their morphological properties.
 *   Steps: gradient → extended minima → marker-controlled watershed → label analysis.
 */

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.measure.ResultsTable

// ─────────────────────────────────────────────
//  PARAMETERS  ← adjust these for your data
// ─────────────────────────────────────────────
int    GRADIENT_RADIUS = 2
int    DYNAMIC         = 10
int    CONNECTIVITY    = 4
int    MIN_AREA        = 50
boolean CALCULATE_DAMS = true
// ─────────────────────────────────────────────

def safeRun = { ImagePlus target, String command, String options ->
    try {
        if (target != null) IJ.run(target, command, options)
        else IJ.run(command, options)
        return true
    } catch (RuntimeException re) {
        IJ.log("[WARN] Command failed: " + command + " -> " + re.getMessage())
        return false
    }
}

// ── 0. Get or load the input image ────────────────────────────────────────────
ImagePlus imp = WindowManager.getCurrentImage()
if (imp == null) {
    IJ.log("[MorphoLibJ workflow] No image open — loading Fiji Blobs sample.")
    IJ.run("Blobs (25K)")
    imp = WindowManager.getCurrentImage()
    if (imp == null) {
        IJ.error("Could not load sample image. Please open an image first.")
        return
    }
    imp.show()
}

String title    = imp.getTitle().replaceAll("\\.[^.]+$", "")
String savePath = imp.getOriginalFileInfo()?.directory ?: IJ.getDirectory("imagej")
IJ.log("─── MorphoLibJ workflow starting on: " + imp.getTitle())
IJ.log("─── Output will be saved to: " + savePath)

// Work on a duplicate to preserve original data
ImagePlus procImp = imp.duplicate()
if (procImp == null) {
    IJ.error("Could not duplicate input image. Aborting.")
    return
}
procImp.setTitle(title + "-processing")

// ── 1. Ensure image is 8-bit or 16-bit grayscale ──────────────────────────────
if (procImp.getType() == ImagePlus.COLOR_RGB) {
    IJ.log("[Step 1] Converting RGB to 8-bit grayscale.")
    IJ.run(procImp, "8-bit", "")
}
if (procImp.getType() == ImagePlus.GRAY32) {
    IJ.log("[Step 1] Converting 32-bit to 16-bit.")
    IJ.run(procImp, "16-bit", "")
}

// ── 2. Compute morphological gradient ─────────────────────────────────────────
IJ.log("[Step 2] Computing morphological gradient (radius=" + GRADIENT_RADIUS + ").")
IJ.run(procImp, "Duplicate...", "title=[" + title + "-working]")
ImagePlus workImp = WindowManager.getImage(title + "-working")
if (workImp == null) {
    IJ.error("Duplicate failed. Aborting.")
    return
}

if (!safeRun(workImp, "Morphological Filters", "operation=Gradient element=Disk radius=" + GRADIENT_RADIUS)) {
    IJ.error("Gradient computation failed. Aborting.")
    return
}
ImagePlus gradImp = WindowManager.getCurrentImage()
if (gradImp == null || gradImp == workImp) {
    IJ.error("Gradient computation failed. Aborting.")
    return
}
gradImp.setTitle(title + "-gradient")
workImp.close()
procImp.close()
IJ.log("[Step 2] Gradient image created: " + gradImp.getTitle())

// ── 3. Find extended minima ───────────────────────────────────────────────────
IJ.log("[Step 3] Finding extended minima (dynamic=" + DYNAMIC + ", connectivity=" + CONNECTIVITY + ").")
if (!safeRun(gradImp, "Extended Min & Max", "operation=[Extended Minima] connectivity=" + CONNECTIVITY + " dynamic=" + DYNAMIC)) {
    IJ.error("Extended Minima failed. Aborting.")
    return
}
ImagePlus minimaImp = WindowManager.getCurrentImage()
if (minimaImp == null || minimaImp == gradImp) {
    IJ.error("Extended Minima failed. Aborting.")
    return
}
minimaImp.setTitle(title + "-minima")

// ── 4. Label connected components of minima ───────────────────────────────────
IJ.log("[Step 4] Labeling minima with connected components.")
if (!safeRun(minimaImp, "Connected Components Labeling", "connectivity=" + CONNECTIVITY + " type=[16 bits]")) {
    IJ.error("Connected components labeling failed. Aborting.")
    return
}
ImagePlus markerImp = WindowManager.getCurrentImage()
if (markerImp == null || markerImp == minimaImp) {
    IJ.error("Connected components labeling failed. Aborting.")
    return
}
markerImp.setTitle(title + "-markers")
minimaImp.close()

// ── 5. Marker-controlled watershed ────────────────────────────────────────────
IJ.log("[Step 5] Running marker-controlled watershed.")
String damsFlag     = CALCULATE_DAMS ? "calculate " : ""
String diagonalFlag = (CONNECTIVITY == 8) ? "use" : ""

if (!safeRun(null, "Marker-controlled Watershed",
    "input=" + gradImp.getTitle() + " marker=" + markerImp.getTitle() + " mask=None " + damsFlag + diagonalFlag)) {
    IJ.error("Watershed failed. Aborting.")
    return
}

ImagePlus labelsImp = WindowManager.getCurrentImage()
if (labelsImp == null) {
    IJ.error("Watershed failed — no output image created. Aborting.")
    return
}
labelsImp.setTitle(title + "-labels")
IJ.log("[Step 5] Watershed completed. Labels image: " + labelsImp.getTitle())

// Clean up intermediate images
gradImp.close()
markerImp.close()

// ── 6. Post-processing ────────────────────────────────────────────────────────
IJ.log("[Step 6] Removing border labels.")
safeRun(labelsImp, "Remove Border Labels", "")

IJ.log("[Step 6] Removing labels smaller than " + MIN_AREA + " px².")
safeRun(labelsImp, "Label Size Opening", "min=" + MIN_AREA)

IJ.log("[Step 6] Remapping labels (removing gaps after removal).")
safeRun(labelsImp, "Remap Labels", "")

// ── 7. Create coloured overlay ────────────────────────────────────────────────
IJ.log("[Step 7] Creating coloured overlay.")
imp.show()
labelsImp.show()
safeRun(labelsImp, "Set Label Map", "colormap=Golden_angle background=Black shuffle")
if (safeRun(labelsImp, "Labels to RGB", "colormap=Golden_angle background=Black shuffle")) {
    ImagePlus rgbImp = WindowManager.getCurrentImage()
    if (rgbImp != null && rgbImp != labelsImp) {
        rgbImp.setTitle(title + "-overlay")
        IJ.log("[Step 7] RGB overlay created.")
    }
}

// ── 8. Measure region properties ──────────────────────────────────────────────
IJ.log("[Step 8] Measuring region properties.")
labelsImp.show()

safeRun(labelsImp, "Analyze Regions",
    "area perimeter circularity inertia_ellipse ellipse_elong convexity " +
    "max_feret oriented_box oriented_box_elong geodesic_diameter tortuosity " +
    "max_inscribed_disc geodesic_elong")

ResultsTable rt = ResultsTable.getResultsTable()
if (rt != null && rt.size() > 0) {
    IJ.log("[Step 8] Measured " + rt.size() + " regions.")
    String csvPath = savePath + title + "-measurements.csv"
    try {
        rt.save(csvPath)
        IJ.log("[Step 8] Results saved to: " + csvPath)
    } catch (Exception e) {
        IJ.log("[Step 8] WARNING: Could not save CSV: " + e.getMessage())
    }
} else {
    IJ.log("[Step 8] WARNING: Results table is empty — check that the label image has labels.")
}

// ── 9. Save label image as TIFF ───────────────────────────────────────────────
String labelPath = savePath + title + "-labels.tif"
try {
    IJ.saveAsTiff(labelsImp, labelPath)
    IJ.log("[Step 9] Label image saved to: " + labelPath)
} catch (Exception e) {
    IJ.log("[Step 9] WARNING: Could not save label image: " + e.getMessage())
}

IJ.log("─── MorphoLibJ workflow completed successfully.")
IJ.log("    Labels image:  " + labelsImp.getTitle())
IJ.log("    Regions found: " + (rt != null ? rt.size() : "unknown"))
IJ.log("    Results CSV:   " + labelPath.replace("-labels.tif", "-measurements.csv"))
