// ============================================================================
// CLIJ2 — 3D spot/object detection in a z-stack + projections (the case where
// the GPU pays off most: 3D neighborhood filters).
//
// Pattern:  push stack → denoise 3D → DoG → threshold → connected components
//           → 3D statistics → Z-projection for QC → release
//
// Tested end-to-end on Fiji 2.16.0/1.54p, CLIJ2 2.5.3.5, NVIDIA A100.
// If IMAGE_PATH is empty the script generates a synthetic stack, so it runs
// as-is and can be used as a self-test of the GPU pipeline.
// ============================================================================
import net.haesleinhuepf.clij2.CLIJ2
import ij.IJ
import ij.measure.ResultsTable

// ── Parameters ───────────────────────────────────────────────────────────────
def IMAGE_PATH = ""                    // e.g. "/data/stack.tif"; "" → synthetic
def OUTPUT_DIR = "/data/clij2_spots3d"
def MEDIAN_R   = 1                     // 3D median radius (px) — denoise
def DOG_SMALL  = 2.0                   // DoG sigma1 (≈ spot radius)
def DOG_LARGE  = 6.0                   // DoG sigma2 (background scale)
def Z_RATIO    = 1.0                   // voxel_depth / voxel_width; 4.0 for anisotropic stacks

new File(OUTPUT_DIR).mkdirs()
def clij2 = CLIJ2.getInstance()
clij2.clear()
IJ.log("GPU: " + clij2.getGPUName())

// ── 1. Get a 3D buffer onto the GPU ──────────────────────────────────────────
def input
if (IMAGE_PATH) {
    def imp = IJ.openImage(IMAGE_PATH)
    if (imp == null) throw new RuntimeException("could not open " + IMAGE_PATH)
    // push() transfers the WHOLE stack; pushCurrentZStack(imp) takes only the
    // current channel/time point of a hyperstack.
    input = imp.getNSlices() > 1 && imp.getNChannels() > 1 ? clij2.pushCurrentZStack(imp)
                                                           : clij2.push(imp)
} else {
    // Synthetic: 30 bright spheres in a 256x256x64 float volume + offset.
    input = clij2.create([256, 256, 64] as long[], clij2.Float)
    clij2.set(input, 100)                                   // background level
    def rng = new Random(42)
    30.times {
        clij2.drawSphere(input,
                         10 + rng.nextInt(236), 10 + rng.nextInt(236), 5 + rng.nextInt(54),
                         3, 3, 3, 800)                      // radii x,y,z + value
    }
}
IJ.log("input: " + Arrays.toString(input.getDimensions()) + " " + input.getNativeType())

// ── 2. Denoise in 3D (a true 3D neighborhood — slow on CPU, cheap on GPU) ────
def denoised = clij2.create(input)
clij2.median3DSphere(input, denoised, MEDIAN_R, MEDIAN_R, Math.max(1, (int)(MEDIAN_R / Z_RATIO)))

// ── 3. Difference of Gaussians = spot enhancement / background flattening ────
// Divide the z sigmas by the voxel aspect ratio so the filter is isotropic in
// physical space (CLIJ2 works in PIXELS and ignores image calibration).
def dog = clij2.create(input.getDimensions(), clij2.Float)
clij2.differenceOfGaussian3D(denoised, dog,
                             DOG_SMALL, DOG_SMALL, DOG_SMALL / Z_RATIO,
                             DOG_LARGE, DOG_LARGE, DOG_LARGE / Z_RATIO)

// ── 4. Threshold → binary (CLIJ2 binaries are 0/1, NOT 0/255) ───────────────
def binary = clij2.create(input.getDimensions(), clij2.UnsignedByte)
clij2.thresholdOtsu(dog, binary)

// ── 5. Label in 3D ───────────────────────────────────────────────────────────
def labels = clij2.create(input.getDimensions(), clij2.Float)
clij2.connectedComponentsLabelingBox(binary, labels)        // Box = 26-connected

def labels_clean = clij2.create(labels)
clij2.excludeLabelsOnEdges(labels, labels_clean)            // drops objects cut by the volume border

int count = (int) clij2.maximumOfAllPixels(labels_clean)
IJ.log("3D objects: " + count)

// ── 6. 3D measurements ───────────────────────────────────────────────────────
def rt = new ResultsTable()
clij2.statisticsOfLabelledPixels(input, labels_clean, rt)   // PIXEL_COUNT = voxel count
rt.save(OUTPUT_DIR + "/spots3d.csv")

// ── 7. Projections for QC (maximum / mean / sum along Z) ────────────────────
def dims = input.getDimensions()
def mip = clij2.create([dims[0], dims[1]] as long[], clij2.Float)
clij2.maximumZProjection(input, mip)
IJ.saveAs(clij2.pull(mip), "Tiff", OUTPUT_DIR + "/max_projection.tif")

def label_mip = clij2.create([dims[0], dims[1]] as long[], clij2.Float)
clij2.maximumZProjection(labels_clean, label_mip)
IJ.saveAs(clij2.pull(label_mip), "Tiff", OUTPUT_DIR + "/labels_projection.tif")

// ── 8. Release everything ────────────────────────────────────────────────────
[input, denoised, dog, binary, labels, labels_clean, mip, label_mip].each { clij2.release(it) }
clij2.clear()

IJ.log("SUMMARY spots=" + count + " out=" + OUTPUT_DIR)
println("SUMMARY spots=" + count)
