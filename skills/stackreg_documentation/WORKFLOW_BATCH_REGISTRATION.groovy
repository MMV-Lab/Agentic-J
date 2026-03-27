/**
 * STACKREG_WORKFLOW_BATCH_REGISTRATION.groovy
 * StackReg — Batch Time-Lapse / Stack Registration
 *
 * PURPOSE:
 *   Opens one or more TIFF stacks from an input directory, registers every
 *   slice to its neighbour using StackReg (propagating from a chosen anchor
 *   slice), and saves the registered stacks to an output directory.
 *
 *   Optionally duplicates each stack before registration so the original
 *   data is preserved alongside the registered version.
 *
 * HOW TO RUN:
 *   1. Open Fiji
 *   2. Plugins › Script Editor
 *   3. Set language to Groovy
 *   4. Edit the PARAMETERS block below
 *   5. Run › Run Script (Ctrl+R)
 *
 * REQUIREMENTS:
 *   - StackReg and TurboReg both installed via BIG-EPFL update site:
 *       Help › Update… → Manage Update Sites → tick BIG-EPFL → Apply Changes
 *   - Source stacks must be grayscale or stacks of RGB-colour images
 *     (NOT RGB-stacks = 3-component stacks)
 *
 * KEY SCRIPTING NOTES:
 *   - "StackReg " — trailing space is MANDATORY
 *   - StackReg IS macro-recordable (unlike TurboReg)
 *   - StackReg modifies the active stack IN-PLACE; always duplicate if
 *     you need the original data
 *   - The anchor slice is set by navigating to it with imp.setSlice()
 *     before calling IJ.run()
 */

import ij.IJ
import ij.ImagePlus
import ij.plugin.Duplicator
import java.io.File

// ============================================================
// PARAMETERS — edit these for your dataset
// ============================================================

// Directory containing the input TIFF stacks
def INPUT_DIR  = "/data/raw/"

// Directory where registered stacks will be saved (created if absent)
def OUTPUT_DIR = "/data/registered/"

// Transformation type — choose one:
//   "Translation"     — XY drift only (fastest, most robust)
//   "Rigid Body"      — drift + rotation
//   "Scaled Rotation" — drift + rotation + isotropic scale
//   "Affine"          — full 2D linear (use only when clearly needed)
// NOTE: "Bilinear" is NOT available in StackReg
def TRANSFORMATION = "Rigid Body"

// Anchor slice strategy — choose one:
//   "middle"  — use the middle slice (recommended for most stacks)
//   "first"   — use slice 1 (default if you open a stack and run StackReg directly)
//   "last"    — use the last slice
//   "fixed:N" — use a specific 1-based slice number, e.g. "fixed:30"
def ANCHOR_STRATEGY = "middle"

// Keep a copy of the original stack alongside the registered one?
def KEEP_ORIGINAL = true

// Suffix added to the output filename
def OUTPUT_SUFFIX = "_registered"

// ============================================================
// SETUP
// ============================================================

def inputDir  = new File(INPUT_DIR)
def outputDir = new File(OUTPUT_DIR)

if (!inputDir.isDirectory()) {
    IJ.error("StackReg Workflow", "Input directory not found:\n" + INPUT_DIR)
    return
}
outputDir.mkdirs()

def files = inputDir.listFiles()
    .findAll { it.isFile() && (it.name.endsWith(".tif") || it.name.endsWith(".tiff")) }
    .sort { it.name }

if (files.isEmpty()) {
    IJ.log("No .tif files found in: " + INPUT_DIR)
    return
}

IJ.log("=" * 60)
IJ.log("StackReg Batch Registration")
IJ.log("Input     : " + INPUT_DIR)
IJ.log("Output    : " + OUTPUT_DIR)
IJ.log("Transform : " + TRANSFORMATION)
IJ.log("Anchor    : " + ANCHOR_STRATEGY)
IJ.log("Files     : " + files.size())
IJ.log("=" * 60)

// ============================================================
// HELPER: Compute anchor slice index (1-based)
// ============================================================

def getAnchorSlice = { ImagePlus imp ->
    int n = imp.getNSlices()
    if (ANCHOR_STRATEGY == "first") return 1
    if (ANCHOR_STRATEGY == "last")  return n
    if (ANCHOR_STRATEGY == "middle") return Math.max(1, n / 2 as int)
    if (ANCHOR_STRATEGY.startsWith("fixed:")) {
        int fixed = ANCHOR_STRATEGY.split(":")[1].toInteger()
        return Math.max(1, Math.min(fixed, n))
    }
    return Math.max(1, n / 2 as int)  // fallback: middle
}

// ============================================================
// MAIN LOOP
// ============================================================

def succeeded = []
def failed    = []

files.each { file ->
    IJ.log("\n--- " + file.name + " ---")

    // Open
    def imp = IJ.openImage(file.absolutePath)
    if (imp == null) {
        IJ.log("  ERROR: could not open file")
        failed << file.name
        return
    }

    int nSlices = imp.getNSlices()
    IJ.log("  Slices : " + nSlices + " | Type: " + imp.getBitDepth() + "-bit")

    // Validate
    if (nSlices < 2) {
        IJ.log("  SKIP: fewer than 2 slices — nothing to register")
        imp.close()
        return
    }

    // Optionally save original before registration (StackReg modifies in-place)
    if (KEEP_ORIGINAL) {
        def origName = file.name.replaceAll(/\.tiff?$/, "_original.tif")
        def origPath = OUTPUT_DIR + origName
        IJ.saveAsTiff(imp, origPath)
        IJ.log("  Original saved: " + origName)
    }

    // Show image and set anchor slice
    imp.show()
    int anchor = getAnchorSlice(imp)
    imp.setSlice(anchor)
    IJ.log("  Anchor slice: " + anchor + " of " + nSlices)

    // Register — trailing space in "StackReg " is mandatory
    try {
        IJ.run(imp, "StackReg ", "transformation=[" + TRANSFORMATION + "]")
    } catch (Exception e) {
        IJ.log("  ERROR during registration: " + e.getMessage())
        failed << file.name
        imp.close()
        return
    }

    // Save registered result
    def baseName = file.name.replaceAll(/\.tiff?$/, "")
    def outPath  = OUTPUT_DIR + baseName + OUTPUT_SUFFIX + ".tif"
    IJ.saveAsTiff(imp, outPath)
    IJ.log("  Registered saved: " + baseName + OUTPUT_SUFFIX + ".tif")

    imp.close()
    succeeded << file.name
}

// ============================================================
// SUMMARY
// ============================================================

IJ.log("\n" + "=" * 60)
IJ.log("StackReg Batch Complete")
IJ.log("Succeeded : " + succeeded.size())
IJ.log("Failed    : " + failed.size())
if (!failed.isEmpty()) {
    IJ.log("Failed files:")
    failed.each { IJ.log("  ✗ " + it) }
}
IJ.log("Output directory: " + OUTPUT_DIR)
IJ.log("=" * 60)
