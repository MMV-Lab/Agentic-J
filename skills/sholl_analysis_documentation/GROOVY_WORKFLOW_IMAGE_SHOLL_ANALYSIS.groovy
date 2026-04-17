// Parse a segmented 2D or 3D image into a Sholl profile and export the sampled profile plus summary statistics.
#@ File(label = "Input segmented image", required = false) inputImageFile
#@ Boolean(label = "Use built-in sample image when input image is not provided", value = true) useSampleImageIfInputMissing
#@ String(choices = {"Otsu dark", "Huang", "Triangle", "none"}, label = "Auto-threshold method when image is not already binary", value = "Otsu dark") autoThresholdMethod
#@ Double(label = "Manual lower threshold (-1 = binary/auto)", value = -1) lowerThreshold
#@ Double(label = "Manual upper threshold (-1 = binary/auto)", value = -1) upperThreshold
#@ Integer(label = "Center X in pixels (-1 = image center)", value = -1) centerX
#@ Integer(label = "Center Y in pixels (-1 = image center)", value = -1) centerY
#@ Integer(label = "Center Z in pixels for 3D (-1 = middle slice)", value = -1) centerZ
#@ Double(label = "Start radius", value = 0) startRadius
#@ Double(label = "Radius step size (0 = continuous)", value = 5) stepSize
#@ Double(label = "End radius (<= 0 = maximum possible radius)", value = 0) endRadius
#@ Integer(label = "Channel (1-based)", value = 1) channelIndex
#@ Integer(label = "Frame (1-based)", value = 1) frameIndex
#@ Integer(label = "Slice for 2D analysis (1-based)", value = 1) sliceIndex
#@ Boolean(label = "Ignore isolated single voxels in 3D", value = true) skipSingleVoxels3D
#@ File(label = "Output profile CSV", style = "save", value = "/data/sholl_validation/image_sholl_profile.csv") profileCsvFile
#@ File(label = "Output Sholl stats CSV", style = "save", value = "/data/sholl_validation/image_sholl_stats.csv") statsCsvFile

import ij.IJ
import ij.ImagePlus
import sc.fiji.snt.analysis.sholl.ShollUtils
import sc.fiji.snt.analysis.sholl.math.LinearProfileStats
import sc.fiji.snt.analysis.sholl.math.NormalizedProfileStats
import sc.fiji.snt.analysis.sholl.math.ShollStats
import sc.fiji.snt.analysis.sholl.parsers.ImageParser2D
import sc.fiji.snt.analysis.sholl.parsers.ImageParser3D

void requireFreshOutput(File file, String label) {
    if (file == null) {
        throw new IllegalArgumentException(label + " must be provided")
    }
    file.parentFile?.mkdirs()
    if (file.exists()) {
        throw new IllegalArgumentException(label + " already exists: " + file.absolutePath)
    }
}

String csvEscape(Object value) {
    return (value == null ? "" : value.toString()).replace("\"", "\"\"")
}

String csvCell(Object value) {
    return "\"" + csvEscape(value) + "\""
}

ImagePlus loadImage() {
    if (inputImageFile != null) {
        if (!inputImageFile.exists() || !inputImageFile.isFile()) {
            throw new IllegalArgumentException("Input image file not found: " + inputImageFile)
        }
        def imp = IJ.openImage(inputImageFile.absolutePath)
        if (imp == null) {
            throw new IllegalStateException("Could not open input image: " + inputImageFile.absolutePath)
        }
        return imp
    }
    if (useSampleImageIfInputMissing) {
        def imp = ShollUtils.sampleImage()
        if (imp == null) {
            throw new IllegalStateException("Sholl sample image could not be obtained")
        }
        return imp
    }
    throw new IllegalArgumentException("Provide an input image file or enable the sample image fallback")
}

void configureThreshold(ImagePlus imp, def parser) {
    if (lowerThreshold >= 0 && upperThreshold >= 0) {
        parser.setThreshold(lowerThreshold, upperThreshold)
        return
    }
    if (imp.isThreshold() || imp.getProcessor().isBinary()) {
        return
    }
    if ("none".equals(autoThresholdMethod)) {
        throw new IllegalArgumentException("Image is not binary or thresholded. Provide manual thresholds or enable auto-thresholding.")
    }
    IJ.setAutoThreshold(imp, autoThresholdMethod)
}

int[] resolveCenter(ImagePlus imp) {
    int x = centerX >= 0 ? centerX : (int) Math.round(imp.getWidth() / 2.0)
    int y = centerY >= 0 ? centerY : (int) Math.round(imp.getHeight() / 2.0)
    int z = centerZ >= 0 ? centerZ : Math.max(1, (int) Math.round(imp.getNSlices() / 2.0))
    return [x, y, z] as int[]
}

void writeProfileCsv(File file, def profile) {
    double[] radii = profile.radiiAsArray()
    double[] counts = profile.countsAsArray()
    file.withWriter("UTF-8") { writer ->
        writer.println("radius,count")
        for (int i = 0; i < radii.length; i++) {
            writer.println(radii[i] + "," + counts[i])
        }
    }
}

