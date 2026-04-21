#@ File (label = "Input image", value = "/data/example_1.tif") inputFile
#@ File (label = "Output directory", style = "directory", value = "/data/orientationj_validation/workflow_output") outputDir
#@ String (label = "Mode", choices = {"Analysis", "Distribution", "Vector Field", "Corner Harris", "Dominant Direction"}, value = "Analysis") mode
#@ String (label = "Gradient", choices = {"Cubic Spline", "Finite Difference", "Fourier", "Riesz Filters", "Gaussian"}, value = "Cubic Spline") gradientMethod
#@ Double (label = "Tensor sigma", value = 1.0, min = 0.01) tensorSigma
#@ Boolean (label = "Use radians", value = false) useRadians
#@ String (label = "Survey color space", choices = {"HSB", "RGB"}, value = "HSB") surveyColorSpace
#@ String (label = "Survey hue or red", choices = {"Orientation", "Coherency", "Energy", "Gradient-X", "Gradient-Y", "Constant", "Original-Image"}, value = "Orientation") surveyHue
#@ String (label = "Survey saturation or green", choices = {"Orientation", "Coherency", "Energy", "Gradient-X", "Gradient-Y", "Constant", "Original-Image"}, value = "Coherency") surveySaturation
#@ String (label = "Survey brightness or blue", choices = {"Orientation", "Coherency", "Energy", "Gradient-X", "Gradient-Y", "Constant", "Original-Image"}, value = "Original-Image") surveyBrightness
#@ Double (label = "Distribution min coherency (%)", value = 10.0, min = 0.0, max = 100.0) distributionMinCoherency
#@ Double (label = "Distribution min energy (%)", value = 5.0, min = 0.0, max = 100.0) distributionMinEnergy
#@ Integer (label = "Vector grid size", value = 24, min = 1) vectorGrid
#@ Double (label = "Vector scale (%)", value = 100.0, min = 0.0) vectorScale
#@ String (label = "Vector length mode", choices = {"Maximum", "Energy", "Coherency", "Energy x Coherency"}, value = "Maximum") vectorType
#@ Double (label = "Harris k", value = 0.05, min = 0.01, max = 0.2) harrisK
#@ Integer (label = "Harris window size", value = 3, min = 1) harrisWindowSize
#@ Double (label = "Harris min level (%)", value = 10.0, min = 0.0, max = 100.0) harrisMinLevel
#@ Boolean (label = "Quit Fiji when done", value = false) quitWhenDone

import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.measure.ResultsTable
import ij.text.TextWindow
import java.awt.Frame
import java.util.Locale

/*
 * OrientationJ - Directional analysis export workflow
 *
 * PURPOSE:
 *   1. Open one grayscale image from disk
 *   2. Run one validated OrientationJ mode through IJ.run(...)
 *   3. Save the image windows, tables, and overlays produced by that mode
 *
 * VALIDATED MODES:
 *   - Analysis
 *   - Distribution
 *   - Vector Field
 *   - Corner Harris
 *   - Dominant Direction
 *
 * IMPORTANT:
 *   - OrientationJ must already be installed in Fiji.
 *   - Use a fresh or empty output directory, or at least a path where the
 *     generated filenames do not already exist.
 *   - Vector Field and Corner Harris place overlays on the active image. This
 *     workflow exports those overlays as flattened TIFF files.
 *   - GUI-backed Fiji is the most reliable path for IJ1 table export. In
 *     headless Fiji, image outputs remain reliable and Dominant Direction uses
 *     a direct CSV fallback.
 *   - Distribution mode in this repo's Groovy pass exported the histogram plot
 *     and distribution table. Separate binary-mask and orientation-mask
 *     windows were not observed through the validated IJ.run(...) path.
 */

Map<String, Integer> GRADIENT_INDEX = [
    "Cubic Spline"    : 0,
    "Finite Difference": 1,
    "Fourier"         : 2,
    "Riesz Filters"   : 3,
    "Gaussian"        : 4
]

Map<String, Integer> VECTOR_TYPE_INDEX = [
    "Maximum"             : 0,
    "Energy"              : 1,
    "Coherency"           : 2,
    "Energy x Coherency"  : 3
]

