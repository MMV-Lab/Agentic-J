// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ String (label = "Ilastik executable path", value = "") executablePath
#@ File (label = "Multicut project", value = "/data/ilastik_validation/core/Boundary-basedSegmentationwMulticut3d1c.ilp") projectFile
#@ File (label = "Raw input HDF5", value = "/data/ilastik_validation/core/3d1c.h5") rawFile
#@ String (label = "Raw dataset name", value = "/data") rawDatasetName
#@ String (label = "Raw axis order", value = "zyxc") rawAxisOrder
#@ File (label = "Boundary-probability HDF5", value = "/data/ilastik_validation/core/3d1c_Probabilities.h5") boundaryFile
#@ String (label = "Boundary dataset name", value = "/exported_data") boundaryDatasetName
#@ String (label = "Boundary axis order", value = "zyxc") boundaryAxisOrder
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/core/multicut_segmentation.tif") outputFile
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
import org.ilastik.ilastik4ij.workflow.MulticutCommand

/*
 * ilastik — Run a trained Multicut project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Import one raw HDF5 dataset and one boundary-probability HDF5 dataset
 *   3. Apply a trained ilastik Multicut project
 *   4. Save the returned segmentation as TIFF
 *
 * REQUIRED INPUTS:
 *   executablePath      - ilastik executable path; leave empty to use ILASTIK_EXECUTABLE
 *   projectFile         - trained Multicut .ilp file
 *   rawFile             - raw-image HDF5 file
 *   rawDatasetName      - dataset path inside rawFile
 *   rawAxisOrder        - row-major axis string for rawFile
 *   boundaryFile        - boundary-probability HDF5 file
 *   boundaryDatasetName - dataset path inside boundaryFile
 *   boundaryAxisOrder   - row-major axis string for boundaryFile
 *   outputFile          - TIFF path to write
 *   numThreads          - ilastik thread limit, use `-1` for all available threads
 *   maxRamMb            - ilastik RAM limit in MiB
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own project, input, and output files.
 *   - Provide executablePath explicitly or set ILASTIK_EXECUTABLE in the environment.
 *   - The `.ilp` project must be closed in ilastik before Fiji runs it.
 *   - The sample project used here expects `inputdata/3d1c.h5` and `inputdata/3d1c_Probabilities.h5` next to the `.ilp` file.
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
if (boundaryFile == null || !boundaryFile.exists()) {
    throw new IllegalArgumentException("Boundary HDF5 file not found: " + boundaryFile)
}
if (rawDatasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("rawDatasetName must not be empty")
}
if (rawAxisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("rawAxisOrder must not be empty")
}
if (boundaryDatasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("boundaryDatasetName must not be empty")
}
if (boundaryAxisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("boundaryAxisOrder must not be empty")
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

    def boundaryImport = new ImportCommand()
    boundaryImport.setContext(context)
    boundaryImport.select = boundaryFile
    boundaryImport.datasetName = boundaryDatasetName
    boundaryImport.axisOrder = boundaryAxisOrder
    boundaryImport.run()

    def boundaryOutput = boundaryImport.output
    if (boundaryOutput == null) {
        throw new IllegalStateException("ImportCommand returned null boundary output")
    }

    IJ.log("ilastik Multicut")
    IJ.log("Project: " + projectFile.absolutePath)
    IJ.log("Raw input: " + rawFile.absolutePath + " " + rawDatasetName)
    IJ.log("Boundary input: " + boundaryFile.absolutePath + " " + boundaryDatasetName)

    def rawDataset = datasetService.create(rawOutput)
    def boundaryDataset = datasetService.create(boundaryOutput)

    def future = command.run(MulticutCommand, true,
        "projectFileName", projectFile,
        "inputImage", rawDataset,
        "boundaryPredictionImage", boundaryDataset
    )

    if (future == null) {
        throw new IllegalStateException("MulticutCommand returned null future")
    }

    def module = future.get()
    def predictions = module.getOutput("predictions")
    if (predictions == null) {
        throw new IllegalStateException("MulticutCommand returned null predictions")
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
