// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.TrackingCommand

/*
 * ilastik — Run a trained Tracking project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Import one raw time-series HDF5 dataset and one matching probability HDF5 dataset
 *   3. Apply a trained ilastik Tracking project
 *   4. Save the returned tracking result as TIFF
 *
 * REQUIRED INPUTS:
 *   EXECUTABLE       - absolute path to the ilastik executable
 *   PROJECT_FILE     - absolute path to a trained Tracking .ilp file
 *   RAW_H5           - absolute path to the raw-image HDF5 file
 *   RAW_DATASET      - dataset path inside RAW_H5
 *   RAW_AXES         - row-major axis string for RAW_H5
 *   PROB_H5          - absolute path to the probability HDF5 file
 *   PROB_DATASET     - dataset path inside PROB_H5
 *   PROB_AXES        - row-major axis string for PROB_H5
 *   SECOND_INPUT_TYPE - Probabilities or Segmentation
 *   OUTPUT_TIFF      - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - The .ilp project must be closed in ilastik before Fiji runs it
 *   - The sample project used here expects inputdata/5t2d_simple.h5 and inputdata/5t2d_Probabilities_simple.h5 next to the .ilp file
 *   - The raw image and the second input must describe the same time series
 */

String EXECUTABLE = "/home/imagentj/ilastik-1.4.1.post1-Linux/run_ilastik.sh"
String PROJECT_FILE = "/data/ilastik_validation/core/TrackingwLearning5t2d_wPred.ilp"
String RAW_H5 = "/data/ilastik_validation/core/5t2d_simple.h5"
String RAW_DATASET = "/simple"
String RAW_AXES = "tyx"
String PROB_H5 = "/data/ilastik_validation/core/5t2d_Probabilities_simple.h5"
String PROB_DATASET = "/simple"
String PROB_AXES = "tyxc"
String SECOND_INPUT_TYPE = "Probabilities"
String OUTPUT_TIFF = "/data/ilastik_validation/core/tracking_result.tif"

if (!(SECOND_INPUT_TYPE in ["Probabilities", "Segmentation"])) {
    throw new IllegalArgumentException(
        "SECOND_INPUT_TYPE must be Probabilities or Segmentation: " + SECOND_INPUT_TYPE)
}

def executableFile = new File(EXECUTABLE)
def projectFile = new File(PROJECT_FILE)
def rawFile = new File(RAW_H5)
def probFile = new File(PROB_H5)
def outputFile = new File(OUTPUT_TIFF)

if (!executableFile.exists()) {
    throw new IllegalArgumentException("Executable not found: " + EXECUTABLE)
}
if (!projectFile.exists()) {
    throw new IllegalArgumentException("Project file not found: " + PROJECT_FILE)
}
if (!rawFile.exists()) {
    throw new IllegalArgumentException("Raw HDF5 file not found: " + RAW_H5)
}
if (!probFile.exists()) {
    throw new IllegalArgumentException("Second-input HDF5 file not found: " + PROB_H5)
}
if (RAW_DATASET.trim().isEmpty()) {
    throw new IllegalArgumentException("RAW_DATASET must not be empty")
}
if (RAW_AXES.trim().isEmpty()) {
    throw new IllegalArgumentException("RAW_AXES must not be empty")
}
if (PROB_DATASET.trim().isEmpty()) {
    throw new IllegalArgumentException("PROB_DATASET must not be empty")
}
if (PROB_AXES.trim().isEmpty()) {
    throw new IllegalArgumentException("PROB_AXES must not be empty")
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

def rawImport = new ImportCommand()
rawImport.setContext(context)
rawImport.select = rawFile
rawImport.datasetName = RAW_DATASET
rawImport.axisOrder = RAW_AXES
rawImport.run()

def rawOutput = rawImport.output
println("rawOutput=" + rawOutput)
if (rawOutput == null) {
    throw new IllegalStateException("ImportCommand returned null raw output")
}

def probImport = new ImportCommand()
probImport.setContext(context)
probImport.select = probFile
probImport.datasetName = PROB_DATASET
probImport.axisOrder = PROB_AXES
probImport.run()

def probOutput = probImport.output
println("probOutput=" + probOutput)
if (probOutput == null) {
    throw new IllegalStateException("ImportCommand returned null second input")
}

def rawDataset = datasetService.create(rawOutput)
def secondDataset = datasetService.create(probOutput)

def future = command.run(TrackingCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", SECOND_INPUT_TYPE
)
println("future=" + future)

if (future == null) {
    throw new IllegalStateException("TrackingCommand returned null future")
}

def module = future.get()
println("module=" + module)

def predictions = module.getOutput("predictions")
println("predictions=" + predictions)
if (predictions == null) {
    throw new IllegalStateException("TrackingCommand returned null predictions")
}

def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