String slug(String text) {
    return text.replaceAll(/[^A-Za-z0-9._-]+/, "_").replaceAll(/^_+|_+$/, "")
}

String stem(String filename) {
    int dot = filename.lastIndexOf(".")
    return dot > 0 ? filename.substring(0, dot) : filename
}

void ensureTargetDoesNotExist(File file) {
    if (file.exists()) {
        throw new IllegalArgumentException("Output file already exists: " + file.absolutePath)
    }
}

Set<Integer> captureImageIds() {
    def ids = WindowManager.getIDList()
    if (ids == null) {
        return new LinkedHashSet<Integer>()
    }
    return new LinkedHashSet<Integer>(ids as List<Integer>)
}

Set<Frame> captureFrames() {
    return new LinkedHashSet<Frame>(Frame.getFrames() as List<Frame>)
}

List<ImagePlus> findNewOrientationImages(Set<Integer> beforeImageIds) {
    List<ImagePlus> images = []
    def ids = WindowManager.getIDList()
    if (ids == null) {
        return images
    }

    ids.each { id ->
        if (beforeImageIds.contains(id)) {
            return
        }
        def imp = WindowManager.getImage(id)
        if (imp != null && imp.getTitle().startsWith("OJ-")) {
            images << imp
        }
    }
    return images
}

List<TextWindow> findNewOrientationTables(Set<Frame> beforeFrames) {
    List<TextWindow> tables = []
    Frame.getFrames().each { frame ->
        if (beforeFrames.contains(frame)) {
            return
        }
        if (frame instanceof TextWindow) {
            def title = frame.getTitle()
            if (title.startsWith("OJ-") || title.startsWith("Dominant Direction of ")) {
                tables << (TextWindow) frame
            }
        }
    }
    return tables
}

void closeImageIfOpen(ImagePlus imp) {
    if (imp != null) {
        imp.changes = false
        imp.close()
    }
}

void saveImage(ImagePlus imp, File outputFile) {
    ensureTargetDoesNotExist(outputFile)
    IJ.saveAsTiff(imp, outputFile.absolutePath)
    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write TIFF: " + outputFile.absolutePath)
    }
}

void saveTextWindow(TextWindow textWindow, File outputFile) {
    ensureTargetDoesNotExist(outputFile)
    def headings = textWindow.getTextPanel().getColumnHeadings()
    def text = textWindow.getTextPanel().getText()

    outputFile.withWriter("UTF-8") { writer ->
        String headingsCsv = headings == null ? "" : headings.replace('\t', ',')
        if (!headingsCsv.isBlank()) {
            writer.println(headingsCsv)
        }

        List<String> lines = []
        if (text != null && !text.isBlank()) {
            lines = text.readLines()
        }
        if (!lines.isEmpty() && lines[0].replace('\t', ',') == headingsCsv) {
            lines = lines.drop(1)
        }
        lines.each { line ->
            writer.println(line.replace('\t', ','))
        }
    }

    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write CSV: " + outputFile.absolutePath)
    }
}

void saveResultsTableObject(ResultsTable table, File outputFile) {
    ensureTargetDoesNotExist(outputFile)

    String headings = table.getColumnHeadings()
    boolean hasHeadings = headings != null && !headings.isBlank()
    boolean hasRows = table.getCounter() > 0
    if (!hasHeadings && !hasRows) {
        return
    }

    outputFile.withWriter("UTF-8") { writer ->
        if (headings != null && !headings.isBlank()) {
            writer.println(headings.replace('\t', ','))
        }
        for (int row = 0; row < table.getCounter(); row++) {
            writer.println(table.getRowAsString(row).replace('\t', ','))
        }
    }

    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write CSV: " + outputFile.absolutePath)
    }
}

