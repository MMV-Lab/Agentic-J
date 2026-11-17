// These #@ lines inject Fiji parameters; they must stay at the top of the file.
// Run with EVERY parameter set explicitly — SciJava remembers values from earlier runs.
// Running without a dialog (e.g. from an agent): replace each #@ line with a plain variable
// of the same name and type (`File input = new File("/path")`, `String gpuMode = "auto"`);
// change nothing else. Fiji services are fetched in the code, not via #@.
#@ File (label = "Image to train on (2D or 3D, calibrated)") imageFile
#@ String (label = "Label source", choices = {"label image", "ROI set (.zip)", "ROI Manager"}, value = "label image") labelSource
#@ String (label = "Label image (0 = unlabeled, 1..N = classes) or ROI set .zip", value = "") labelFile
#@ String (label = "Class names, in label-value order (1,2,...)", value = "background,marker") classNames
#@ Integer (label = "Channel to use (1-based)", value = 1) channel
#@ Integer (label = "Line ROI width (px) — for 'ROI Manager'", value = 3) lineWidth
#@ String (label = "GPU", choices = {"auto", "off", "on"}, value = "auto") gpuMode
#@ File (label = "Output classifier (.classifier)", style = "save") classifierFile

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import ij.gui.Line
import ij.gui.PolygonRoi
import ij.gui.Roi
import ij.plugin.Duplicator
import ij.plugin.frame.RoiManager
import ij.io.RoiDecoder
import java.util.zip.ZipFile
import ij.process.ByteProcessor
import net.imglib2.img.ImagePlusAdapter
import net.imglib2.img.array.ArrayImgs
import net.imglib2.img.display.imagej.ImageJFunctions
import net.imglib2.roi.Regions
import net.imglib2.type.logic.BitType
import net.imglib2.util.ValuePair
import net.imglib2.view.Views
import sc.fiji.labkit.ui.labeling.Labeling
import sc.fiji.labkit.ui.segmentation.weka.TrainableSegmentationSegmenter

// Fiji's SciJava context, fetched here (not via #@) so the script still works when the
// #@ inputs are replaced by plain variables.
context = (org.scijava.Context) IJ.runPlugIn("org.scijava.Context", "")

/*
 * Labkit — train a pixel classifier WITHOUT painting in the Labkit window
 *
 * Use when the labels already exist as
 *   - a sparse label image (same X/Y/Z size as the image; 0 = unlabeled, 1..N = class),
 *     e.g. strokes the user painted in Fiji, a Labkit "Export selected Label as Bitmap",
 *     or labels derived from another tool; or
 *   - ROIs whose NAME starts with a class name (e.g. "marker-1", "background 3"), either in an
 *     ROI set .zip (ROI Manager > More > Save...; works headless) or in the open ROI Manager. Lines are drawn `lineWidth` px wide, areas are filled. In a z-stack
 *     each ROI goes to its own slice (add ROIs with the stack slice set, so they carry a
 *     position); ROIs without a position are applied to slice 1.
 *
 * WHAT LABKIT DOES WITH THE IMAGE
 *   Features (raw, Gaussian, difference of Gaussians, gradient, Laplacian, Hessian;
 *   sigma 1-8) are computed in 2D or 3D automatically from the image dimensionality, and
 *   the voxel size is taken from the image CALIBRATION (relative to X). A z-stack with
 *   0.32 x 0.32 x 0.54 µm voxels therefore gets 3D filters stretched 1.65x less in Z.
 *   Check the calibration first (Image > Properties): a wrong Z step distorts the filters.
 *
 * OUTPUT
 *   classifierFile (.classifier, JSON) — usable by GROOVY_WORKFLOW_BATCH_SEGMENTATION.groovy,
 *   by the Labkit window (Segmentation > Open Classifier) and by the Labkit macro commands.
 *   Segmentation value k (0-based) = k-th class name. Prints LABKIT_TRAIN_OK <classes>.
 *
 * GPU
 *   "auto" uses the GPU only if CLIJ sees a GPU and >= 6 GB GPU memory is free, and falls back
 *   to CPU if GPU training fails. Labkit has no CPU fallback of its own: with too little free
 *   GPU memory it fails (CL_MEM_OBJECT_ALLOCATION_FAILURE / NullPointerException / endless
 *   "warnings generated"). For training, the GPU is rarely faster (kernel compilation); "off"
 *   is a safe default.
 */

List<String> classes = classNames.split(",").collect { it.trim() }.findAll { it }
if (classes.size() < 2) throw new IllegalArgumentException("Need at least two class names, got: " + classNames)
if (!imageFile.exists()) throw new IllegalArgumentException("Image not found: " + imageFile)
classifierFile.parentFile?.mkdirs()

ImagePlus imp = IJ.openImage(imageFile.absolutePath)
if (imp == null) throw new IllegalStateException("Could not open " + imageFile)
if (imp.getNChannels() > 1) {
    imp = new Duplicator().run(imp, channel, channel, 1, imp.getNSlices(), 1, imp.getNFrames())
}
def cal = imp.getCalibration()
int W = imp.getWidth(), H = imp.getHeight(), Z = imp.getNSlices(), T = imp.getNFrames()
IJ.log(String.format("[Labkit] image %dx%dx%d (t=%d), voxel %.4g x %.4g x %.4g %s", W, H, Z, T,
        cal.pixelWidth, cal.pixelHeight, cal.pixelDepth, cal.getUnit()))
if (T > 1) throw new IllegalArgumentException("Train on a single time point (duplicate one frame first).")

