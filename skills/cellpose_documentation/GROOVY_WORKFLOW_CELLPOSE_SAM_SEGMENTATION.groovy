#@ Context ctx
/*
 * Cellpose-SAM (cpsam) — single-image instance segmentation via the BIOP wrapper
 * =============================================================================
 * Uses the CellposeSAM command + the cellpose4 conda env. Returns the label image
 * in-process as cp.cellpose_imp. No TrackMate, no /tmp scraping.
 *
 * WHEN TO USE THIS (vs GROOVY_WORKFLOW_CELLPOSE_SEGMENTATION.groovy):
 *   - Use THIS for the cpsam (Cellpose-SAM, Cellpose 4) model — newest, most general,
 *     highest accuracy. Best with a GPU.
 *   - Use the OTHER workflow for the v3 models (cyto3, nuclei, cyto2, tissuenet, ...),
 *     which are much faster on CPU.
 *
 * KEY DIFFERENCES from the v3 workflow (do not copy v3 fields here):
 *   - command  = CellposeSAM       (NOT Cellpose)
 *   - env_path = /opt/conda/envs/cellpose4   (cellpose 4.1.1, NOT the v3 env)
 *   - model    = "cpsam"
 *   - NO ch1 / ch2 fields          (declared on the v3 Cellpose class only -> MissingPropertyException)
 *   - LEAVE diameter ALONE         (inherited from the shared parent; the wrapper always forwards
 *                                   "--diameter 30.0". Cellpose 4 uses it to rescale to its 30 px
 *                                   training diameter, so the default is a no-op -- but a non-30
 *                                   value DOES change the result. It is not ignored.)
 *
 * FLAGS: `additional_flags` is split on COMMAS ONLY. Every flag AND every value is its own
 * comma-separated token. A space-separated string becomes a single argv token; cellpose exits
 * with "unrecognized arguments", cellpose_imp comes back null, and the next access throws
 * NullPointerException on "cellpose_t_imp". See SCRIPT_API.md.
 *
 * BRIGHT-FIELD: cellpose expects objects BRIGHTER than the background. If your background is
 * bright (dark cells), invert in ImageJ first: IJ.run(imp, "Invert", ""). You CANNOT use
 * "--invert" here -- it is deprecated and silently ignored in cellpose >= 4.0.1.
 *
 * Outputs:
 *   <outputDir>/cpsam_labels.tif    16-bit instance label image (0 = bg, 1..N = objects)
 *   <outputDir>/cpsam_objects.csv   per-label area (px) + centroid
 *
 * PERFORMANCE: the SAM transformer is very slow on CPU (many minutes even for a small
 * image). Add "--use_gpu" to flags on a GPU deployment. On CPU-only, prefer the v3
 * workflow with cyto3/nuclei unless you specifically need cpsam accuracy.
 *
 * Requires (already configured in this image): BIOP wrapper jar on the classpath,
 * cellpose4 conda env, and BASH_ENV=/opt/conda/etc/profile.d/conda.sh so the wrapper's
 * `conda activate` works (set in src/imagentj/imagej_context.py).
 */

import ch.epfl.biop.wrappers.cellpose.ij2commands.CellposeSAM
import ij.IJ
import ij.ImagePlus
import ij.measure.ResultsTable
import ij.process.ImageConverter

// ── CONFIG (edit these) ──────────────────────────────────────────────────────
def imagePath = "/app/data/.../input.tif"          // "" to use the currently active image
def outputDir = "/app/data/.../cpsam_out"
def envPath   = "/opt/conda/envs/cellpose4"         // cellpose 4.1.1 (cpsam)
// COMMA-separated flags AND values — never spaces. "" forces CPU.
// To tune: lower cellprob_threshold => more/larger masks; raise flow_threshold => looser QC (more masks).
//   "--use_gpu, --cellprob_threshold, -1.0, --flow_threshold, 0.4"   <- correct
//   "--use_gpu --cellprob_threshold -1.0 --flow_threshold 0.4"       <- WRONG, yields null labels
def flags     = "--use_gpu"                         // GPU when present; cellpose falls back to CPU automatically
// ─────────────────────────────────────────────────────────────────────────────