Map<String, ResultsTable> fallbackResultsTables(String mode, String imageTitle) {
    Map<String, ResultsTable> tables = new LinkedHashMap<String, ResultsTable>()
    String preferredTitle = null

    if (mode == "Distribution") {
        preferredTitle = "OJ-Distribution-1"
    }
    else if (mode == "Vector Field") {
        preferredTitle = "OJ-Table-Vector-Field-"
    }
    else if (mode == "Corner Harris") {
        preferredTitle = "OJ-Table-Corners Harris-"
    }
    else if (mode == "Dominant Direction") {
        preferredTitle = "Dominant Direction of " + imageTitle
    }

    if (preferredTitle == null) {
        return tables
    }

    def table = ResultsTable.getResultsTable(preferredTitle)
    if (table == null) {
        table = ResultsTable.getActiveTable()
    }
    if (table == null && mode == "Distribution") {
        table = ResultsTable.getResultsTable()
    }
    if (table != null) {
        tables.put(preferredTitle, table)
    }

    return tables
}

File saveDominantDirectionFallback(ImagePlus imp, File outputDirectory) {
    def outputFile = new File(outputDirectory, slug("Dominant Direction of " + imp.getTitle()) + ".csv")
    ensureTargetDoesNotExist(outputFile)

    def plugin = new OrientationJ_Dominant_Direction()
    int originalSlice = imp.getSlice()

    outputFile.withWriter("UTF-8") { writer ->
        writer.println("Slice,Orientation [Degrees],Coherency [%]")
        for (int slice = 1; slice <= imp.getStackSize(); slice++) {
            imp.setSlice(slice)
            def result = plugin.computeSpline(imp.getProcessor().crop())
            writer.println(String.format(Locale.US, "%d,%.4f,%.5f", slice, result[0], result[1]))
        }
    }

    imp.setSlice(originalSlice)

    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Failed to write dominant-direction CSV: " + outputFile.absolutePath)
    }
    return outputFile
}

if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile.absolutePath)
}
if (outputDir.exists() && !outputDir.isDirectory()) {
    throw new IllegalArgumentException("Output path is not a directory: " + outputDir.absolutePath)
}
if (!outputDir.exists() && !outputDir.mkdirs()) {
    throw new IllegalArgumentException("Could not create output directory: " + outputDir.absolutePath)
}
if (!GRADIENT_INDEX.containsKey(gradientMethod)) {
    throw new IllegalArgumentException("Unsupported gradient: " + gradientMethod)
}
if (!VECTOR_TYPE_INDEX.containsKey(vectorType)) {
    throw new IllegalArgumentException("Unsupported vector type: " + vectorType)
}

def buildAnalysisArgs = {
    "tensor=${tensorSigma} gradient=${GRADIENT_INDEX[gradientMethod]} " +
        "hsb=${surveyColorSpace == 'HSB' ? 'on' : 'off'} " +
        "hue=${surveyHue} sat=${surveySaturation} bri=${surveyBrightness} " +
        "color-survey=on orientation=on coherency=on energy=on " +
        "radian=${useRadians ? 'on' : 'off'} "
}

def buildDistributionArgs = {
    "tensor=${tensorSigma} gradient=${GRADIENT_INDEX[gradientMethod]} " +
        "radian=${useRadians ? 'on' : 'off'} " +
        "histogram=on table=on " +
        "min-coherency=${distributionMinCoherency} min-energy=${distributionMinEnergy} "
}

def buildVectorArgs = {
    "tensor=${tensorSigma} gradient=${GRADIENT_INDEX[gradientMethod]} " +
        "radian=${useRadians ? 'on' : 'off'} " +
        "vectorgrid=${vectorGrid} vectorscale=${vectorScale} " +
        "vectortype=${VECTOR_TYPE_INDEX[vectorType]} " +
        "vectoroverlay=on vectortable=on "
}

def buildHarrisArgs = {
    "tensor=${tensorSigma} gradient=${GRADIENT_INDEX[gradientMethod]} " +
        "harris-index=on harrisk=${harrisK} harrisl=${harrisWindowSize} " +
        "harrismin=${harrisMinLevel} harrisoverlay=on harristable=on "
}

ImagePlus imp = null
List<ImagePlus> newImages = []
List<TextWindow> newTables = []
List<File> savedFiles = []