// ---- label image (values 0..N) --------------------------------------------------------------
ImagePlus labels
if (labelSource == "label image") {
    labels = IJ.openImage(labelFile)
    if (labels == null) throw new IllegalArgumentException("Label image not found: " + labelFile)
    if (labels.getWidth() != W || labels.getHeight() != H || labels.getStackSize() != Z)
        throw new IllegalArgumentException("Label image size ${labels.getWidth()}x${labels.getHeight()}x${labels.getStackSize()} " +
                "does not match image ${W}x${H}x${Z}")
} else {
    List<Roi> rois = []
    if (labelSource == "ROI set (.zip)") {
        def zf = new ZipFile(labelFile)
        zf.entries().findAll { it.name.endsWith(".roi") }.each { e ->
            Roi r = new RoiDecoder(zf.getInputStream(e).bytes, e.name).getRoi()
            if (r != null) { if (!r.getName()) r.setName(e.name.replaceFirst(/\.roi$/, "")); rois << r }
        }
        zf.close()
    } else {
        def rm = RoiManager.getInstance()
        if (rm == null) throw new IllegalArgumentException("No ROI Manager open — save the ROIs as a .zip and use 'ROI set (.zip)'")
        rois = rm.getRoisAsArray() as List
    }
    if (rois.isEmpty()) throw new IllegalArgumentException("No ROIs found")
    ImageStack st = new ImageStack(W, H)
    for (int z = 0; z < Z; z++) st.addSlice(new ByteProcessor(W, H))
    int used = 0
    for (Roi roi : rois) {
        String name = (roi.getName() ?: "").toLowerCase()
        int cls = classes.findIndexOf { name.startsWith(it.toLowerCase()) } + 1
        if (cls == 0) { IJ.log("[Labkit] skipping ROI '" + roi.getName() + "' (name matches no class)"); continue }
        int z = roi.getZPosition() > 0 ? roi.getZPosition() : (roi.getPosition() > 0 ? roi.getPosition() : 1)
        def ip = st.getProcessor(Math.min(z, Z)); ip.setValue(cls)
        if (roi.isLine()) { ip.setLineWidth(lineWidth); ip.draw(roi) } else ip.fill(roi)
        used++
    }
    labels = new ImagePlus("labels", st)
    IJ.log("[Labkit] rasterized " + used + " ROI(s) into a label image")
}

// ---- Labeling: one bit mask per class -------------------------------------------------------
long[] dims = Z > 1 ? [W, H, Z] as long[] : [W, H] as long[]
def labelImg = ImageJFunctions.wrapReal(labels)
Map<String, Object> regions = new LinkedHashMap<>()
List<Integer> counts = []
classes.eachWithIndex { String name, int i ->
    def mask = ArrayImgs.bits(dims)
    def lc = Views.flatIterable(labelImg).cursor(); def mc = Views.flatIterable(mask).cursor(); long n = 0
    while (lc.hasNext()) { boolean on = ((int) lc.next().getRealDouble()) == i + 1; def m = mc.next(); if (on) { m.set(true); n++ } }
    counts << (int) n
    regions.put(name, Regions.iterable(mask))
}
IJ.log("[Labkit] labeled voxels per class: " + [classes, counts].transpose().collect { it.join("=") }.join(", "))
if (counts.any { it == 0 }) throw new IllegalArgumentException("Every class needs labeled voxels: " + counts)
def labeling = Labeling.fromMap(regions)

// ---- train ----------------------------------------------------------------------------------
def image = ImagePlusAdapter.wrapImgPlus(imp)          // keeps axes + calibration -> voxel size
long voxels = (long) W * H * Z

boolean gpuAvailable(long needMiB) {
    try {
        def names = net.haesleinhuepf.clij.CLIJ.getAvailableDeviceNames()
        if (!names.any { it =~ /(?i)nvidia|geforce|quadro|tesla|a100|h100|rtx|radeon/ }) return false
        def p = ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"].execute(); p.waitFor()
        def free = p.text.readLines()*.trim().findAll { it }.collect { it as long }
        return free && free[0] >= needMiB
    } catch (Throwable t) { return false }
}
long needMiB = Math.max(6144L, (long) (voxels * 60L / (1L << 20)))   // ~5.5 GB measured for 84 M voxels
boolean useGpu = gpuMode == "on" || (gpuMode == "auto" && gpuAvailable(needMiB))

def train = { boolean gpu ->
    def seg = new TrainableSegmentationSegmenter(context)
    seg.setUseGpu(gpu)
    long t0 = System.currentTimeMillis()
    seg.train([new ValuePair(image, labeling)])
    IJ.log(String.format("[Labkit] trained on %s in %.1f s", gpu ? "GPU" : "CPU", (System.currentTimeMillis() - t0) / 1000.0))
    return seg
}
def seg
try {
    seg = train(useGpu)
} catch (Throwable t) {
    if (!useGpu) throw t
    IJ.log("[Labkit] GPU training failed (" + t.getClass().simpleName + ": " + t.message + ") — retrying on CPU")
    seg = train(false)
}
def gs = seg.getSegmenter().settings().globals()
IJ.log("[Labkit] features: " + gs.numDimensions() + "D, voxel size relative to X " + gs.pixelSize() + ", sigmas " + gs.sigmas())
seg.saveModel(classifierFile.absolutePath)
IJ.log("[Labkit] classifier saved: " + classifierFile + "  classes (segmentation value 0..N-1): " + seg.classNames())
println("LABKIT_TRAIN_OK " + seg.classNames())
