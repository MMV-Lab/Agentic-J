// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Input 3D TIFF", value = "/data/your_3d_stack.tif") inputFile
#@ String (label = "Auto-threshold method", value = "Otsu") autoThresholdMethod
#@ Boolean (label = "Separate touching nuclei", value = true) separateTouchingNuclei
#@ Float (label = "Manual threshold override (0 disables)", value = 0.0, min = 0.0) manualThreshold
#@ File (label = "Nuclei label TIFF", style = "save", value = "/data/3d_imagej_suite_output/nuclei_labels.tif") labelOutputFile

import ij.IJ
import ij.ImagePlus
import ij.process.AutoThresholder
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.segment.Segment3DNuclei
import mcib_plugins.analysis.SimpleMeasure

/*
 * 3D ImageJ Suite — nuclei segmentation
 *
 * PURPOSE:
 *   1. Open a 3D TIFF stack from disk
 *   2. Segment nuclei-like objects with Segment3DNuclei
 *   3. Save the labelled nuclei stack
 *
 * This workflow follows the suite's `3D Nuclei Segmentation` plugin and
 * exposes the threshold method, watershed-style separation, and manual
 * threshold override used by the underlying API.
 */

void requireReadable(File file, String label) {
    if (file == null || !file.exists()) {
        throw new IllegalArgumentException(label + " not found: " + file)
    }
}

void requireFreshWritable(File file, String label) {
    if (file == null) {
        throw new IllegalArgumentException(label + " must be provided")
    }
    File parent = file.getParentFile()
    if (parent != null && !parent.exists()) {
        parent.mkdirs()
    }
    if (file.exists()) {
        throw new IllegalArgumentException(label + " already exists: " + file.absolutePath)
    }
}

void closeImage(ImagePlus imp) {
    if (imp != null) {
        imp.changes = false
        imp.close()
    }
}

String stripTiffExtension(String name) {
    return name
        .replaceAll(/(?i)\.ome\.tiff?$/, "")
        .replaceAll(/(?i)\.tiff?$/, "")
}

AutoThresholder.Method parseThresholdMethod(String methodName) {
    try {
        return AutoThresholder.Method.valueOf(methodName)
    }
    catch (IllegalArgumentException ignored) {
        throw new IllegalArgumentException(
            "Unsupported autoThresholdMethod: " + methodName +
            ". Accepted ImageJ methods: " + AutoThresholder.getMethods().join(", ")
        )
    }
}

requireReadable(inputFile, "Input 3D TIFF")
requireFreshWritable(labelOutputFile, "Nuclei label TIFF")

ImagePlus sourceImp = null
ImagePlus analysisImp = null
ImagePlus labelImp = null

try {
    sourceImp = IJ.openImage(inputFile.absolutePath)
    if (sourceImp == null) {
        throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
    }

    analysisImp = SimpleMeasure.extractCurrentStack(sourceImp)
    if (analysisImp == null) {
        throw new IllegalStateException("Could not extract a 3D stack from: " + inputFile.absolutePath)
    }

    String baseTitle = stripTiffExtension(inputFile.getName())
    analysisImp.setTitle(baseTitle)

    Segment3DNuclei segmenter = new Segment3DNuclei(ImageHandler.wrap(analysisImp))
    segmenter.setMethod(parseThresholdMethod(autoThresholdMethod))
    segmenter.setSeparate(separateTouchingNuclei)
    segmenter.setManual(manualThreshold)

    def labelHandler = segmenter.segment()
    if (labelHandler == null) {
        throw new IllegalStateException("3D Nuclei Segmentation returned no label image")
    }

    labelImp = labelHandler.getImagePlus()
    if (labelImp == null) {
        throw new IllegalStateException("3D Nuclei Segmentation returned no ImagePlus")
    }
    labelImp.setCalibration(analysisImp.getCalibration())
    labelImp.setTitle(baseTitle + "-nuclei")

    IJ.saveAs(labelImp, "Tiff", labelOutputFile.absolutePath)
    if (!labelOutputFile.exists() || labelOutputFile.length() == 0) {
        throw new IllegalStateException("Could not save nuclei label TIFF: " + labelOutputFile.absolutePath)
    }

    double maxLabel = labelImp.getStatistics().max
    if (maxLabel <= 0) {
        throw new IllegalStateException("3D Nuclei Segmentation found no nuclei. Check the threshold method or input image.")
    }

    IJ.log("3D nuclei segmentation workflow complete")
    IJ.log("Input         : " + inputFile.absolutePath)
    IJ.log("Label TIFF    : " + labelOutputFile.absolutePath)
    IJ.log("Method        : " + autoThresholdMethod)
    IJ.log("Detected labels: " + Math.round(maxLabel))
}
finally {
    closeImage(labelImp)
    if (analysisImp != null && analysisImp != sourceImp) {
        closeImage(analysisImp)
    }
    closeImage(sourceImp)
}
