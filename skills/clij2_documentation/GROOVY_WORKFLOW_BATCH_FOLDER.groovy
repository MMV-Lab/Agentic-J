// ============================================================================
// CLIJ2 — batch processing a folder on the GPU with strict memory hygiene.
//
// The GPU has far less memory than the host (e.g. 40 GB on an A100) and CLIJ2
// does NOT free buffers automatically. In a loop, a missing release() is the
// difference between "runs forever" and "CL_MEM_OBJECT_ALLOCATION_FAILURE on
// image 12". The try/finally below is the pattern to copy.
//
// Tested end-to-end on Fiji 2.16.0/1.54p, CLIJ2 2.5.3.5, NVIDIA A100.
// ============================================================================
import net.haesleinhuepf.clij2.CLIJ2
import ij.IJ
import ij.measure.ResultsTable

// ── Parameters ───────────────────────────────────────────────────────────────
def INPUT_DIR    = "/data/benchmark_images"
def OUTPUT_DIR   = "/data/clij2_batch"
def FILE_PATTERN = ~/(?i).*\.(tif|tiff|png|jpg|gif)$/   // Groovy regex, not a glob
def MAX_FILES    = 5                                    // 0 = no limit
def SPOT_SIGMA   = 3.0
def OUTLINE_SIGMA= 1.0

new File(OUTPUT_DIR).mkdirs()
def clij2 = CLIJ2.getInstance()
clij2.clear()
IJ.log("GPU: " + clij2.getGPUName())

def files = new File(INPUT_DIR).listFiles()
                .findAll { it.isFile() && it.name ==~ FILE_PATTERN }
                .sort { it.name }
if (MAX_FILES > 0 && files.size() > MAX_FILES) files = files[0..<MAX_FILES]
IJ.log("processing " + files.size() + " file(s) from " + INPUT_DIR)

def summary = new ResultsTable()
int failed = 0

files.each { f ->
    def imp = null, input = null, labels = null, clean = null
    try {
        imp = IJ.openImage(f.getAbsolutePath())
        if (imp == null) { IJ.log("SKIP (not readable): " + f.name); failed++; return }
        // RGB images must be converted — CLIJ2 handles single-channel data only.
        if (imp.getType() == ij.ImagePlus.COLOR_RGB) IJ.run(imp, "8-bit", "")

        input  = clij2.push(imp)
        labels = clij2.create(input.getDimensions(), clij2.Float)
        clij2.voronoiOtsuLabeling(input, labels, SPOT_SIGMA, OUTLINE_SIGMA)

        clean = clij2.create(labels)
        clij2.excludeLabelsOnEdges(labels, clean)

        int count = (int) clij2.maximumOfAllPixels(clean)
        double mean_int = clij2.meanOfAllPixels(input)

        IJ.saveAs(clij2.pull(clean), "Tiff", OUTPUT_DIR + "/" + f.name.replaceFirst(/\.[^.]+$/, "") + "_labels.tif")

        summary.incrementCounter()
        summary.addValue("file", f.name)
        summary.addValue("objects", count)
        summary.addValue("mean_intensity", mean_int)
        IJ.log(f.name + " → " + count + " objects")
    } catch (Exception e) {
        // One bad image must not abort the batch.
        failed++
        IJ.log("FAILED " + f.name + ": " + e.getMessage())
    } finally {
        // Release inside the loop — this is the whole point.
        [input, labels, clean].each { if (it != null) clij2.release(it) }
        if (imp != null) imp.close()
    }
}

summary.save(OUTPUT_DIR + "/batch_summary.csv")
IJ.log(clij2.reportMemory())     // must read "contains 0 images" here
clij2.clear()

IJ.log("SUMMARY processed=" + summary.size() + " failed=" + failed + " out=" + OUTPUT_DIR)
println("SUMMARY processed=" + summary.size() + " failed=" + failed)
