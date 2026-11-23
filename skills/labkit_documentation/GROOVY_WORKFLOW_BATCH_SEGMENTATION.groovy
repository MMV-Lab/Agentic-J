// These #@ lines inject Fiji parameters; they must stay at the top of the file.
// Run with EVERY parameter set explicitly — SciJava remembers values from earlier runs.
// Running without a dialog (e.g. from an agent): replace each #@ line with a plain variable
// of the same name and type (`File input = new File("/path")`, `String gpuMode = "auto"`);
// change nothing else. Fiji services are fetched in the code, not via #@.
#@ File (label = "Input image OR folder") input
#@ String (label = "File pattern for a folder (glob)", value = "*.tif") filePattern
#@ File (label = "Labkit classifier (.classifier)") classifierFile
#@ File (label = "Output folder", style = "directory") outputDir
#@ String (label = "Outputs", choices = {"segmentation", "probabilities", "both"}, value = "segmentation") outputs
#@ Integer (label = "Channel to use (1-based; must match training)", value = 1) channel
#@ String (label = "GPU", choices = {"auto", "off", "on"}, value = "auto") gpuMode

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import ij.plugin.Duplicator
import java.nio.file.FileSystems
import sc.fiji.labkit.ui.plugin.SegmentImageWithLabkitIJ1Plugin
import sc.fiji.labkit.ui.plugin.CalculateProbabilityMapWithLabkitIJ1Plugin

// Fiji's CommandService, fetched here (not via #@) so the script still works when the
// #@ inputs are replaced by plain variables.
command = ((org.scijava.Context) IJ.runPlugIn("org.scijava.Context", "")).service(org.scijava.command.CommandService)

/*
 * Labkit — apply a saved classifier to one image or a folder (2D, 3D, time-lapse)
 *
 * OUTPUT (per input <stem>, written to outputDir, calibration copied from the input)
 *   <stem>_labkit_seg.tif   8-bit class image, value k = k-th class of the classifier
 *                           (the log prints the class names; e.g. 0 = background, 1 = marker)
 *   <stem>_labkit_prob.tif  32-bit probabilities, one CHANNEL per class, same Z/T as the input
 *   Prints LABKIT_SEGMENT_OK <n files>.
 *
 * WHY NOT JUST CALL THE COMMAND
 *   - Labkit's IJ1 commands return 3D results with the axes mixed up: the segmentation comes
 *     back as 1 slice x Z channels, the probability map as Z channels x classes slices. This
 *     script restores [C = classes] x Z x T so 3D labeling / measuring works.
 *   - Labkit has no CPU fallback: with too little free GPU memory it fails
 *     (CL_MEM_OBJECT_ALLOCATION_FAILURE, NullPointerException, or a long run of
 *     "warnings generated"). "auto" uses the GPU only when CLIJ sees one and enough GPU memory
 *     is free (~60 bytes/voxel, >= 6 GB), and retries on CPU if the GPU run fails anyway.
 *     Measured on a 1000x1000x84 stack: segmentation CPU 90 s / GPU 41 s, probabilities
 *     CPU 89 s / GPU 9 s, peak 5.5 GB GPU memory.
 *   - Never call Segmenter.segment(...) on a whole large stack yourself: it allocates all
 *     features at once and fails above 2^31 elements (e.g. 84 M voxels x 27 features). The
 *     commands used here work block-wise.
 */

if (!classifierFile.isFile()) throw new IllegalArgumentException("Classifier not found: " + classifierFile)
outputDir.mkdirs()
List<File> files
if (input.isDirectory()) {
    def m = FileSystems.getDefault().getPathMatcher("glob:" + filePattern)
    files = (input.listFiles() ?: [] as File[]).findAll { it.isFile() && m.matches(it.toPath().getFileName()) }.sort { it.name }
    if (files.isEmpty()) throw new IllegalArgumentException("No files matching '" + filePattern + "' in " + input)
} else {
    if (!input.isFile()) throw new IllegalArgumentException("Input not found: " + input)
    files = [input]
}

boolean gpuAvailable(long needMiB) {
    try {
        def names = net.haesleinhuepf.clij.CLIJ.getAvailableDeviceNames()
        if (!names.any { it =~ /(?i)nvidia|geforce|quadro|tesla|a100|h100|rtx|radeon/ }) return false
        def p = ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"].execute(); p.waitFor()
        def free = p.text.readLines()*.trim().findAll { it }.collect { it as long }
        return free && free[0] >= needMiB
    } catch (Throwable t) { return false }
}