boolean success = false
try {
    new File(outputDir).mkdirs()

    def imp = (imagePath == null || imagePath.isEmpty()) ? IJ.getImage() : IJ.openImage(imagePath)
    if (imp == null) { IJ.log("[ERROR] could not load input image"); println("FINAL STATUS: FAILURE"); return }
    IJ.log("[INFO] input: ${imp.getTitle()} ${imp.getWidth()}x${imp.getHeight()} bitDepth=${imp.getBitDepth()}")

    // ── run Cellpose-SAM ─────────────────────────────────────────────────────
    def cp = new CellposeSAM()
    ctx.inject(cp)
    cp.imp              = imp
    cp.env_path         = new File(envPath)
    cp.env_type         = "conda"
    cp.model            = "cpsam"
    cp.additional_flags = flags
    cp.verbose          = Boolean.TRUE
    // NOTE: cp.ch1 / cp.ch2 don't exist on CellposeSAM (setting them throws). Leave cp.diameter
    // at its default — it is forwarded as "--diameter 30.0" and a non-30 value rescales the image.
    IJ.log("[INFO] running Cellpose-SAM (cpsam, env=${envPath}) — VERY slow on CPU, GPU recommended")
    cp.run()

    def labels = cp.cellpose_imp
    if (labels == null) { IJ.log("[ERROR] cellpose_imp is null — see cellpose log above"); println("FINAL STATUS: FAILURE"); return }

    // ── tidy the label image ─────────────────────────────────────────────────
    // Labels come back 32-bit float (values 1..N). Convert to 16-bit WITHOUT scaling,
    // otherwise ImageJ rescales the values to 0..65535 and destroys the label IDs.
    if (labels.getBitDepth() == 32) {
        ImageConverter.setDoScaling(false)
        IJ.run(labels, "16-bit", "")
        ImageConverter.setDoScaling(true)
    }
    labels.setCalibration(imp.getCalibration())
    labels.setTitle("cpsam_instance_labels")

    // ── per-label measurement (MorphoLibJ-free: single pass over pixels) ──────
    def ip = labels.getProcessor()
    int W = labels.getWidth(), H = labels.getHeight()
    def area = [:].withDefault { 0L }
    def sumX = [:].withDefault { 0.0d }
    def sumY = [:].withDefault { 0.0d }
    int maxLabel = 0
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        int v = (int) ip.getf(x, y)
        if (v <= 0) continue
        area[v] = area[v] + 1L
        sumX[v] = sumX[v] + x
        sumY[v] = sumY[v] + y
        if (v > maxLabel) maxLabel = v
    }
    def cal = imp.getCalibration()
    def rt = new ResultsTable()
    area.keySet().sort().each { int lbl ->
        long a = area[lbl]
        rt.incrementCounter()
        rt.addValue("label", lbl)
        rt.addValue("area_px", a)
        rt.addValue("area_cal", a * cal.pixelWidth * cal.pixelHeight)
        rt.addValue("centroid_x", sumX[lbl] / a)
        rt.addValue("centroid_y", sumY[lbl] / a)
    }

    IJ.saveAsTiff(labels, "${outputDir}/cpsam_labels.tif")
    rt.save("${outputDir}/cpsam_objects.csv")
    IJ.log("[RESULT] objects = ${maxLabel}")
    IJ.log("[INFO] wrote ${outputDir}/cpsam_labels.tif and cpsam_objects.csv")
    labels.show()
    success = true

} catch (Throwable t) {
    IJ.log("[ERROR] ${t}")
    t.printStackTrace()
}

println(success ? "FINAL STATUS: SUCCESS" : "FINAL STATUS: FAILURE")
