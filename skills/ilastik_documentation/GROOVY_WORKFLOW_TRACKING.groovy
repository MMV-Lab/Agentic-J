// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Tracking project", value = "/data/ilastik_validation/core/TrackingwLearning5t2d_wPred.ilp") projectFile
#@ File (label = "Raw input HDF5", value = "/data/ilastik_validation/core/5t2d_simple.h5") rawFile
#@ String (label = "Raw dataset name", value = "/simple") rawDatasetName
#@ String (label = "Raw axis order", value = "tyx") rawAxisOrder
#@ File (label = "Second input HDF5", value = "/data/ilastik_validation/core/5t2d_Probabilities_simple.h5") secondInputFile
#@ String (label = "Second input dataset name", value = "/simple") secondInputDatasetName
#@ String (label = "Second input axis order", value = "tyxc") secondInputAxisOrder
#@ String (label = "Second input type", choices = {"Probabilities", "Segmentation"}, value = "Probabilities") secondInputType
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/core/tracking_result.tif") outputFile
#@ Integer (label = "Threads (-1 for all)", value = -1) numThreads
#@ Integer (label = "Max RAM (MiB)", value = 4096) maxRamMb
#@ org.scijava.command.CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import ij.IJ
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.TrackingCommand

/*
 * ilastik — Run a trained Tracking project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Import one raw time-series HDF5 dataset and one matching second-input HDF5 dataset
 *   3. Apply a trained ilastik Tracking project
 *   4. Save the returned tracking result as TIFF
 *
 * REQUIRED INPUTS:
 *   executablePath         - ilastik executable path; leave empty to use ILASTIK_EXECUTABLE
 *   projectFile            - trained Tracking .ilp file
 *   rawFile                - raw-image HDF5 file
 *   rawDatasetName         - dataset path inside rawFile
 *   rawAxisOrder           - row-major axis string for rawFile
 *   secondInputFile        - probability or segmentation HDF5 file
 *   secondInputDatasetName - dataset path inside secondInputFile
 *   secondInputAxisOrder   - row-major axis string for secondInputFile
 *   secondInputType        - `Probabilities` or `Segmentation`
 *   outputFile             - TIFF path to write
 *   numThreads             - ilastik thread limit, use `-1` for all available threads
 *   maxRamMb               - ilastik RAM limit in MiB
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own project, input, and output files.
 *   - Provide executablePath explicitly or set ILASTIK_EXECUTABLE in the environment.
 *   - The `.ilp` project must be closed in ilastik before Fiji runs it.
 *   - The default validated configuration uses probabilities as the second input.
 *   - The sample project used here expects `inputdata/5t2d_simple.h5` and `inputdata/5t2d_Probabilities_simple.h5` next to the `.ilp` file.
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
if (rawFile == null || !rawFile.exists()) {
    throw new IllegalArgumentException("Raw HDF5 file not found: " + rawFile)
}
if (secondInputFile == null || !secondInputFile.exists()) {
    throw new IllegalArgumentException("Second-input HDF5 file not found: " + secondInputFile)
}
if (rawDatasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("rawDatasetName must not be empty")
}
if (rawAxisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("rawAxisOrder must not be empty")
}
if (secondInputDatasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("secondInputDatasetName must not be empty")
}
if (secondInputAxisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("secondInputAxisOrder must not be empty")
}
if (secondInputType !in ["Probabilities", "Segmentation"]) {
    throw new IllegalArgumentException(
        "secondInputType must be Probabilities or Segmentation: " + secondInputType)
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

    def rawImport = new ImportCommand()
    rawImport.setContext(context)
    rawImport.select = rawFile
    rawImport.datasetName = rawDatasetName
    rawImport.axisOrder = rawAxisOrder
    rawImport.run()

    def rawOutput = rawImport.output
    if (rawOutput == null) {
        throw new IllegalStateException("ImportCommand returned null raw output")
    }

    def secondImport = new ImportCommand()
    secondImport.setContext(context)
    secondImport.select = secondInputFile
    secondImport.datasetName = secondInputDatasetName
    secondImport.axisOrder = secondInputAxisOrder
    secondImport.run()

    def secondOutput = secondImport.output
    if (secondOutput == null) {
        throw new IllegalStateException("ImportCommand returned null second input")
    }

    IJ.log("ilastik Tracking")
    IJ.log("Project: " + projectFile.absolutePath)
    IJ.log("Raw input: " + rawFile.absolutePath + " " + rawDatasetName)
    IJ.log("Second input: " + secondInputFile.absolutePath + " " + secondInputDatasetName)
    IJ.log("Second input type: " + secondInputType)

    def rawDataset = datasetService.create(rawOutput)
    def secondDataset = datasetService.create(secondOutput)

    def future = command.run(TrackingCommand, true,
        "projectFileName", projectFile,
        "inputImage", rawDataset,
        "inputProbOrSegImage", secondDataset,
        "secondInputType", secondInputType
    )

    if (future == null) {
        throw new IllegalStateException("TrackingCommand returned null future")
    }

    def module = future.get()
    def predictions = module.getOutput("predictions")
    if (predictions == null) {
        throw new IllegalStateException("TrackingCommand returned null predictions")
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
