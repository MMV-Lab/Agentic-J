#@ File (label = "Input image", value = "/data/example_1.tif") inputFile
#@ File (label = "Output directory", style = "directory", value = "/data/featurej_validation/workflow_output") outputDir
#@ String (label = "Mode", choices = {"Derivatives", "Edges", "Laplacian", "Hessian", "Structure", "Statistics"}, value = "Edges") mode
#@ Double (label = "Smoothing scale", value = 1.5, min = 0.01) smoothingScale
#@ Boolean (label = "Use physical calibration", value = false) usePhysicalCalibration
#@ Integer (label = "Derivative x-order", value = 1, min = 0, max = 10) derivativeXOrder
#@ Integer (label = "Derivative y-order", value = 0, min = 0, max = 10) derivativeYOrder
#@ Integer (label = "Derivative z-order", value = 0, min = 0, max = 10) derivativeZOrder
#@ Boolean (label = "Edges: compute gradient magnitude", value = true) edgesComputeGradient
#@ Boolean (label = "Edges: suppress non-maximum gradients", value = true) edgesSuppressNonMaximum
#@ String (label = "Edges: lower threshold", value = "20.0") edgesLowerThreshold
#@ String (label = "Edges: higher threshold", value = "40.0") edgesHigherThreshold
#@ Boolean (label = "Laplacian: compute Laplacian image", value = true) laplacianCompute
#@ Boolean (label = "Laplacian: detect zero-crossings", value = true) laplacianDetectZeroCrossings
#@ Boolean (label = "Hessian: save largest eigenvalue", value = true) hessianLargest
#@ Boolean (label = "Hessian: save middle eigenvalue", value = false) hessianMiddle
#@ Boolean (label = "Hessian: save smallest eigenvalue", value = true) hessianSmallest
#@ Boolean (label = "Hessian: absolute eigenvalue comparison", value = false) hessianAbsolute
#@ Boolean (label = "Structure: save largest eigenvalue", value = true) structureLargest
#@ Boolean (label = "Structure: save middle eigenvalue", value = false) structureMiddle
#@ Boolean (label = "Structure: save smallest eigenvalue", value = true) structureSmallest
#@ Double (label = "Structure integration scale", value = 3.0, min = 0.01) structureIntegrationScale
#@ String (label = "Statistics metrics", value = "Minimum,Maximum,Mean,Median,Elements,Mass,Variance,Mode,S-deviation,A-deviation,L1-norm,L2-norm,Skewness,Kurtosis") statisticsMetrics
#@ Integer (label = "Statistics decimals", value = 3, min = 0, max = 10) statisticsDecimals
#@ Integer (label = "ROI x", value = 0, min = 0) roiX
#@ Integer (label = "ROI y", value = 0, min = 0) roiY
#@ Integer (label = "ROI width", value = 0, min = 0) roiWidth
#@ Integer (label = "ROI height", value = 0, min = 0) roiHeight
#@ Boolean (label = "Quit Fiji when done", value = false) quitWhenDone

import ij.IJ
import ij.ImagePlus
import ij.gui.Roi
import ij.process.ByteProcessor
import groovy.transform.Field
import imagescience.feature.Differentiator
import imagescience.feature.Edges
import imagescience.feature.Hessian
import imagescience.feature.Laplacian
import imagescience.feature.Statistics
import imagescience.feature.Structure
import imagescience.image.Aspects
import imagescience.image.Coordinates
import imagescience.image.FloatImage
import imagescience.image.Image
import imagescience.segment.Thresholder
import imagescience.segment.ZeroCrosser
import java.util.Locale

