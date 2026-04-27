#@ File (label = "Input NeuronJ data file", value = "/data/neuronj_validation/neurites.ndf") inputNdfFile
#@ File (label = "Output directory", style = "directory", value = "/data/neuronj_validation/ndf_export") outputDir
#@ String (label = "Vertex CSV filename", value = "neurites_vertices.csv") vertexCsvName
#@ String (label = "Tracing summary CSV filename", value = "neurites_tracing_summary.csv") summaryCsvName
#@ Double (label = "Pixel width", value = 1.0, min = 0.000001) pixelWidth
#@ Double (label = "Pixel height", value = 1.0, min = 0.000001) pixelHeight
#@ String (label = "Length unit", value = "pixel") lengthUnit
#@ Boolean (label = "Use legacy calibration from NDF 1.0 files when present", value = true) useLegacyCalibration
#@ Boolean (label = "Export one segmented-line ROI per tracing", value = true) exportRois
#@ Boolean (label = "Overwrite existing outputs", value = false) overwriteOutputs
#@ Boolean (label = "Quit Fiji when done", value = false) quitWhenDone

import ij.IJ
import ij.gui.PolygonRoi
import ij.gui.Roi
import ij.io.RoiEncoder
import java.util.Locale

/*
 * NeuronJ - Export saved NDF tracings to CSV tables and optional ROI files.
 *
 * PURPOSE:
 *   1. Read an existing NeuronJ data file (.ndf)
 *   2. Export all tracing vertices to CSV
 *   3. Export one tracing-level length summary CSV
 *   4. Optionally write one ImageJ polyline ROI per tracing
 *
 * REQUIRED INPUTS:
 *   inputNdfFile - a saved NeuronJ data file
 *   outputDir    - directory for the exported tables and ROI files
 *
 * IMPORTANT:
 *   - This workflow post-processes tracings already saved by NeuronJ. It does
 *     not run NeuronJ's interactive path-search algorithm.
 *   - NeuronJ 1.1.0 and later do not store image calibration in the NDF file.
 *     Set Pixel width, Pixel height, and Length unit to match the original
 *     image calibration before using the length columns for measurement.
 *   - Existing output files are not overwritten unless Overwrite existing
 *     outputs is enabled.
 */

class NjSegment {
    int index
    List<int[]> points = []
}

class NjTracing {
    int id
    int typeIndex
    int clusterIndex
    String label
    List<NjSegment> segments = []
}

class NjNdf {
    String version
    Map<String, Object> parameters = [:]
    List<String> typeNames = []
    List<Integer> typeColorIndices = []
    List<String> clusterNames = []
    List<NjTracing> tracings = []
    Double legacyPixelWidth = null
    Double legacyPixelHeight = null
    String legacyUnit = null
}

List<Integer> versionParts(String text) {
    return text.tokenize(".").collect { it as int }
}

boolean versionAtLeast(String version, String minimum) {
    List<Integer> v = versionParts(version)
    List<Integer> m = versionParts(minimum)
    int size = Math.max(v.size(), m.size())
    for (int i = 0; i < size; i++) {
        int vi = i < v.size() ? v[i] : 0
        int mi = i < m.size() ? m[i] : 0
        if (vi != mi) return vi > mi
    }
    return true
}

void requireReadableFile(File file, String label) {
    if (file == null) throw new IllegalArgumentException("${label} must be provided")
    if (!file.exists()) throw new IllegalArgumentException("${label} does not exist: ${file.absolutePath}")
    if (!file.isFile()) throw new IllegalArgumentException("${label} is not a file: ${file.absolutePath}")
    if (!file.canRead()) throw new IllegalArgumentException("${label} is not readable: ${file.absolutePath}")
}

void requireSimpleFilename(String name, String label) {
    if (name == null || name.trim().isEmpty()) {
        throw new IllegalArgumentException("${label} must be provided")
    }
    if (name.contains("/") || name.contains("\\") || name == "." || name == "..") {
        throw new IllegalArgumentException("${label} must be a filename, not a path: ${name}")
    }
}

