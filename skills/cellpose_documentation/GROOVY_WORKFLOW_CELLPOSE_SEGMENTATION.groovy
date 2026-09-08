#@ Context ctx
/*
 * Cellpose (BIOP wrapper) — single-image instance segmentation
 * ============================================================
 * Direct path: runs Cellpose via ch.epfl.biop.wrappers.cellpose and reads the
 * label image back in-process as cp.cellpose_imp. No TrackMate, no /tmp scraping.
 *
 * Verified: cyto3 on a 1024x1024 DAPI crop (CPU) -> 97 instance labels.
 *
 * FLAGS: `additional_flags` is split on COMMAS ONLY. Every flag AND every value is its own
 * comma-separated token. A space-separated string becomes a single argv token; cellpose exits
 * with "unrecognized arguments", cellpose_imp comes back null, and the next access throws
 * NullPointerException on "cellpose_t_imp". See SCRIPT_API.md.
 *
 * BRIGHT-FIELD: cellpose expects objects BRIGHTER than the background. If your background is
 * bright (dark cells), invert first: IJ.run(imp, "Invert", "") -- or add "--invert" to flags
 * (v3 only; it is a silent no-op on cpsam).
 *
 * Outputs:
 *   <outputDir>/cellpose_labels.tif   16-bit instance label image (0 = bg, 1..N = objects)
 *   <outputDir>/cellpose_objects.csv  per-label area (px) + centroid
 *
 * Requires (already configured in this image):
 *   - BIOP wrapper jar on the classpath (bundled in /opt/Fiji.app/jars)
 *   - cellpose conda env at envPath with a working tifffile (>=2025)
 *   - BASH_ENV=/opt/conda/etc/profile.d/conda.sh so 'conda activate' works
 *     (set in src/imagentj/imagej_context.py; export it yourself if running Fiji standalone)
 */

import ch.epfl.biop.wrappers.cellpose.ij2commands.Cellpose
import ij.IJ
import ij.ImagePlus
import ij.measure.ResultsTable
import ij.process.ImageConverter

// ── CONFIG (edit these) ──────────────────────────────────────────────────────
def imagePath = "/app/data/.../input.tif"          // "" to use the currently active image
def outputDir = "/app/data/.../cellpose_out"
def envPath   = "/opt/conda/envs/cellpose"          // cellpose v3.1.1.2 (use cellpose4 + CellposeSAM for cpsam)
def model     = "cyto3"                             // or "nucleitorch_0", "cyto2", "tissuenet_cp3", ... (see SCRIPT_API.md)
float diameter = 30f                                // expected object diameter in px; 0f = auto (cyto* only)
int   ch1     = 0                                   // channel to segment (0 = grayscale)
int   ch2     = 0                                   // optional nucleus channel (0 = none)
// COMMA-separated flags AND values — never spaces. "" forces CPU.
// To tune: lower cellprob_threshold => more/larger masks; raise flow_threshold => looser QC (more masks).
//   "--use_gpu, --cellprob_threshold, -1.0, --flow_threshold, 0.4"   <- correct
//   "--use_gpu --cellprob_threshold -1.0 --flow_threshold 0.4"       <- WRONG, yields null labels
def   flags   = "--use_gpu"                         // GPU when present; cellpose falls back to CPU automatically
// ─────────────────────────────────────────────────────────────────────────────

boolean success = false
try {
    new File(outputDir).mkdirs()

    def imp = (imagePath == null || imagePath.isEmpty()) ? IJ.getImage() : IJ.openImage(imagePath)
    if (imp == null) { IJ.log("[ERROR] could not load input image"); println("FINAL STATUS: FAILURE"); return }
    IJ.log("[INFO] input: ${imp.getTitle()} ${imp.getWidth()}x${imp.getHeight()} bitDepth=${imp.getBitDepth()}")

    // ── run Cellpose ─────────────────────────────────────────────────────────
    def cp = new Cellpose()
    ctx.inject(cp)
    cp.imp              = imp
    cp.env_path         = new File(envPath)
    cp.env_type         = "conda"
    cp.model            = model
    cp.diameter         = diameter
    cp.ch1              = ch1
    cp.ch2              = ch2
    cp.additional_flags = flags
    cp.verbose          = Boolean.TRUE
    IJ.log("[INFO] running Cellpose: model=${model} diameter=${diameter} env=${envPath} (CPU may take minutes)")
    cp.run()

    def labels = cp.cellpose_imp
    if (labels == null) { IJ.log("[ERROR] cellpose_imp is null — see cellpose log above"); println("FINAL STATUS: FAILURE"); return }

    // ── tidy the label image ─────────────────────────────────────────────────
    // Labels come back 32-bit float (values 1..N). Convert to 16-bit WITHOUT scaling,
    // otherwise ImageJ rescales the values to 0..65535 and destroys the label IDs.
    if (labels.getBitDepth() == 32) {
        ImageConverter.setDoScaling(false)
        IJ.run(labels, "16-bit", "")
        ImageConverter.setDoScaling(true)                          // restore global default
    }
    labels.setCalibration(imp.getCalibration())                    // cellpose drops calibration
    labels.setTitle("cellpose_instance_labels")

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

    IJ.saveAsTiff(labels, "${outputDir}/cellpose_labels.tif")
    rt.save("${outputDir}/cellpose_objects.csv")
    IJ.log("[RESULT] objects = ${maxLabel}")
    IJ.log("[INFO] wrote ${outputDir}/cellpose_labels.tif and cellpose_objects.csv")
    labels.show()
    success = true

} catch (Throwable t) {
    IJ.log("[ERROR] ${t}")
    t.printStackTrace()
}

println(success ? "FINAL STATUS: SUCCESS" : "FINAL STATUS: FAILURE")