/*
 * FeatureJ - Multi-mode feature extraction workflow
 *
 * PURPOSE:
 *   1. Open one grayscale image from disk
 *   2. Run one validated FeatureJ mode through the installed ImageScience API
 *   3. Save deterministic TIFF or CSV outputs to a user-supplied directory
 *
 * VALIDATED MODES:
 *   - Derivatives
 *   - Edges
 *   - Laplacian
 *   - Hessian
 *   - Structure
 *   - Statistics
 *
 * IMPORTANT:
 *   - FeatureJ and imagescience.jar must already be installed in Fiji.
 *   - Open this script in Fiji's Script Editor or execute it through a
 *     SciJava-aware launcher that supplies the #@ parameters.
 *   - Use a fresh or empty output directory, or at least a path where the
 *     generated filenames do not already exist.
 *   - FeatureJ operates on grayscale images. Convert RGB or indexed-color data
 *     before running the workflow.
 *   - When Use physical calibration is enabled, the workflow preserves the
 *     input image calibration and uses it exactly as the FeatureJ Options
 *     dialog describes. When disabled, smoothing scales are interpreted in
 *     pixel units.
 *   - Statistics mode supports an optional rectangular ROI. Leave ROI width
 *     and ROI height at 0 to measure the whole image.
 */

@Field Map<String, Integer> STATISTIC_INDEX = [
    "Minimum"    : Statistics.MINIMUM,
    "Maximum"    : Statistics.MAXIMUM,
    "Mean"       : Statistics.MEAN,
    "Median"     : Statistics.MEDIAN,
    "Elements"   : Statistics.ELEMENTS,
    "Mass"       : Statistics.MASS,
    "Variance"   : Statistics.VARIANCE,
    "Mode"       : Statistics.MODE,
    "S-deviation": Statistics.SDEVIATION,
    "A-deviation": Statistics.ADEVIATION,
    "L1-norm"    : Statistics.L1NORM,
    "L2-norm"    : Statistics.L2NORM,
    "Skewness"   : Statistics.SKEWNESS,
    "Kurtosis"   : Statistics.KURTOSIS
]

String slug(String text) {
    return text.replaceAll(/[^A-Za-z0-9._-]+/, "_").replaceAll(/^_+|_+$/, "")
}

String stem(String filename) {
    int dot = filename.lastIndexOf(".")
    return dot > 0 ? filename.substring(0, dot) : filename
}

void ensureTargetDoesNotExist(File file) {
    if (file.exists()) {
        throw new IllegalArgumentException("Output file already exists: " + file.absolutePath)
    }
}

void saveTiff(Image image, File outputFile, String title) {
    ensureTargetDoesNotExist(outputFile)
    image.name(title)
    ImagePlus out = image.imageplus()
    out.setTitle(title)
    IJ.saveAsTiff(out, outputFile.absolutePath)
    out.changes = false
    out.close()
    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write TIFF: " + outputFile.absolutePath)
    }
}

void saveLines(File outputFile, List<String> lines) {
    ensureTargetDoesNotExist(outputFile)
    outputFile.withWriter("UTF-8") { writer ->
        lines.each { line -> writer.println(line) }
    }
    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write file: " + outputFile.absolutePath)
    }
}

Image prepareFeatureImage(ImagePlus imp, boolean usePhysicalCalibration) {
    Image image = Image.wrap(imp)
    if (!usePhysicalCalibration) {
        image.aspects(new Aspects())
    }
    return image
}

FloatImage prepareFloatFeatureImage(ImagePlus imp, boolean usePhysicalCalibration) {
    FloatImage image = new FloatImage(Image.wrap(imp))
    if (!usePhysicalCalibration) {
        image.aspects(new Aspects())
    }
    return image
}

double parseOptionalThreshold(String text, String label) {
    if (text == null || text.trim().isEmpty()) {
        return Double.NaN
    }
    try {
        return Double.parseDouble(text.trim())
    }
    catch (Exception ignored) {
        throw new IllegalArgumentException("Invalid ${label} threshold value: ${text}")
    }
}

Roi buildOptionalRoi(ImagePlus imp) {
    if (roiWidth <= 0 || roiHeight <= 0) {
        return null
    }
    if (roiX < 0 || roiY < 0) {
        throw new IllegalArgumentException("ROI coordinates must be non-negative.")
    }
    if (roiX + roiWidth > imp.getWidth() || roiY + roiHeight > imp.getHeight()) {
        throw new IllegalArgumentException(
            "ROI extends beyond image bounds: " +
            "x=${roiX}, y=${roiY}, width=${roiWidth}, height=${roiHeight}, " +
            "image=${imp.getWidth()}x${imp.getHeight()}"
        )
    }
    return new Roi(roiX, roiY, roiWidth, roiHeight)
}