void prepareOutputFile(File file, boolean overwrite) {
    file.parentFile?.mkdirs()
    if (file.exists()) {
        if (!overwrite) {
            throw new IllegalArgumentException("Output file already exists: ${file.absolutePath}")
        }
        if (!file.delete()) {
            throw new IllegalArgumentException("Could not overwrite existing output file: ${file.absolutePath}")
        }
    }
}

String csvCell(Object value) {
    String text = value == null ? "" : String.valueOf(value)
    boolean quote = text.contains(",") || text.contains("\"") || text.contains("\n") || text.contains("\r")
    text = text.replace("\"", "\"\"")
    return quote ? "\"${text}\"" : text
}

String csvRow(List values) {
    return values.collect { csvCell(it) }.join(",")
}

String fmt(double value) {
    return String.format(Locale.US, "%.9f", value)
}

double segmentLength(List<int[]> points, double pw, double ph) {
    double length = 0.0d
    for (int i = 1; i < points.size(); i++) {
        double dx = (points[i][0] - points[i - 1][0]) * pw
        double dy = (points[i][1] - points[i - 1][1]) * ph
        length += Math.sqrt(dx * dx + dy * dy)
    }
    return length
}

double tracingLength(NjTracing tracing, double pw, double ph) {
    double length = 0.0d
    tracing.segments.each { segment ->
        length += segmentLength(segment.points, pw, ph)
    }
    return length
}

String indexedName(List<String> names, int index, String fallbackPrefix) {
    return (index >= 0 && index < names.size()) ? names[index] : "${fallbackPrefix} ${index}"
}

NjNdf readNdf(File file) {
    List<String> lines = file.readLines("UTF-8")
    int cursor = 0

    def readLine = { String label ->
        if (cursor >= lines.size()) {
            throw new IllegalArgumentException("Unexpected end of NDF file while reading ${label}")
        }
        return lines[cursor++]
    }
    def readMaybe = {
        return cursor < lines.size() ? lines[cursor++] : null
    }
    def readInt = { String label ->
        String line = readLine(label).trim()
        try {
            return Integer.parseInt(line)
        }
        catch (Exception ignored) {
            throw new IllegalArgumentException("Expected integer for ${label}, found '${line}'")
        }
    }
    def readDouble = { String label ->
        String line = readLine(label).trim()
        try {
            return Double.parseDouble(line)
        }
        catch (Exception ignored) {
            throw new IllegalArgumentException("Expected number for ${label}, found '${line}'")
        }
    }

    NjNdf ndf = new NjNdf()
    String header = readLine("NDF header")
    if (!header.startsWith("// NeuronJ Data File")) {
        throw new IllegalArgumentException("Input file is not a NeuronJ data file: ${file.absolutePath}")
    }

    ndf.version = readLine("NDF version").trim()
    String parameterHeader = readLine("parameters header")
    if (!parameterHeader.startsWith("// Parameters")) {
        throw new IllegalArgumentException("Missing parameters block in NDF file")
    }

    if (versionAtLeast(ndf.version, "1.4.0")) {
        ndf.parameters.appearance = readInt("neurite appearance")
    }
    else {
        ndf.parameters.appearance = 0
    }
    ndf.parameters.hessianSmoothingScale = readDouble("Hessian smoothing scale")
    ndf.parameters.costWeightFactor = readDouble("cost weight factor")
    ndf.parameters.snapWindowSize = readInt("snap window size")
    ndf.parameters.pathSearchWindowSize = readInt("path-search window size")
    ndf.parameters.tracingSmoothingRange = readInt("tracing smoothing range")
    ndf.parameters.tracingSubsamplingFactor = readInt("tracing subsampling factor")

    if (versionAtLeast(ndf.version, "1.1.0")) {
        ndf.parameters.lineWidth = readInt("line width")
    }
    else {
        ndf.parameters.lineWidth = null
        ndf.legacyPixelWidth = readDouble("legacy pixel width")
        ndf.legacyPixelHeight = readDouble("legacy pixel height")
        ndf.legacyUnit = readLine("legacy unit").trim()
        readLine("legacy auto-save option")
        readLine("legacy log option")
    }

    String typeHeader = readLine("type names header")
    if (!typeHeader.startsWith("// Type names and colors")) {
        throw new IllegalArgumentException("Missing type names block in NDF file")
    }
    for (int i = 0; i <= 10; i++) {
        ndf.typeNames << readLine("type ${i} name")
        ndf.typeColorIndices << readInt("type ${i} color")
    }

    String clusterHeader = readLine("cluster names header")
    if (!clusterHeader.startsWith("// Cluster names")) {
        throw new IllegalArgumentException("Missing cluster names block in NDF file")
    }
    for (int i = 0; i <= 10; i++) {
        ndf.clusterNames << readLine("cluster ${i} name")
    }

    String line = readMaybe()
    while (line != null && line.startsWith("// Tracing")) {
        NjTracing tracing = new NjTracing()
        tracing.id = readInt("tracing id")
        tracing.typeIndex = readInt("tracing type")
        tracing.clusterIndex = readInt("tracing cluster")
        tracing.label = readLine("tracing label")

        line = readMaybe()
        int segmentIndex = 1
        while (line != null && line.startsWith("// Segment")) {
            NjSegment segment = new NjSegment(index: segmentIndex++)
            line = readMaybe()
            while (line != null && !line.startsWith("//")) {
                int x
                int y
                try {
                    x = Integer.parseInt(line.trim())
                }
                catch (NumberFormatException ignored) {
                    throw new IllegalArgumentException("Invalid x coordinate in tracing N${tracing.id}: '${line}'")
                }
                String yLine = readLine("vertex y coordinate")
                try {
                    y = Integer.parseInt(yLine.trim())
                }
                catch (NumberFormatException ignored) {
                    throw new IllegalArgumentException("Invalid y coordinate in tracing N${tracing.id}: '${yLine}'")
                }
                segment.points << ([x, y] as int[])
                line = readMaybe()
            }
            if (!segment.points.isEmpty()) {
                tracing.segments << segment
            }
        }

        if (!tracing.segments.isEmpty()) {
            ndf.tracings << tracing
        }
    }

    return ndf
}

