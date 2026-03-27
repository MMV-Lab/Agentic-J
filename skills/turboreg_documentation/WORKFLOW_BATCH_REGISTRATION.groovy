/**
 * TURBOREG_WORKFLOW_BATCH_REGISTRATION.groovy
 * TurboReg — Batch Registration of a Stack to a Reference Image
 *
 * PURPOSE:
 *   Opens a reference (target) image and a source stack, registers every
 *   slice of the source stack to the reference using TurboReg, and saves
 *   the result as a TIFF stack.
 *
 * HOW TO RUN:
 *   1. Open Fiji
 *   2. Plugins › Script Editor
 *   3. Set language to Groovy
 *   4. Edit the PARAMETERS block below
 *   5. Run › Run Script (Ctrl+R)
 *
 * REQUIREMENTS:
 *   - TurboReg installed via the BIG-EPFL update site:
 *       Help › Update… → Manage Update Sites → tick BIG-EPFL → Apply Changes
 *   - Source must be a grayscale stack (not RGB)
 *   - Target must be a single 2D grayscale image
 *
 * KEY SCRIPTING NOTES:
 *   - The command name MUST include the trailing space: "TurboReg "
 *   - TurboReg is NOT macro-recordable; the parameter string must be written manually
 *   - Output is always float 32-bit
 */

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.io.FileSaver

// ============================================================
// PARAMETERS — edit these for your dataset
// ============================================================

// Path to the reference (target) image — fixed, 2D grayscale
def TARGET_PATH = "/data/experiment01/reference.tif"

// Path to the source stack — each slice will be registered to the target
def SOURCE_PATH = "/data/experiment01/timelapse.tif"

// Path for the registered output stack
def OUTPUT_PATH = "/data/experiment01/registered.tif"

// Transformation type — choose one:
//   "translation"     — XY shift only (1 landmark)
//   "rigidBody"       — shift + rotation (3 landmarks)
//   "scaledRotation"  — shift + rotation + isotropic scale (2 landmarks)
//   "affine"          — shift + rotation + shear + anisotropic scale (3 landmarks)
//   "bilinear"        — non-linear (4 landmarks)
def TRANSFORMATION = "rigidBody"

// Convert float 32-bit output to 16-bit before saving?
def SAVE_AS_16BIT = true

// ============================================================
// SETUP
// ============================================================

IJ.log("=" * 60)
IJ.log("TurboReg Batch Registration")
IJ.log("Target : " + TARGET_PATH)
IJ.log("Source : " + SOURCE_PATH)
IJ.log("Output : " + OUTPUT_PATH)
IJ.log("Transform: " + TRANSFORMATION)
IJ.log("=" * 60)

// Open images
IJ.log("\nOpening images...")
def target = IJ.openImage(TARGET_PATH)
if (target == null) {
    IJ.error("TurboReg Workflow", "Could not open target:\n" + TARGET_PATH)
    return
}
target.show()

def source = IJ.openImage(SOURCE_PATH)
if (source == null) {
    IJ.error("TurboReg Workflow", "Could not open source:\n" + SOURCE_PATH)
    target.close()
    return
}
source.show()

def nSlices = source.getNSlices()
def sw = source.getWidth()
def sh = source.getHeight()
def tw = target.getWidth()
def th = target.getHeight()

IJ.log("Source: " + sw + " x " + sh + ", " + nSlices + " slice(s)")
IJ.log("Target: " + tw + " x " + th)

// Validate
if (nSlices < 1) {
    IJ.error("TurboReg Workflow", "Source has no slices.")
    source.close(); target.close(); return
}
if (source.isComposite() || source.getType() == ImagePlus.COLOR_RGB) {
    IJ.error("TurboReg Workflow", "Source must be a grayscale stack (not RGB).")
    source.close(); target.close(); return
}

// ============================================================
// BUILD LANDMARK STRING
// ============================================================

// Compute sensible default landmark positions centred on the image.
// These are starting positions for automatic refinement — TurboReg
// will move them to minimise mean-square error.
//
// NOTE (important practical tip):
// If your sample is mainly at the *image edge* (e.g. phase contrast with tissue
// only on the border), these centred defaults can converge to the identity
// ("no movement") or produce unstable fits.
// In that case, two common fixes are:
//   1) Register on an edge-enhanced copy (e.g. Difference-of-Gaussians or Find Edges)
//   2) Place landmarks near borders/corners (inset ~10%) instead of centred landmarks

