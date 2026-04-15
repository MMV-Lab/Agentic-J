// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Pixel Classification project", value = "/data/ilastik_validation/pixel_class_2d_cells_apoptotic.ilp") projectFile
#@ File (label = "Input TIFF", value = "/data/ilastik_validation/2d_cells_apoptotic.tif") inputFile
#@ String (label = "Output type", choices = {"Probabilities", "Segmentation"}, value = "Probabilities") outputType
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/pixel_class_probabilities.tif") outputFile
#@ Integer (label = "Threads (-1 for all)", value = -1) numThreads
#@ Integer (label = "Max RAM (MiB)", value = 4096) maxRamMb
#@ org.scijava.command.CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import ij.IJ
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.PixelClassificationCommand

/*
 * ilastik — Run a trained Pixel Classification project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Open a raw input image as a Dataset
 *   3. Apply a trained ilastik Pixel Classification project
 *   4. Save the returned probabilities or segmentation as TIFF
 *
 * REQUIRED INPUTS:
 *   executablePath - ilastik executable path; leave empty to use ILASTIK_EXECUTABLE
 *   projectFile    - trained Pixel Classification .ilp file
 *   inputFile      - raw image to process
 *   outputType     - `Probabilities` or `Segmentation`
 *   outputFile     - TIFF path to write
 *   numThreads     - ilastik thread limit, use `-1` for all available threads
 *   maxRamMb       - ilastik RAM limit in MiB
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own project, input, and output files.
 *   - Provide executablePath explicitly or set ILASTIK_EXECUTABLE in the environment.
 *   - The `.ilp` project must be closed in ilastik before Fiji runs it.
 *   - The image dimensionality and channel layout must match the project.
 *   - Choose a new output path instead of overwriting an existing file.
 */

String resolvedExecutablePath = executablePath?.trim()
if (!resolvedExecutablePath) {
    resolvedExecutablePath = System.getenv("ILASTIK_EXECUTABLE") ?: ""
}
if (!resolvedExecutablePath) {
    throw new IllegalArgumentException(
        "Set executablePath or ILASTIK_EXECUTABLE before running this workflow")
}

def executableFile = new File(resolvedExecutablePath)
if (!executableFile.exists()) {
    throw new IllegalArgumentException("Executable not found: " + resolvedExecutablePath)
}
if (projectFile == null || !projectFile.exists()) {
    throw new IllegalArgumentException("Project file not found: " + projectFile)
}
if (inputFile == null || !inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile)
}
if (outputType !in ["Probabilities", "Segmentation"]) {
    throw new IllegalArgumentException(
        "outputType must be Probabilities or Segmentation: " + outputType)
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output TIFF file must be provided")
}
outputFile.parentFile?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException(
        "Output file already exists: " + outputFile.absolutePath)
}

def options = optionsService.getOptions(IlastikOptions)
def previousExecutableFile = options.executableFile
int previousNumThreads = options.numThreads
int previousMaxRamMb = options.maxRamMb

try {
    options.executableFile = executableFile
    options.numThreads = numThreads
    options.maxRamMb = maxRamMb
    options.save()

    IJ.log("ilastik Pixel Classification")
    IJ.log("Project: " + projectFile.absolutePath)
    IJ.log("Input: " + inputFile.absolutePath)
    IJ.log("Output type: " + outputType)

    def dataset = datasetIOService.open(inputFile.absolutePath)
    def future = command.run(PixelClassificationCommand, true,
        "projectFileName", projectFile,
        "inputImage", dataset,
        "pixelClassificationType", outputType
    )

    if (future == null) {
        throw new IllegalStateException("PixelClassificationCommand returned null future")
    }

    def module = future.get()
    def predictions = module.getOutput("predictions")
    if (predictions == null) {
        throw new IllegalStateException("PixelClassificationCommand returned null predictions")
    }

    def outputDataset = datasetService.create(predictions)
    datasetIOService.save(outputDataset, outputFile.absolutePath)
    IJ.log("Saved prediction: " + outputFile.absolutePath)
}
finally {
    options.executableFile = previousExecutableFile
    options.numThreads = previousNumThreads
    options.maxRamMb = previousMaxRamMb
    options.save()
}
