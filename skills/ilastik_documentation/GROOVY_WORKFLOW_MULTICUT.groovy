// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
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
 *   EXECUTABLE    - absolute path to the ilastik executable
 *   PROJECT_FILE  - absolute path to a trained Multicut .ilp file
 *   INPUT_H5      - absolute path to the raw-image HDF5 file
 *   INPUT_DATASET - dataset path inside INPUT_H5
 *   INPUT_AXES    - row-major axis string for INPUT_H5
 *   PROB_H5       - absolute path to the boundary-probability HDF5 file
 *   PROB_DATASET  - dataset path inside PROB_H5
 *   PROB_AXES     - row-major axis string for PROB_H5
 *   OUTPUT_TIFF   - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - The .ilp project must be closed in ilastik before Fiji runs it
 *   - The sample project used here expects inputdata/3d1c.h5 and inputdata/3d1c_Probabilities.h5 next to the .ilp file
 *   - The raw image and boundary probabilities must describe the same volume
 */

String EXECUTABLE = "/home/imagentj/ilastik-1.4.1.post1-Linux/run_ilastik.sh"
String PROJECT_FILE = "/data/ilastik_validation/core/Boundary-basedSegmentationwMulticut3d1c.ilp"
String INPUT_H5 = "/data/ilastik_validation/core/3d1c.h5"
String INPUT_DATASET = "/data"
String INPUT_AXES = "zyxc"
String PROB_H5 = "/data/ilastik_validation/core/3d1c_Probabilities.h5"
String PROB_DATASET = "/exported_data"
String PROB_AXES = "zyxc"
String OUTPUT_TIFF = "/data/ilastik_validation/core/multicut_segmentation.tif"

def executableFile = new File(EXECUTABLE)
def projectFile = new File(PROJECT_FILE)
def rawFile = new File(INPUT_H5)
def probFile = new File(PROB_H5)
def outputFile = new File(OUTPUT_TIFF)

if (!executableFile.exists()) {
    throw new IllegalArgumentException("Executable not found: " + EXECUTABLE)
}
if (!projectFile.exists()) {
    throw new IllegalArgumentException("Project file not found: " + PROJECT_FILE)
}
if (!rawFile.exists()) {
    throw new IllegalArgumentException("Raw HDF5 file not found: " + INPUT_H5)
}
if (!probFile.exists()) {
    throw new IllegalArgumentException("Probability HDF5 file not found: " + PROB_H5)
}
if (INPUT_DATASET.trim().isEmpty()) {
    throw new IllegalArgumentException("INPUT_DATASET must not be empty")
}
if (INPUT_AXES.trim().isEmpty()) {
    throw new IllegalArgumentException("INPUT_AXES must not be empty")
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
rawImport.datasetName = INPUT_DATASET
rawImport.axisOrder = INPUT_AXES
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
    throw new IllegalStateException("ImportCommand returned null probability output")
}

def rawDataset = datasetService.create(rawOutput)
def boundaryDataset = datasetService.create(probOutput)

def future = command.run(MulticutCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "boundaryPredictionImage", boundaryDataset
)
println("future=" + future)

if (future == null) {
    throw new IllegalStateException("MulticutCommand returned null future")
}

def module = future.get()
println("module=" + module)

def predictions = module.getOutput("predictions")
println("predictions=" + predictions)
if (predictions == null) {
    throw new IllegalStateException("MulticutCommand returned null predictions")
}

def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
