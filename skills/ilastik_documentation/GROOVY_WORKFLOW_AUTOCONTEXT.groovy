// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Autocontext project", value = "/data/ilastik_validation/core/Autocontext2d3c.ilp") projectFile
#@ File (label = "Input HDF5", value = "/data/ilastik_validation/core/2d3c.h5") inputFile
#@ String (label = "Dataset name", value = "/data") datasetName
#@ String (label = "Axis order", value = "yxc") axisOrder
#@ String (label = "Output type", choices = {"Probabilities", "Segmentation"}, value = "Probabilities") outputType
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/core/autocontext_probabilities.tif") outputFile
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
import org.ilastik.ilastik4ij.workflow.AutocontextCommand

/*
 * ilastik — Run a trained Autocontext project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Import one raw HDF5 dataset as a Dataset
 *   3. Apply a trained ilastik Autocontext project
 *   4. Save the returned probabilities or segmentation as TIFF
 *
 * REQUIRED INPUTS:
 *   executablePath - ilastik executable path; leave empty to use ILASTIK_EXECUTABLE
 *   projectFile    - trained Autocontext .ilp file
 *   inputFile      - raw image exported as HDF5
 *   datasetName    - dataset path inside inputFile
 *   axisOrder      - row-major axis string for inputFile
 *   outputType     - `Probabilities` or `Segmentation`
 *   outputFile     - TIFF path to write
 *   numThreads     - ilastik thread limit, use `-1` for all available threads
 *   maxRamMb       - ilastik RAM limit in MiB
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own project, input, and output files.
 *   - Provide executablePath explicitly or set ILASTIK_EXECUTABLE in the environment.
 *   - The `.ilp` project must be closed in ilastik before Fiji runs it.
 *   - The sample project used here expects `inputdata/2d3c.h5` next to the `.ilp` file.
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
    throw new IllegalArgumentException("Input HDF5 file not found: " + inputFile)
}
if (datasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("datasetName must not be empty")
}
if (axisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("axisOrder must not be empty")
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

    def importCommand = new ImportCommand()
    importCommand.setContext(context)
    importCommand.select = inputFile
    importCommand.datasetName = datasetName
    importCommand.axisOrder = axisOrder
    importCommand.run()

    def imported = importCommand.output
    if (imported == null) {
        throw new IllegalStateException("ImportCommand returned null output")
    }

    IJ.log("ilastik Autocontext")
    IJ.log("Project: " + projectFile.absolutePath)
    IJ.log("Input: " + inputFile.absolutePath + " " + datasetName)
    IJ.log("Output type: " + outputType)

    def dataset = datasetService.create(imported)
    def future = command.run(AutocontextCommand, true,
        "projectFileName", projectFile,
        "inputImage", dataset,
        "AutocontextPredictionType", outputType
    )

    if (future == null) {
        throw new IllegalStateException("AutocontextCommand returned null future")
    }

    def module = future.get()
    def predictions = module.getOutput("predictions")
    if (predictions == null) {
        throw new IllegalStateException("AutocontextCommand returned null predictions")
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