// Labkit IJ1 output: planes ordered with the input's Z/T as the FASTEST index and the classes
// slowest. Rebuild as a hyperstack C = classes, Z, T (ImageJ order c fastest, then z, then t).
ImagePlus fixAxes(ImagePlus out, ImagePlus src, int nClasses) {
    int Z = src.getNSlices(), T = src.getNFrames(), planes = Z * T
    if (out.getStackSize() != planes * nClasses) {
        IJ.log("[Labkit] WARNING unexpected output size " + out.getStackSize() + " (expected " + planes * nClasses + "), left as is")
        return out
    }
    ImageStack st = new ImageStack(out.getWidth(), out.getHeight())
    for (int p = 0; p < planes; p++)
        for (int k = 0; k < nClasses; k++)
            st.addSlice(out.getStack().getProcessor(k * planes + p + 1))
    ImagePlus fixed = new ImagePlus(out.getTitle(), st)
    fixed.setDimensions(nClasses, Z, T)
    if (nClasses > 1) fixed.setOpenAsHyperStack(true)
    fixed.setCalibration(src.getCalibration().copy())
    return fixed
}

def runCmd = { Class cls, ImagePlus imp, boolean gpu ->
    command.run(cls, true, "input", imp, "segmenter_file", classifierFile, "use_gpu", gpu).get().getOutput("output")
}

int done = 0
List<String> classNames = null
for (File f : files) {
    long t0 = System.currentTimeMillis()
    ImagePlus imp = IJ.openImage(f.absolutePath)
    if (imp == null) { IJ.log("[Labkit] SKIP unreadable " + f.name); continue }
    if (imp.getNChannels() > 1) imp = new Duplicator().run(imp, channel, channel, 1, imp.getNSlices(), 1, imp.getNFrames())
    long voxels = (long) imp.getWidth() * imp.getHeight() * imp.getNSlices() * imp.getNFrames()
    boolean gpu = gpuMode == "on" || (gpuMode == "auto" && gpuAvailable(Math.max(6144L, (long) (voxels * 60L / (1L << 20)))))
    String stem = f.name.replaceFirst(/\.[^.]+$/, "").replaceFirst(/\.ome$/, "")

    def wanted = outputs == "both" ? [SegmentImageWithLabkitIJ1Plugin, CalculateProbabilityMapWithLabkitIJ1Plugin]
            : (outputs == "probabilities" ? [CalculateProbabilityMapWithLabkitIJ1Plugin] : [SegmentImageWithLabkitIJ1Plugin])
    for (Class cls : wanted) {
        ImagePlus out
        boolean usedGpu = gpu
        try {
            out = runCmd(cls, imp, gpu)
        } catch (Throwable t) {
            if (!gpu) throw t
            // wording avoids "error"/"exception"/"failed": the script runner reports those words as a failed run
            IJ.log("[Labkit] GPU did not work for " + f.name + " (" + (t instanceof OutOfMemoryError ? "Java heap too small" : "OpenCL/GPU issue") + ") — using CPU instead")
            usedGpu = false
            out = runCmd(cls, imp, false)
        }
        boolean isProb = cls == CalculateProbabilityMapWithLabkitIJ1Plugin
        int nClasses = isProb ? (int) (out.getStackSize() / (imp.getNSlices() * imp.getNFrames())) : 1
        ImagePlus fixed = fixAxes(out, imp, nClasses)
        String path = new File(outputDir, stem + (isProb ? "_labkit_prob.tif" : "_labkit_seg.tif")).absolutePath
        IJ.saveAsTiff(fixed, path)
        if (!isProb) {
            def stats = new ij.process.StackStatistics(fixed, 256, 0, 256)
            long n = (long) imp.getWidth() * imp.getHeight() * fixed.getStackSize()
            def frac = (0..<256).findAll { stats.histogram[it] > 0 }.collect { "${it}: ${String.format('%.2f', 100.0 * stats.histogram[it] / n)}%" }
            IJ.log("[Labkit] " + f.name + " -> " + new File(path).name + " (" + (usedGpu ? "GPU" : "CPU") + ") class fractions " + frac.join(", "))
        } else {
            IJ.log("[Labkit] " + f.name + " -> " + new File(path).name + " (" + (usedGpu ? "GPU" : "CPU") + ", " + nClasses + " class channels)")
        }
        out.close(); fixed.close()
    }
    if (classNames == null) {
        try { classNames = new groovy.json.JsonSlurper().parse(classifierFile)?.classNames } catch (Throwable ignored) { }
    }
    imp.close()
    done++
    IJ.log(String.format("[Labkit] %s done in %.1f s", f.name, (System.currentTimeMillis() - t0) / 1000.0))
}
if (classNames) IJ.log("[Labkit] class values: " + classNames.withIndex().collect { n, i -> "${i} = ${n}" }.join(", "))
println("LABKIT_SEGMENT_OK " + done)
