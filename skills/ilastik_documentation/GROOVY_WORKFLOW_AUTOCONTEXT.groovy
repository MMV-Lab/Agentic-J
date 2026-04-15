// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.AutocontextCommand

/*
 * ilastik — Run a trained Autocontext project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Open a raw input image as a Dataset
 *   3. Apply a trained ilastik Autocontext project
 *   4. Save the returned probabilities or segmentation as TIFF
 *
 * REQUIRED INPUTS:
 *   EXECUTABLE   - absolute path to the ilastik executable
 *   PROJECT_FILE - absolute path to a trained Autocontext .ilp file
 *   INPUT_H5     - absolute path to the raw image exported as HDF5
 *   DATASET_NAME - dataset path inside INPUT_H5
 *   AXIS_ORDER   - row-major axis string for INPUT_H5
 *   OUTPUT_TYPE  - Probabilities or Segmentation
 *   OUTPUT_TIFF  - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - The .ilp project must be closed in ilastik before Fiji runs it
 *   - The sample project used here expects inputdata/2d3c.h5 next to the .ilp file
 *   - The dataset dimensionality and channel layout must match the project
 */

String EXECUTABLE = "/home/imagentj/ilastik-1.4.1.post1-Linux/run_ilastik.sh"
String PROJECT_FILE = "/data/ilastik_validation/core/Autocontext2d3c.ilp"
String INPUT_H5 = "/data/ilastik_validation/core/2d3c.h5"
String DATASET_NAME = "/data"
String AXIS_ORDER = "yxc"
String OUTPUT_TYPE = "Probabilities"
String OUTPUT_TIFF = "/data/ilastik_validation/core/autocontext_probabilities.tif"

if (!(OUTPUT_TYPE in ["Probabilities", "Segmentation"])) {
    throw new IllegalArgumentException(
        "OUTPUT_TYPE must be Probabilities or Segmentation: " + OUTPUT_TYPE)
}

def executableFile = new File(EXECUTABLE)
def projectFile = new File(PROJECT_FILE)
def inputFile = new File(INPUT_H5)
def outputFile = new File(OUTPUT_TIFF)

if (!executableFile.exists()) {
    throw new IllegalArgumentException("Executable not found: " + EXECUTABLE)
}
if (!projectFile.exists()) {
    throw new IllegalArgumentException("Project file not found: " + PROJECT_FILE)
}
if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input HDF5 file not found: " + INPUT_H5)
}
if (DATASET_NAME.trim().isEmpty()) {
    throw new IllegalArgumentException("DATASET_NAME must not be empty")
}
if (AXIS_ORDER.trim().isEmpty()) {
    throw new IllegalArgumentException("AXIS_ORDER must not be empty")
}
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    outputFile.delete()
}

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = executableFile
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = inputFile
importCommand.datasetName = DATASET_NAME
importCommand.axisOrder = AXIS_ORDER
importCommand.run()

def imported = importCommand.output
println("imported=" + imported)
if (imported == null) {
    throw new IllegalStateException("ImportCommand returned null output")
}

def dataset = datasetService.create(imported)
println("dataset=" + dataset)

def future = command.run(AutocontextCommand, true,
    "projectFileName", projectFile,
    "inputImage", dataset,
    "AutocontextPredictionType", OUTPUT_TYPE
)
println("future=" + future)

if (future == null) {
    throw new IllegalStateException("AutocontextCommand returned null future")
}

def module = future.get()
println("module=" + module)

def predictions = module.getOutput("predictions")
println("predictions=" + predictions)
if (predictions == null) {
    throw new IllegalStateException("AutocontextCommand returned null predictions")
}

def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
