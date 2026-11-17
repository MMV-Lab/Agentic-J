# Labkit — Groovy API (verified against the installed jars, 2026-11-16)

Prefer the ready workflows (`GROOVY_WORKFLOW_*.groovy`); this file documents what they use.

## Commands (all `headless = true`, run via `CommandService`)

| Menu (Plugins > Labkit > …) | Class (`sc.fiji.labkit.ui.plugin.` unless noted) | Parameters |
|---|---|---|
| Open Current Image With Labkit | `LabkitPlugin` | `dataset` — opens the interactive window (needs a display) |
| Open Image File With Labkit | `LabkitImportPlugin` | file chooser |
| Macro Recordable > Segment Image With Labkit | `SegmentImageWithLabkitPlugin` | `input` (Dataset), `segmenter_file` (File), `use_gpu` (Boolean) → `output` (Dataset, axes + calibration kept) |
| Macro Recordable > Segment Image With Labkit (IJ1) | `SegmentImageWithLabkitIJ1Plugin` | `input` (ImagePlus), `segmenter_file`, `use_gpu` → `output` (ImagePlus; **3D axes scrambled**, see below) |
| Macro Recordable > Calculate Probability Map With Labkit | `CalculateProbabilityMapWithLabkitPlugin` | as above, Dataset |
| Macro Recordable > Calculate Probability Map With Labkit (IJ1) | `CalculateProbabilityMapWithLabkitIJ1Plugin` | as above, ImagePlus; **axes scrambled** |
| Macro Recordable > Segment Images in Directory with Labkit | `LabkitSegmentImagesInDirectoryPlugin` | `input_directory`, `file_filter` (**glob**, `*.tif`), `output_directory`, `output_file_suffix`, `segmenter_file`, `use_gpu` |
| Macro Recordable > Calculate Probability Map for Images in Directory with Labkit | `LabkitProbabilityMapForImagesInDirectoryPlugin` | same directory parameters |
| Plugins > Segmentation > Measure Connected Components | `MeasureConnectedComponents` | counts components of a segmentation |

```groovy
import sc.fiji.labkit.ui.plugin.SegmentImageWithLabkitIJ1Plugin
// service from the running Fiji; a `#@ CommandService command` line works too, but is lost
// when the #@ inputs are replaced by plain variables for a headless run
command = ((org.scijava.Context) ij.IJ.runPlugIn("org.scijava.Context", "")).service(org.scijava.command.CommandService)
def out = command.run(SegmentImageWithLabkitIJ1Plugin, true,
    "input", imp, "segmenter_file", new File("/path/model.classifier"), "use_gpu", false
).get().getOutput("output")
```

**IJ1 output axes (z-stack input Z slices):** segmentation = 1 slice × Z channels; probability map =
Z channels × nClasses slices, planes ordered with Z fastest and classes slowest. Fix:

```groovy
ImageStack st = new ImageStack(out.getWidth(), out.getHeight())
int planes = imp.getNSlices() * imp.getNFrames()
for (int p = 0; p < planes; p++) for (int k = 0; k < nClasses; k++) st.addSlice(out.getStack().getProcessor(k * planes + p + 1))
def fixed = new ImagePlus(out.getTitle(), st); fixed.setDimensions(nClasses, imp.getNSlices(), imp.getNFrames())
fixed.setCalibration(imp.getCalibration().copy())          // nClasses = 1 for the segmentation
```

Segmentation values are 0-based class indices in the order of the classifier's `classNames`
(stored in the `.classifier` JSON: `{"features", "classNames", "classifier"}`).

## Scripted training (no Labkit window)

```groovy
import net.imglib2.img.ImagePlusAdapter
import net.imglib2.util.ValuePair
import sc.fiji.labkit.ui.labeling.Labeling
import sc.fiji.labkit.ui.segmentation.weka.TrainableSegmentationSegmenter

context = (org.scijava.Context) ij.IJ.runPlugIn("org.scijava.Context", "")
def image = ImagePlusAdapter.wrapImgPlus(imp)          // axes + calibration -> 3D + voxel size
def labeling = Labeling.fromMap(["background": bgRegion, "marker": markerRegion])   // IterableRegion<BitType> per class
// or Labeling.fromImg(labelImg)  (labels then named by their value)
def seg = new TrainableSegmentationSegmenter(context)
seg.setUseGpu(false)
seg.train([new ValuePair(image, labeling)])            // labeling size must equal image X/Y/Z(/T), no channel axis
seg.saveModel("/path/model.classifier")
println seg.classNames()
println seg.getSegmenter().settings().globals().pixelSize()   // e.g. [1.0, 1.0, 1.65]
```

Default settings (when `setFeatureSettings` is not called) are taken from the image: 2D or 3D from
its spatial axes, voxel size from its calibration (relative to X), sigma range 1–8, features
identity + Gaussian + difference of Gaussians + gradient + Laplacian + Hessian. Override only with
reason, e.g.:

```groovy
import sc.fiji.labkit.pixel_classification.pixel_feature.settings.*
import sc.fiji.labkit.pixel_classification.pixel_feature.filter.SingleFeatures
import sc.fiji.labkit.pixel_classification.pixel_feature.filter.GroupedFeatures
seg.setFeatureSettings(new FeatureSettings(
    GlobalSettings.default3d().pixelSize(1.0d, 1.0d, 1.65d).sigmaRange(1.0d, 8.0d).build(),
    [SingleFeatures.identity(), GroupedFeatures.gauss(), GroupedFeatures.differenceOfGaussians(),
     GroupedFeatures.gradient(), GroupedFeatures.laplacian(), GroupedFeatures.hessian()]))
```

Do **not** segment a large stack with `seg.segment(image, out)` / `Segmenter.segment(...)`: it
computes all features for the whole image at once and fails above 2^31 elements
("Number of elements in ArrayImg too big", e.g. 84 M voxels × 27 features). Save the model and use
the commands, which work block-wise.

## GPU (CLIJ / OpenCL)

GPU only accelerates feature computation (the random forest stays on the CPU). Labkit has no CPU
fallback: with too little free GPU memory it fails (`CL_MEM_OBJECT_ALLOCATION_FAILURE`,
`NullPointerException` in `DefaultGpuApi.handleOutOfMemoryException`, `CL_INVALID_COMMAND_QUEUE`, or
a long run of "N warnings generated"). Measured peak: 5.5 GB for an 84 M-voxel stack (~60 B/voxel).

```groovy
boolean gpuAvailable(long needMiB) {
    try {
        def names = net.haesleinhuepf.clij.CLIJ.getAvailableDeviceNames()   // POCL-only = CPU OpenCL, no GPU
        if (!names.any { it =~ /(?i)nvidia|geforce|quadro|tesla|a100|h100|rtx|radeon/ }) return false
        def p = ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"].execute(); p.waitFor()
        def free = p.text.readLines()*.trim().findAll { it }.collect { it as long }
        return free && free[0] >= needMiB
    } catch (Throwable t) { return false }
}
// use_gpu = gpuAvailable(Math.max(6144L, voxels * 60L / (1L << 20))); on any exception retry with use_gpu = false
```

Measured (1000×1000×84, A100): segmentation CPU 90 s / GPU 41 s; probability map CPU 89 s / GPU 9 s;
training is usually not faster on GPU (kernel compilation). If CLIJ lists only a CPU device, the
image lacks the NVIDIA OpenCL ICD registration (`/etc/OpenCL/vendors/nvidia.icd`), which the GPU
Dockerfile adds; CPU is then the only option.