try {
    imp = IJ.openImage(inputFile.absolutePath)
    if (imp == null) {
        throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
    }
    if (!(imp.getType() in [ImagePlus.GRAY8, ImagePlus.GRAY16, ImagePlus.GRAY32])) {
        throw new IllegalArgumentException("OrientationJ expects an 8-bit, 16-bit, or 32-bit grayscale image.")
    }

    imp.setTitle(stem(inputFile.getName()))
    imp.show()
    WindowManager.setCurrentWindow(imp.getWindow())

    Set<Integer> beforeImageIds = captureImageIds()
    Set<Frame> beforeFrames = captureFrames()

    IJ.log("OrientationJ workflow")
    IJ.log("Mode       : " + mode)
    IJ.log("Input      : " + inputFile.absolutePath)
    IJ.log("Output dir : " + outputDir.absolutePath)

    switch (mode) {
        case "Analysis":
            IJ.run(imp, "OrientationJ Analysis", buildAnalysisArgs())
            break
        case "Distribution":
            IJ.run(imp, "OrientationJ Distribution", buildDistributionArgs())
            break
        case "Vector Field":
            IJ.run(imp, "OrientationJ Vector Field", buildVectorArgs())
            break
        case "Corner Harris":
            IJ.run(imp, "OrientationJ Corner Harris", buildHarrisArgs())
            break
        case "Dominant Direction":
            IJ.run(imp, "OrientationJ Dominant Direction", "")
            break
        default:
            throw new IllegalArgumentException("Unsupported mode: " + mode)
    }

    IJ.wait(800)

    newImages = findNewOrientationImages(beforeImageIds)
    newTables = findNewOrientationTables(beforeFrames)

    Set<String> writtenImageNames = new LinkedHashSet<String>()
    newImages.each { image ->
        def fileName = slug(stem(image.getTitle())) + ".tif"
        if (!writtenImageNames.add(fileName)) {
            return
        }
        def outFile = new File(outputDir, fileName)
        saveImage(image, outFile)
        savedFiles << outFile
    }

    Set<String> writtenTableNames = new LinkedHashSet<String>()
    newTables.each { table ->
        def fileName = slug(stem(table.getTitle())) + ".csv"
        if (!writtenTableNames.add(fileName)) {
            return
        }
        def outFile = new File(outputDir, fileName)
        saveTextWindow(table, outFile)
        savedFiles << outFile
    }

    fallbackResultsTables(mode, imp.getTitle()).each { title, table ->
        def fileName = slug(stem(title)) + ".csv"
        if (!writtenTableNames.add(fileName)) {
            return
        }
        def outFile = new File(outputDir, fileName)
        saveResultsTableObject(table, outFile)
        if (outFile.exists() && outFile.length() > 0) {
            savedFiles << outFile
        }
    }

    if (mode == "Vector Field" || mode == "Corner Harris") {
        if (imp.getOverlay() == null || imp.getOverlay().size() == 0) {
            throw new IllegalStateException(mode + " did not leave an overlay on the active image.")
        }
        def overlayName = stem(inputFile.getName()) + (mode == "Vector Field" ? "_vector_overlay.tif" : "_harris_overlay.tif")
        def overlayFile = new File(outputDir, overlayName)
        def flattened = imp.flatten()
        saveImage(flattened, overlayFile)
        savedFiles << overlayFile
        closeImageIfOpen(flattened)
    }

    if (mode == "Dominant Direction" && savedFiles.isEmpty()) {
        savedFiles << saveDominantDirectionFallback(imp, outputDir)
    }

    if (savedFiles.isEmpty()) {
        throw new IllegalStateException("OrientationJ produced no exported files for mode: " + mode)
    }

    IJ.log("Saved files:")
    savedFiles.each { file ->
        IJ.log("  " + file.absolutePath)
    }
}
finally {
    newImages.each { image ->
        closeImageIfOpen(image)
    }
    newTables.each { table ->
        table.dispose()
    }
    closeImageIfOpen(imp)
}

IJ.log("OrientationJ workflow complete")

if (quitWhenDone) {
    System.exit(0)
}
