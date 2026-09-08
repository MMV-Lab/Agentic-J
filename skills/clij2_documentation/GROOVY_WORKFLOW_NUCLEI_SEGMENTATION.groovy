// ============================================================================
// CLIJ2 — GPU nuclei/blob segmentation, counting and measurement (2D)
//
// Pattern:  push → background removal → Voronoi-Otsu labeling → clean up
//           → measure → pull/save → release
//
// Tested end-to-end on Fiji 2.16.0/1.54p, CLIJ2 2.5.3.5, NVIDIA A100 (OpenCL 1.2).
// Popup-free: no #@ script parameters, no IJ.run() dialogs, no window grabbing.
// ============================================================================
import net.haesleinhuepf.clij2.CLIJ2
import ij.IJ
import ij.measure.ResultsTable

// ── Parameters (edit these; do NOT use #@ parameters — they open a dialog) ────
def IMAGE_PATH   = "https://imagej.net/images/blobs.gif"  // or "/data/my_image.tif"
def OUTPUT_DIR   = "/data/clij2_nuclei"
def BACKGROUND_R = 15      // top-hat radius in px; must exceed object radius
def SPOT_SIGMA   = 3.0     // Voronoi-Otsu: blur for seed detection (bigger = fewer seeds)
def OUTLINE_SIGMA= 1.0     // Voronoi-Otsu: blur for the outline/threshold step
def MIN_AREA     = 50      // discard labels smaller than this (px)
def MAX_AREA     = 1e9

new File(OUTPUT_DIR).mkdirs()

// ── 1. GPU handle. getInstance() picks the fastest available OpenCL device. ──
def clij2 = CLIJ2.getInstance()
clij2.clear()                       // start from a clean GPU memory state
IJ.log("GPU: " + clij2.getGPUName())

// ── 2. Push the image to GPU memory ──────────────────────────────────────────
// CLIJ2 reads RAW PIXEL VALUES: display LUTs (incl. inverting LUTs) and spatial
// calibration are ignored, so no LUT fix-up is needed before thresholding.
def imp = IJ.openImage(IMAGE_PATH)
if (imp == null) throw new RuntimeException("could not open " + IMAGE_PATH)
def input = clij2.push(imp)

// ── 3. Remove uneven background (white top-hat) ──────────────────────────────
def background_subtracted = clij2.create(input)
clij2.topHatBox(input, background_subtracted, BACKGROUND_R, BACKGROUND_R, 0)

// ── 4. Segment: Voronoi-Otsu labeling (blur → Otsu → seeded Voronoi split) ───
//     One call replaces threshold + distance map + maxima + watershed.
def labels = clij2.create(input.getDimensions(), clij2.Float)
clij2.voronoiOtsuLabeling(background_subtracted, labels, SPOT_SIGMA, OUTLINE_SIGMA)

// ── 5. Clean up: drop objects touching the border, then filter by size ───────
def labels_no_edge = clij2.create(labels)
clij2.excludeLabelsOnEdges(labels, labels_no_edge)

def labels_filtered = clij2.create(labels)
clij2.excludeLabelsOutsideSizeRange(labels_no_edge, labels_filtered, MIN_AREA, MAX_AREA)
// excludeLabels* renumbers 1..N itself; call closeIndexGapsInLabelMap() only
// after ops that leave holes in the numbering (e.g. replaceIntensities).

// ── 6. Count and measure — all on the GPU ───────────────────────────────────
int count = (int) clij2.maximumOfAllPixels(labels_filtered)   // labels are 1..N
IJ.log("objects after cleanup: " + count)

// statisticsOfLabelledPixels(intensity_image, label_map, ResultsTable):
// one row per label, 36 columns (IDENTIFIER, BOUNDING_BOX_*, PIXEL_COUNT,
// MINIMUM/MAXIMUM/MEAN/STANDARD_DEVIATION_INTENSITY, MASS_CENTER_*,
// CENTROID_*, SUM_DISTANCE_TO_*, MAXIMUM_DISTANCE_TO_*, AVERAGE_DISTANCE_TO_*).
def rt = new ResultsTable()
clij2.statisticsOfLabelledPixels(input, labels_filtered, rt)
rt.save(OUTPUT_DIR + "/measurements.csv")

// Aggregate straight from the table:
double mean_area = 0
for (int i = 0; i < rt.size(); i++) mean_area += rt.getValue("PIXEL_COUNT", i)
mean_area = rt.size() > 0 ? mean_area / rt.size() : 0
IJ.log("mean area (px): " + mean_area)

// ── 7. Pull results back to ImageJ and save ─────────────────────────────────
// pull() returns the raw values; a label map comes back as 32-bit.
def label_imp = clij2.pull(labels_filtered)
label_imp.setTitle("labels")
IJ.saveAs(label_imp, "Tiff", OUTPUT_DIR + "/labels.tif")

// ── 8. Free GPU memory — every create()/push() must be released ─────────────
clij2.release(input)
clij2.release(background_subtracted)
clij2.release(labels)
clij2.release(labels_no_edge)
clij2.release(labels_filtered)
clij2.clear()          // belt-and-braces: frees anything still held

IJ.log("SUMMARY count=" + count + " mean_area=" + mean_area + " out=" + OUTPUT_DIR)
println("SUMMARY count=" + count + " mean_area=" + mean_area)
