// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Input 3D TIFF", value = "/data/your_3d_stack.tif") inputFile
#@ String (label = "Filter token", value = "Mean") filterToken
#@ Float (label = "Radius X (pixels)", value = 1.0, min = 0.0) radiusX
#@ Float (label = "Radius Y (pixels)", value = 1.0, min = 0.0) radiusY
#@ Float (label = "Radius Z (pixels)", value = 1.0, min = 0.0) radiusZ
#@ Integer (label = "CPU threads", value = 1, min = 1) cpuThreads
#@ File (label = "Filtered TIFF", style = "save", value = "/data/3d_imagej_suite_output/filtered_only.tif") outputFile

import ij.IJ
import ij.ImagePlus
import ij.WindowManager

/*
 * 3D ImageJ Suite — batch 3D filtering
 *
 * PURPOSE:
 *   1. Open a 3D TIFF stack
 *   2. Apply the suite's 3D Fast Filters command
 *   3. Save the created filtered stack
 *
 * VALIDATED COMMAND FORM:
 *   IJ.run(imp, "3D Fast Filters",
 *       "filter=Mean radius_x_pix=1.0 radius_y_pix=1.0 radius_z_pix=1.0 Nb_cpus=1")
 *
 * ACCEPTED FILTER TOKENS:
 *   Mean, Median, Minimum, Maximum, MaximumLocal, TopHat,
 *   OpenGray, CloseGray, Variance, Sobel, Adaptive
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

int[] imageIds() {
    int[] ids = WindowManager.getIDList()
    return ids == null ? new int[0] : ids
}

ImagePlus findNewImage(int[] beforeIds) {
    Set<Integer> before = beforeIds.collect { it as Integer } as Set<Integer>
    int[] afterIds = WindowManager.getIDList()
    if (afterIds == null) {
        return null
    }
    for (int id : afterIds) {
        if (!before.contains(id)) {
            return WindowManager.getImage(id)
        }
    }
    return WindowManager.getCurrentImage()
}

Set<String> allowedFilters = [
    "Mean",
    "Median",
    "Minimum",
    "Maximum",
    "MaximumLocal",
    "TopHat",
    "OpenGray",
    "CloseGray",
    "Variance",
    "Sobel",
    "Adaptive"
] as Set<String>

requireReadable(inputFile, "Input 3D TIFF")
requireFreshWritable(outputFile, "Filtered TIFF")

if (!allowedFilters.contains(filterToken)) {
    throw new IllegalArgumentException("Unsupported filter token: " + filterToken)
}

ImagePlus sourceImp = null
ImagePlus filteredImp = null

try {
    sourceImp = IJ.openImage(inputFile.absolutePath)
    if (sourceImp == null) {
        throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
    }

    int[] before = imageIds()
    String arg = [
        "filter=" + filterToken,
        "radius_x_pix=" + radiusX,
        "radius_y_pix=" + radiusY,
        "radius_z_pix=" + radiusZ,
        "Nb_cpus=" + cpuThreads
    ].join(" ")

    IJ.run(sourceImp, "3D Fast Filters", arg)
    filteredImp = findNewImage(before)
    if (filteredImp == null) {
        throw new IllegalStateException("3D Fast Filters did not create an output image.")
    }

    IJ.saveAs(filteredImp, "Tiff", outputFile.absolutePath)
    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Could not save filtered TIFF: " + outputFile.absolutePath)
    }

    IJ.log("3D Fast Filters workflow complete")
    IJ.log("Input   : " + inputFile.absolutePath)
    IJ.log("Filter  : " + filterToken)
    IJ.log("Output  : " + outputFile.absolutePath)
}
finally {
    closeImage(filteredImp)
    closeImage(sourceImp)
}
