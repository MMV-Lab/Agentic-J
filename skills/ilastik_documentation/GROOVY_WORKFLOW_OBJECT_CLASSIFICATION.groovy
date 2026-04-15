// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Object Classification project", value = "/data/ilastik_validation/obj_class_2d_cells_apoptotic.ilp") projectFile
#@ File (label = "Raw input TIFF", value = "/data/ilastik_validation/2d_cells_apoptotic.tif") inputFile
#@ File (label = "Second input TIFF", value = "/data/ilastik_validation/pixel_class_probabilities.tif") secondInputFile
#@ String (label = "Second input type", choices = {"Probabilities", "Segmentation"}, value = "Probabilities") secondInputType
#@ String (label = "Output type", choices = {"Object Predictions", "Object Probabilities", "Object Identities"}, value = "Object Predictions") outputType
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/object_predictions.tif") outputFile
#@ Integer (label = "Threads (-1 for all)", value = -1) numThreads
#@ Integer (label = "Max RAM (MiB)", value = 4096) maxRamMb
#@ org.scijava.command.CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import ij.IJ
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.ObjectClassificationCommand

/*
 * ilastik — Run a trained Object Classification project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Open one raw image and one matching probability or segmentation image
 *   3. Apply a trained ilastik Object Classification project
 *   4. Save the returned object-classification result as TIFF
 *
 * REQUIRED INPUTS:
 *   executablePath  - ilastik executable path; leave empty to use ILASTIK_EXECUTABLE
 *   projectFile     - trained Object Classification .ilp file
 *   inputFile       - raw image
 *   secondInputFile - probability or segmentation image for the same scene
 *   secondInputType - `Probabilities` or `Segmentation`
 *   outputType      - `Object Predictions`, `Object Probabilities`, or `Object Identities`
 *   outputFile      - TIFF path to write
 *   numThreads      - ilastik thread limit, use `-1` for all available threads
 *   maxRamMb        - ilastik RAM limit in MiB
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own project, input, and output files.
 *   - Provide executablePath explicitly or set ILASTIK_EXECUTABLE in the environment.
 *   - The `.ilp` project must be closed in ilastik before Fiji runs it.
 *   - The default second input points to the default probabilities output from GROOVY_WORKFLOW_PIXEL_CLASSIFICATION.groovy.
 *   - Choose a new output path instead of overwriting an existing file.
 */

def validOutputs = [
    "Object Predictions",
    "Object Probabilities",
    "Object Identities"
]

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
if (secondInputFile == null || !secondInputFile.exists()) {
    throw new IllegalArgumentException("Second input image not found: " + secondInputFile)
}
if (secondInputType !in ["Probabilities", "Segmentation"]) {
    throw new IllegalArgumentException(
        "secondInputType must be Probabilities or Segmentation: " + secondInputType)
}
if (!(outputType in validOutputs)) {
    throw new IllegalArgumentException(
        "outputType must be one of " + validOutputs + ": " + outputType)
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

    IJ.log("ilastik Object Classification")
    IJ.log("Project: " + projectFile.absolutePath)
    IJ.log("Input: " + inputFile.absolutePath)
    IJ.log("Second input: " + secondInputFile.absolutePath)
    IJ.log("Second input type: " + secondInputType)
    IJ.log("Output type: " + outputType)

    def rawDataset = datasetIOService.open(inputFile.absolutePath)
    def secondDataset = datasetIOService.open(secondInputFile.absolutePath)

    def future = command.run(ObjectClassificationCommand, true,
        "projectFileName", projectFile,
        "inputImage", rawDataset,
        "inputProbOrSegImage", secondDataset,
        "secondInputType", secondInputType,
        "objectExportSource", outputType
    )

    if (future == null) {
        throw new IllegalStateException("ObjectClassificationCommand returned null future")
    }

    def module = future.get()
    def predictions = module.getOutput("predictions")
    if (predictions == null) {
        throw new IllegalStateException("ObjectClassificationCommand returned null predictions")
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