List<String> parseStatisticNames(String text) {
    List<String> names = []
    text.split(",").each { raw ->
        String name = raw.trim()
        if (!name.isEmpty()) {
            if (!STATISTIC_INDEX.containsKey(name)) {
                throw new IllegalArgumentException("Unsupported statistics metric: " + name)
            }
            names << name
        }
    }
    if (names.isEmpty()) {
        throw new IllegalArgumentException("Statistics metrics list is empty.")
    }
    return names
}

Map<String, Double> computeStatistics(ImagePlus imp, Roi roi, List<String> metricNames) {
    Image image = Image.wrap(imp)
    Coordinates lower = new Coordinates()
    Coordinates upper = new Coordinates()
    Image maskImage = null

    if (roi != null) {
        imp.setRoi(roi)
        def bounds = roi.getBounds()
        lower.x = bounds.x
        lower.y = bounds.y
        upper.x = bounds.x + bounds.width - 1
        upper.y = bounds.y + bounds.height - 1

        def maskProcessor = roi.getMask()
        if (maskProcessor == null) {
            maskProcessor = new ByteProcessor(1, 1)
            maskProcessor.set(0, 0, 255)
        }
        maskImage = Image.wrap(new ImagePlus("Mask", maskProcessor))
    }
    else {
        def dims = image.dimensions()
        lower.x = 0
        lower.y = 0
        upper.x = dims.x - 1
        upper.y = dims.y - 1
        def fullMask = new ByteProcessor(1, 1)
        fullMask.set(0, 0, 255)
        maskImage = Image.wrap(new ImagePlus("Mask", fullMask))
    }

    Statistics statistics = new Statistics()
    statistics.run(image, lower, upper, maskImage)

    Map<String, Double> values = new LinkedHashMap<String, Double>()
    metricNames.each { name ->
        values[name] = statistics.get(STATISTIC_INDEX[name])
    }
    return values
}

if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile.absolutePath)
}

if (!outputDir.exists() && !outputDir.mkdirs()) {
    throw new IllegalArgumentException("Could not create output directory: " + outputDir.absolutePath)
}

ImagePlus imp = IJ.openImage(inputFile.absolutePath)
if (imp == null) {
    throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
}

if (imp.getType() == ImagePlus.COLOR_RGB || imp.getType() == ImagePlus.COLOR_256) {
    throw new IllegalArgumentException("FeatureJ requires grayscale input images. Convert RGB or indexed-color images before running.")
}

String baseName = stem(inputFile.name)
String modeSlug = slug(mode.toLowerCase(Locale.ROOT))
String prefix = baseName + "-" + modeSlug