def cx = sw / 2 as int;  def cy = sh / 2 as int   // source centre
def rx = tw / 2 as int;  def ry = th / 2 as int   // target centre

String landmarkStr

switch (TRANSFORMATION) {
    case "translation":
        landmarkStr = "-translation ${cx} ${cy} ${rx} ${ry}"
        break

    case "rigidBody":
        // 3 landmarks: centre (translation) + two rotation guides
        int srcRot1Y = cy - (sh / 4) as int
        int srcRot2Y = cy + (sh / 4) as int
        int tgtRot1Y = ry - (th / 4) as int
        int tgtRot2Y = ry + (th / 4) as int
        landmarkStr = "-rigidBody " +
            "${cx} ${cy} ${rx} ${ry} " +
            "${cx} ${srcRot1Y} ${rx} ${tgtRot1Y} " +
            "${cx} ${srcRot2Y} ${rx} ${tgtRot2Y}"
        break

    case "scaledRotation":
        // 2 landmarks: left-centre and right-centre
        int sl = sw / 4 as int;  int sr = 3 * sw / 4 as int
        int tl = tw / 4 as int;  int tr = 3 * tw / 4 as int
        landmarkStr = "-scaledRotation " +
            "${sl} ${cy} ${tl} ${ry} " +
            "${sr} ${cy} ${tr} ${ry}"
        break

    case "affine":
        // 3 landmarks: top-left, top-right, bottom-centre
        int stlx = sw / 4 as int;  int stly = sh / 4 as int
        int strx = 3*sw/4 as int;  int stry = sh / 4 as int
        int sbcx = sw / 2 as int;  int sbcy = 3*sh/4 as int
        int ttlx = tw / 4 as int;  int ttly = th / 4 as int
        int ttrx = 3*tw/4 as int;  int ttry = th / 4 as int
        int tbcx = tw / 2 as int;  int tbcy = 3*th/4 as int
        landmarkStr = "-affine " +
            "${stlx} ${stly} ${ttlx} ${ttly} " +
            "${strx} ${stry} ${ttrx} ${ttry} " +
            "${sbcx} ${sbcy} ${tbcx} ${tbcy}"
        break

    case "bilinear":
        // 4 landmarks: inset corners
        int q = Math.min(sw, sh) / 4 as int
        int tq = Math.min(tw, th) / 4 as int
        landmarkStr = "-bilinear " +
            "${q} ${q} ${tq} ${tq} " +
            "${sw-q} ${q} ${tw-tq} ${tq} " +
            "${q} ${sh-q} ${tq} ${th-tq} " +
            "${sw-q} ${sh-q} ${tw-tq} ${th-tq}"
        break

    default:
        IJ.error("TurboReg Workflow", "Unknown transformation: " + TRANSFORMATION)
        source.close(); target.close(); return
}

IJ.log("Landmarks: " + landmarkStr)

// ============================================================
// RUN TURBOREG
// ============================================================

IJ.log("\nRunning TurboReg (${TRANSFORMATION}, ${nSlices} slice(s))...")

// NOTE: "TurboReg " — the trailing space after TurboReg is MANDATORY
String turboRegArgs =
    "-align " +
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    landmarkStr + " " +
    "-showOutput"

IJ.run("TurboReg ", turboRegArgs)

def registered = IJ.getImage()
if (registered == null || registered == source || registered == target) {
    IJ.error("TurboReg Workflow",
        "Registration failed — no output image found.\n" +
        "Check that TurboReg is installed (BIG-EPFL update site)\n" +
        "and that the source is a grayscale stack.")
    source.close(); target.close(); return
}

IJ.log("Registered: " + registered.getTitle() +
       " (" + registered.getNSlices() + " slices, " +
       registered.getBitDepth() + "-bit)")

// ============================================================
// SAVE OUTPUT
// ============================================================

if (SAVE_AS_16BIT) {
    IJ.log("Converting to 16-bit...")
    IJ.run(registered, "16-bit", "")
}

IJ.log("Saving to: " + OUTPUT_PATH)
new FileSaver(registered).saveAsTiff(OUTPUT_PATH)

// ============================================================
// CLEANUP
// ============================================================

source.close()
target.close()
// Leave registered image open for inspection; close if you prefer:
// registered.close()

IJ.log("\n" + "=" * 60)
IJ.log("Done. Output: " + OUTPUT_PATH)
IJ.log("=" * 60)