boolean writeRoiForTracing(NjTracing tracing, File roiFile, boolean overwrite) {
    List<int[]> polylinePoints = []
    tracing.segments.eachWithIndex { segment, segmentOffset ->
        int start = segmentOffset == 0 ? 0 : 1
        for (int i = start; i < segment.points.size(); i++) {
            polylinePoints << segment.points[i]
        }
    }
    if (polylinePoints.size() < 2) {
        IJ.log("Skipping ROI for tracing N${tracing.id}: fewer than two vertices")
        return false
    }
    prepareOutputFile(roiFile, overwrite)
    int[] xs = new int[polylinePoints.size()]
    int[] ys = new int[polylinePoints.size()]
    for (int i = 0; i < polylinePoints.size(); i++) {
        xs[i] = polylinePoints[i][0]
        ys[i] = polylinePoints[i][1]
    }
    PolygonRoi roi = new PolygonRoi(xs, ys, polylinePoints.size(), Roi.POLYLINE)
    roi.setName("N${tracing.id}")
    new RoiEncoder(roiFile.absolutePath).write(roi)
    if (!roiFile.exists() || roiFile.length() == 0) {
        throw new IllegalStateException("Failed to write ROI file: ${roiFile.absolutePath}")
    }
    return true
}

requireReadableFile(inputNdfFile, "Input NDF file")
requireSimpleFilename(vertexCsvName, "Vertex CSV filename")
requireSimpleFilename(summaryCsvName, "Tracing summary CSV filename")
if (pixelWidth <= 0.0d || pixelHeight <= 0.0d) {
    throw new IllegalArgumentException("Pixel width and height must be positive")
}

outputDir.mkdirs()
if (!outputDir.isDirectory()) {
    throw new IllegalArgumentException("Output directory could not be created: ${outputDir.absolutePath}")
}

File vertexCsvFile = new File(outputDir, vertexCsvName)
File summaryCsvFile = new File(outputDir, summaryCsvName)
prepareOutputFile(vertexCsvFile, overwriteOutputs)
prepareOutputFile(summaryCsvFile, overwriteOutputs)

NjNdf ndf = readNdf(inputNdfFile)
if (ndf.tracings.isEmpty()) {
    throw new IllegalStateException("The NDF file contains no non-empty tracings: ${inputNdfFile.absolutePath}")
}