void writeStatsCsv(File file, ImagePlus imp, int[] centerPx, def profile, def lStats, int bestDegree, double bestRSq, double ksPValue, def nStats) {
    file.withWriter("UTF-8") { writer ->
        writer.println("metric,sampled,fitted")
        writer.println(csvCell("image_title") + "," + csvCell(imp.getTitle()) + ",")
        writer.println(csvCell("profile_dimensions") + "," + profile.nDimensions() + ",")
        writer.println(csvCell("profile_size") + "," + profile.size() + ",")
        writer.println(csvCell("start_radius") + "," + profile.startRadius() + ",")
        writer.println(csvCell("step_size") + "," + profile.stepSize() + ",")
        writer.println(csvCell("end_radius") + "," + profile.endRadius() + ",")
        writer.println(csvCell("center_px") + "," + csvCell(centerPx.join(",")) + ",")

        writer.println(csvCell("min") + "," + lStats.getMin(false) + "," + lStats.getMin(true))
        writer.println(csvCell("max") + "," + lStats.getMax(false) + "," + lStats.getMax(true))
        writer.println(csvCell("mean") + "," + lStats.getMean(false) + "," + lStats.getMean(true))
        writer.println(csvCell("median") + "," + lStats.getMedian(false) + "," + lStats.getMedian(true))
        writer.println(csvCell("sum") + "," + lStats.getSum(false) + "," + lStats.getSum(true))
        writer.println(csvCell("variance") + "," + lStats.getVariance(false) + "," + lStats.getVariance(true))
        writer.println(csvCell("kurtosis") + "," + lStats.getKurtosis(false) + "," + lStats.getKurtosis(true))
        writer.println(csvCell("skewness") + "," + lStats.getSkewness(false) + "," + lStats.getSkewness(true))
        writer.println(csvCell("ramification_index") + "," + lStats.getRamificationIndex(false) + "," + lStats.getRamificationIndex(true))
        writer.println(csvCell("enclosing_radius") + "," + lStats.getEnclosingRadius(false, 1) + "," + lStats.getEnclosingRadius(true, 1))
        writer.println(csvCell("primary_branches") + "," + lStats.getPrimaryBranches(false) + "," + lStats.getPrimaryBranches(true))
        writer.println(csvCell("intersecting_radii") + "," + lStats.getIntersectingRadii(false) + "," + lStats.getIntersectingRadii(true))

        writer.println(csvCell("best_fit_degree") + "," + bestDegree + ",")
        writer.println(csvCell("r_squared_adjusted") + "," + bestRSq + ",")
        writer.println(csvCell("ks_test_p_value") + "," + ksPValue + ",")

        writer.println(csvCell("normalization_method") + "," + csvCell(nStats.getMethodDescription()) + ",")
        writer.println(csvCell("sholl_decay") + "," + nStats.getShollDecay() + ",")
        writer.println(csvCell("determination_ratio") + "," + nStats.getDeterminationRatio() + ",")
    }
}

requireFreshOutput(profileCsvFile, "Profile CSV")
requireFreshOutput(statsCsvFile, "Sholl stats CSV")

def imp = loadImage()
boolean is3D = imp.getNSlices() > 1
int[] centerPx = resolveCenter(imp)

println("Sholl image analysis")
println("Input image      : " + (inputImageFile != null ? inputImageFile.absolutePath : "built-in sample image"))
println("Image title      : " + imp.getTitle())
println("Dimensions       : " + (is3D ? "3D" : "2D"))
println("Center (px)      : " + centerPx.join(", "))
println("Profile CSV      : " + profileCsvFile.absolutePath)
println("Stats CSV        : " + statsCsvFile.absolutePath)

def parser
if (is3D) {
    parser = new ImageParser3D(imp)
    parser.setCenterPx(centerPx[0], centerPx[1], centerPx[2])
    parser.setPosition(channelIndex, frameIndex)
    parser.setSkipSingleVoxels(skipSingleVoxels3D)
} else {
    parser = new ImageParser2D(imp)
    parser.setCenterPx(centerPx[0], centerPx[1])
    parser.setPosition(channelIndex, sliceIndex, frameIndex)
}

configureThreshold(imp, parser)
double resolvedEndRadius = endRadius > 0 ? endRadius : parser.maxPossibleRadius()
parser.setRadii(startRadius, stepSize, resolvedEndRadius)
parser.setHemiShells("none")
parser.parse()

if (!parser.successful()) {
    throw new IllegalStateException("Image parser failed for: " + imp.getTitle())
}

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
if (profile == null || profile.isEmpty()) {
    throw new IllegalStateException("Image-based Sholl profile is empty. Check the center or threshold settings.")
}

def lStats = new LinearProfileStats(profile)
int bestDegree = lStats.findBestFit(2, 30, 0.70, 0.05)
double bestRSq = lStats.getRSquaredOfFit(true)
double ksPValue = lStats.getKStestOfFit()
def nStats = new NormalizedProfileStats(profile, ShollStats.AREA)

writeProfileCsv(profileCsvFile, profile)
writeStatsCsv(statsCsvFile, imp, centerPx, profile, lStats, bestDegree, bestRSq, ksPValue, nStats)

if (!profileCsvFile.exists() || profileCsvFile.length() == 0) {
    throw new IllegalStateException("Could not save profile CSV: " + profileCsvFile.absolutePath)
}
if (!statsCsvFile.exists() || statsCsvFile.length() == 0) {
    throw new IllegalStateException("Could not save Sholl stats CSV: " + statsCsvFile.absolutePath)
}

println("Profile samples  : " + profile.size())
println("Best fit degree  : " + bestDegree)
println("Adjusted R^2     : " + bestRSq)
println("K-S p-value      : " + ksPValue)
println("Sholl decay      : " + nStats.getShollDecay())
println("Sholl image analysis complete")
