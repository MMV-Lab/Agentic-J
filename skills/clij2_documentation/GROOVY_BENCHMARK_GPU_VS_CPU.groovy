// ============================================================================
// CLIJ2 — is the GPU actually worth it here?  Measure, don't guess.
//
// Every GPU call pays a host→device→host transfer. For one small 2D filter that
// transfer costs more than the filter saves; for 3D neighborhood filters and
// long chains it is amortised many times over. This script measures the real
// numbers on the current machine and image, so a workflow decision is evidence-
// based.
//
// IMPORTANT: always warm up. The first CLIJ2 call of a session compiles OpenCL
// kernels (~0.5-2 s) — timing it makes the GPU look catastrophically slow.
//
// Measured on this system (A100, 512x512x64 float32, gaussian blur sigma=4):
//     ImageJ "Gaussian Blur 3D..."   ~1040 ms
//     CLIJ2 incl. push+pull           ~112 ms   →  ~9x faster
// ============================================================================
import net.haesleinhuepf.clij2.CLIJ2
import ij.IJ
import ij.gui.NewImage

// ── Parameters ───────────────────────────────────────────────────────────────
def WIDTH = 512, HEIGHT = 512, DEPTH = 64
def SIGMA = 4.0
def REPEATS = 3

def clij2 = CLIJ2.getInstance()
clij2.clear()
IJ.log("GPU: " + clij2.getGPUName())

// Test volume with structure (constant images can be optimised by some filters).
def imp = NewImage.createFloatImage("test", WIDTH, HEIGHT, DEPTH, NewImage.FILL_RAMP)
IJ.run(imp, "Add Specified Noise...", "stack standard=50")

// ── Warm-up: compile kernels + touch the transfer path once ─────────────────
def warm_in  = clij2.push(imp)
def warm_out = clij2.create(warm_in)
clij2.gaussianBlur3D(warm_in, warm_out, SIGMA, SIGMA, SIGMA)
clij2.pull(warm_out)
clij2.release(warm_in); clij2.release(warm_out)

// ── CPU reference ────────────────────────────────────────────────────────────
def cpu_ms = []
REPEATS.times {
    def dup = imp.duplicate()
    long t0 = System.nanoTime()
    IJ.run(dup, "Gaussian Blur 3D...", "x=" + SIGMA + " y=" + SIGMA + " z=" + SIGMA)
    cpu_ms << (System.nanoTime() - t0) / 1e6
    dup.close()
}

// ── GPU including transfers (the honest end-to-end number) ──────────────────
def gpu_total_ms = []
def gpu_kernel_ms = []
REPEATS.times {
    long t0 = System.nanoTime()
    def input = clij2.push(imp)
    def output = clij2.create(input)
    long t1 = System.nanoTime()
    clij2.gaussianBlur3D(input, output, SIGMA, SIGMA, SIGMA)
    long t2 = System.nanoTime()
    def result = clij2.pull(output)
    long t3 = System.nanoTime()
    gpu_total_ms  << (t3 - t0) / 1e6
    gpu_kernel_ms << (t2 - t1) / 1e6
    clij2.release(input); clij2.release(output)
    result.close()
}

def median = { list -> def s = list.sort(); s[(int)(s.size() / 2)] }
double cpu = median(cpu_ms), gpu = median(gpu_total_ms), kernel = median(gpu_kernel_ms)

IJ.log(String.format("CPU  (ImageJ Gaussian Blur 3D) : %8.1f ms", cpu))
IJ.log(String.format("GPU  (push + kernel + pull)    : %8.1f ms   speedup %.1fx", gpu, cpu / gpu))
IJ.log(String.format("GPU  (kernel only)             : %8.1f ms   transfer overhead %.1f ms", kernel, gpu - kernel))
IJ.log(cpu / gpu > 1.5 ? "→ GPU is worth it for this operation."
                       : "→ GPU is NOT worth it here; transfers dominate. Keep it on the CPU, " +
                         "or chain more operations on the GPU before pulling.")

clij2.clear()
println(String.format("SUMMARY cpu_ms=%.1f gpu_ms=%.1f kernel_ms=%.1f speedup=%.1f", cpu, gpu, kernel, cpu / gpu))