double effectivePixelWidth = pixelWidth
double effectivePixelHeight = pixelHeight
String effectiveUnit = lengthUnit == null || lengthUnit.trim().isEmpty() ? "pixel" : lengthUnit.trim()
if (useLegacyCalibration && ndf.legacyPixelWidth != null && ndf.legacyPixelHeight != null) {
    effectivePixelWidth = ndf.legacyPixelWidth
    effectivePixelHeight = ndf.legacyPixelHeight
    if (ndf.legacyUnit != null && !ndf.legacyUnit.trim().isEmpty()) {
        effectiveUnit = ndf.legacyUnit.trim()
    }
}

vertexCsvFile.withWriter("UTF-8") { writer ->
    writer.println(csvRow([
        "ndf_version", "tracing_id", "type_index", "type_name", "cluster_index",
        "cluster_name", "label", "segment_index", "vertex_index", "x_px", "y_px",
        "x_calibrated", "y_calibrated", "cumulative_length", "length_unit"
    ]))
    ndf.tracings.each { tracing ->
        String typeName = indexedName(ndf.typeNames, tracing.typeIndex, "Type")
        String clusterName = indexedName(ndf.clusterNames, tracing.clusterIndex, "Cluster")
        double cumulative = 0.0d
        tracing.segments.each { segment ->
            int vertexIndex = 1
            int[] previous = null
            segment.points.each { point ->
                if (previous != null) {
                    double dx = (point[0] - previous[0]) * effectivePixelWidth
                    double dy = (point[1] - previous[1]) * effectivePixelHeight
                    cumulative += Math.sqrt(dx * dx + dy * dy)
                }
                writer.println(csvRow([
                    ndf.version,
                    "N${tracing.id}",
                    tracing.typeIndex,
                    typeName,
                    tracing.clusterIndex,
                    clusterName,
                    tracing.label,
                    segment.index,
                    vertexIndex++,
                    point[0],
                    point[1],
                    fmt(point[0] * effectivePixelWidth),
                    fmt(point[1] * effectivePixelHeight),
                    fmt(cumulative),
                    effectiveUnit
                ]))
                previous = point
            }
        }
    }
}

summaryCsvFile.withWriter("UTF-8") { writer ->
    writer.println(csvRow([
        "ndf_version", "tracing_id", "type_index", "type_name", "cluster_index",
        "cluster_name", "label", "segment_count", "vertex_count", "length_px",
        "length_calibrated", "length_unit"
    ]))
    ndf.tracings.each { tracing ->
        String typeName = indexedName(ndf.typeNames, tracing.typeIndex, "Type")
        String clusterName = indexedName(ndf.clusterNames, tracing.clusterIndex, "Cluster")
        int vertexCount = tracing.segments.collect { it.points.size() }.sum() as int
        writer.println(csvRow([
            ndf.version,
            "N${tracing.id}",
            tracing.typeIndex,
            typeName,
            tracing.clusterIndex,
            clusterName,
            tracing.label,
            tracing.segments.size(),
            vertexCount,
            fmt(tracingLength(tracing, 1.0d, 1.0d)),
            fmt(tracingLength(tracing, effectivePixelWidth, effectivePixelHeight)),
            effectiveUnit
        ]))
    }
}

int roiCount = 0
if (exportRois) {
    File roiDir = new File(outputDir, "rois")
    roiDir.mkdirs()
    if (!roiDir.isDirectory()) {
        throw new IllegalArgumentException("ROI directory could not be created: ${roiDir.absolutePath}")
    }
    ndf.tracings.each { tracing ->
        File roiFile = new File(roiDir, "N${tracing.id}.roi")
        if (writeRoiForTracing(tracing, roiFile, overwriteOutputs)) {
            roiCount++
        }
    }
}

IJ.log("NeuronJ NDF export complete")
IJ.log("Input NDF       : ${inputNdfFile.absolutePath}")
IJ.log("Tracings        : ${ndf.tracings.size()}")
IJ.log("Vertex CSV      : ${vertexCsvFile.absolutePath}")
IJ.log("Summary CSV     : ${summaryCsvFile.absolutePath}")
IJ.log("ROI files       : ${roiCount}")
IJ.log("Length unit     : ${effectiveUnit}")

if (quitWhenDone) {
    System.exit(0)
}