switch (mode) {
    case "Derivatives":
        FloatImage derivative = new FloatImage(prepareFeatureImage(imp, usePhysicalCalibration))
        new Differentiator().run(derivative, smoothingScale, derivativeXOrder, derivativeYOrder, derivativeZOrder)
        saveTiff(
            derivative,
            new File(outputDir, prefix + "-x${derivativeXOrder}_y${derivativeYOrder}_z${derivativeZOrder}.tif"),
            prefix + "-derivative"
        )
        break

    case "Edges":
        FloatImage edges = prepareFloatFeatureImage(imp, usePhysicalCalibration)
        double lower = parseOptionalThreshold(edgesLowerThreshold, "lower")
        double higher = parseOptionalThreshold(edgesHigherThreshold, "higher")

        if (edgesComputeGradient || edgesSuppressNonMaximum) {
            Edges detector = new Edges()
            edges = (FloatImage) detector.run(edges, smoothingScale, edgesSuppressNonMaximum)
        }

        Thresholder thresholder = new Thresholder()
        boolean hasLower = !Double.isNaN(lower)
        boolean hasHigher = !Double.isNaN(higher)
        if (hasLower && hasHigher) {
            thresholder.hysteresis(edges, lower, higher)
        }
        else if (hasLower) {
            thresholder.hard(edges, lower)
        }
        else if (hasHigher) {
            thresholder.hard(edges, higher)
        }

        saveTiff(edges, new File(outputDir, prefix + ".tif"), prefix + "-edges")
        break

    case "Laplacian":
        FloatImage laplacian = prepareFloatFeatureImage(imp, usePhysicalCalibration)
        if (laplacianCompute) {
            Laplacian op = new Laplacian()
            laplacian = (FloatImage) op.run(laplacian, smoothingScale)
        }
        if (laplacianDetectZeroCrossings) {
            new ZeroCrosser().run(laplacian)
        }
        saveTiff(laplacian, new File(outputDir, prefix + ".tif"), prefix + "-laplacian")
        break

    case "Hessian":
        Image hessianInput = prepareFeatureImage(imp, usePhysicalCalibration)
        def eigenimages = new Hessian().run(new FloatImage(hessianInput), smoothingScale, hessianAbsolute)
        if (eigenimages.size() == 2) {
            if (hessianLargest) {
                saveTiff(eigenimages[0], new File(outputDir, prefix + "-largest.tif"), prefix + "-largest")
            }
            if (hessianSmallest) {
                saveTiff(eigenimages[1], new File(outputDir, prefix + "-smallest.tif"), prefix + "-smallest")
            }
        }
        else if (eigenimages.size() == 3) {
            if (hessianLargest) {
                saveTiff(eigenimages[0], new File(outputDir, prefix + "-largest.tif"), prefix + "-largest")
            }
            if (hessianMiddle) {
                saveTiff(eigenimages[1], new File(outputDir, prefix + "-middle.tif"), prefix + "-middle")
            }
            if (hessianSmallest) {
                saveTiff(eigenimages[2], new File(outputDir, prefix + "-smallest.tif"), prefix + "-smallest")
            }
        }
        break

    case "Structure":
        Image structureInput = prepareFeatureImage(imp, usePhysicalCalibration)
        def eigenimages = new Structure().run(new FloatImage(structureInput), smoothingScale, structureIntegrationScale)
        if (eigenimages.size() == 2) {
            if (structureLargest) {
                saveTiff(eigenimages[0], new File(outputDir, prefix + "-largest.tif"), prefix + "-largest")
            }
            if (structureSmallest) {
                saveTiff(eigenimages[1], new File(outputDir, prefix + "-smallest.tif"), prefix + "-smallest")
            }
        }
        else if (eigenimages.size() == 3) {
            if (structureLargest) {
                saveTiff(eigenimages[0], new File(outputDir, prefix + "-largest.tif"), prefix + "-largest")
            }
            if (structureMiddle) {
                saveTiff(eigenimages[1], new File(outputDir, prefix + "-middle.tif"), prefix + "-middle")
            }
            if (structureSmallest) {
                saveTiff(eigenimages[2], new File(outputDir, prefix + "-smallest.tif"), prefix + "-smallest")
            }
        }
        break

    case "Statistics":
        Roi roi = buildOptionalRoi(imp)
        List<String> metricNames = parseStatisticNames(statisticsMetrics)
        Map<String, Double> values = computeStatistics(imp, roi, metricNames)

        List<String> lines = ["metric,value"]
        values.each { name, value ->
            lines << String.format(Locale.US, "%s,%.${statisticsDecimals}f", name, value)
        }
        saveLines(new File(outputDir, prefix + ".csv"), lines)

        List<String> summary = [
            "input=" + inputFile.absolutePath,
            "mode=" + mode,
            "roi=" + (roi == null ? "whole-image" : "${roiX},${roiY},${roiWidth},${roiHeight}")
        ]
        saveLines(new File(outputDir, prefix + "-summary.txt"), summary)
        break

    default:
        throw new IllegalArgumentException("Unsupported mode: " + mode)
}

imp.changes = false
imp.close()

if (quitWhenDone) {
    System.exit(0)
}
