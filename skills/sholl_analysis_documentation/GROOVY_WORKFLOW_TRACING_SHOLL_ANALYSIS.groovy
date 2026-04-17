// Load a tracing file, sample a Sholl profile around the root, and export the profile plus summary metrics.
#@ File(label = "Input tracing file") inputTracingFile
#@ Double(label = "Sholl step size (0 = auto)", value = 0) stepSize
#@ File(label = "Output profile CSV", style = "save", value = "/data/sholl_validation/tracing_sholl_profile.csv") profileCsvFile
#@ File(label = "Output Sholl stats CSV", style = "save", value = "/data/sholl_validation/tracing_sholl_stats.csv") statsCsvFile

import sc.fiji.snt.Tree
import sc.fiji.snt.analysis.ShollAnalyzer
import sc.fiji.snt.analysis.TreeStatistics
import sc.fiji.snt.analysis.sholl.math.LinearProfileStats
import sc.fiji.snt.analysis.sholl.math.NormalizedProfileStats
import sc.fiji.snt.analysis.sholl.math.ShollStats
import sc.fiji.snt.analysis.sholl.parsers.TreeParser

void requireReadableTracing(File file) {
    if (file == null || !file.exists() || !file.isFile()) {
        throw new IllegalArgumentException("Input tracing file not found: " + file)
    }
}

void requireFreshOutput(File file, String label) {
    if (file == null) {
        throw new IllegalArgumentException(label + " must be provided")
    }
    file.parentFile?.mkdirs()
    if (file.exists()) {
        throw new IllegalArgumentException(label + " already exists: " + file.absolutePath)
    }
}

String csvEscape(Object value) {
    return (value == null ? "" : value.toString()).replace("\"", "\"\"")
}

String csvCell(Object value) {
    return "\"" + csvEscape(value) + "\""
}

void writeProfileCsv(File file, def profile) {
    double[] radii = profile.radiiAsArray()
    double[] counts = profile.countsAsArray()
    file.withWriter("UTF-8") { writer ->
        writer.println("radius,count")
        for (int i = 0; i < radii.length; i++) {
            writer.println(radii[i] + "," + counts[i])
        }
    }
}

void writeStatsCsv(File file, Tree tree, def profile, Map summaryMetrics, def lStats, int bestDegree, double bestRSq, double ksPValue, def nStats) {
    file.withWriter("UTF-8") { writer ->
        writer.println("metric,sampled,fitted")
        writer.println(csvCell("tree_label") + "," + csvCell(tree.getLabel()) + ",")
        writer.println(csvCell("profile_dimensions") + "," + profile.nDimensions() + ",")
        writer.println(csvCell("profile_size") + "," + profile.size() + ",")
        writer.println(csvCell("start_radius") + "," + profile.startRadius() + ",")
        writer.println(csvCell("step_size") + "," + profile.stepSize() + ",")
        writer.println(csvCell("end_radius") + "," + profile.endRadius() + ",")

        summaryMetrics.each { key, value ->
            writer.println(csvCell("single_value/" + key) + "," + csvCell(value) + ",")
        }

        writer.println(csvCell("min") + "," + lStats.getMin(false) + "," + lStats.getMin(true))
        writer.println(csvCell("max") + "," + lStats.getMax(false) + "," + lStats.getMax(true))
        writer.println(csvCell("mean") + "," + lStats.getMean(false) + "," + lStats.getMean(true))
        writer.println(csvCell("median") + "," + lStats.getMedian(false) + "," + lStats.getMedian(true))
        writer.println(csvCell("sum") + "," + lStats.getSum(false) + "," + lStats.getSum(true))
        writer.println(csvCell("variance") + "," + lStats.getVariance(false) + "," + lStats.getVariance(true))
        writer.println(csvCell("kurtosis") + "," + lStats.getKurtosis(false) + "," + lStats.getKurtosis(true))
        writer.println(csvCell("skewness") + "," + lStats.getSkewness(false) + "," + lStats.getSkewness(true))
        writer.println(csvCell("ramification_index") + "," + lStats.getRamificationIndex(false) + "," + lStats.getRamificationIndex(true))
        writer.println(csvCell("enclosing_radius") + "," + lStats.getEnclosingRadius(false, 1) + "," + lStats.getEnclosingRadius(true, 1))
        writer.println(csvCell("primary_branches") + "," + lStats.getPrimaryBranches(false) + "," + lStats.getPrimaryBranches(true))
        writer.println(csvCell("intersecting_radii") + "," + lStats.getIntersectingRadii(false) + "," + lStats.getIntersectingRadii(true))

        writer.println(csvCell("best_fit_degree") + "," + bestDegree + ",")
        writer.println(csvCell("r_squared_adjusted") + "," + bestRSq + ",")
        writer.println(csvCell("ks_test_p_value") + "," + ksPValue + ",")

        writer.println(csvCell("normalization_method") + "," + csvCell(nStats.getMethodDescription()) + ",")
        writer.println(csvCell("sholl_decay") + "," + nStats.getShollDecay() + ",")
        writer.println(csvCell("determination_ratio") + "," + nStats.getDeterminationRatio() + ",")
    }
}

requireReadableTracing(inputTracingFile)
requireFreshOutput(profileCsvFile, "Profile CSV")
requireFreshOutput(statsCsvFile, "Sholl stats CSV")

println("Sholl tracing analysis")
println("Input tracing    : " + inputTracingFile.absolutePath)
println("Step size        : " + (stepSize > 0 ? stepSize : "auto"))
println("Profile CSV      : " + profileCsvFile.absolutePath)
println("Stats CSV        : " + statsCsvFile.absolutePath)

def tree = Tree.fromFile(inputTracingFile.absolutePath)
if (tree == null || tree.isEmpty()) {
    throw new IllegalStateException("Could not load a tracing tree from: " + inputTracingFile.absolutePath)
}
if (tree.getRoot() == null) {
    throw new IllegalStateException("Tracing tree has no root node: " + inputTracingFile.absolutePath)
}

def parser = new TreeParser(tree)
parser.setCenter(tree.getRoot())
if (stepSize > 0) {
    parser.setStepSize(stepSize)
}
parser.parse()

if (!parser.successful()) {
    throw new IllegalStateException("TreeParser failed for: " + inputTracingFile.absolutePath)
}

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
if (profile == null || profile.isEmpty()) {
    throw new IllegalStateException("Tracing-based Sholl profile is empty: " + inputTracingFile.absolutePath)
}

def treeStats = new TreeStatistics(tree)
treeStats.summarize(false)

def sholl = new ShollAnalyzer(tree, treeStats)
sholl.setEnableCurveFitting(true)
sholl.setPolynomialFitRange(2, 30)
Map singleValueMetrics = sholl.getSingleValueMetrics()
if (singleValueMetrics == null || singleValueMetrics.isEmpty()) {
    throw new IllegalStateException("ShollAnalyzer returned no summary metrics for: " + inputTracingFile.absolutePath)
}

def lStats = new LinearProfileStats(profile)
int bestDegree = lStats.findBestFit(2, 30, 0.70, 0.05)
double bestRSq = lStats.getRSquaredOfFit(true)
double ksPValue = lStats.getKStestOfFit()
def nStats = new NormalizedProfileStats(profile, ShollStats.AREA)

writeProfileCsv(profileCsvFile, profile)
writeStatsCsv(statsCsvFile, tree, profile, singleValueMetrics, lStats, bestDegree, bestRSq, ksPValue, nStats)

if (!profileCsvFile.exists() || profileCsvFile.length() == 0) {
    throw new IllegalStateException("Could not save profile CSV: " + profileCsvFile.absolutePath)
}
if (!statsCsvFile.exists() || statsCsvFile.length() == 0) {
    throw new IllegalStateException("Could not save Sholl stats CSV: " + statsCsvFile.absolutePath)
}

println("Tree nodes       : " + tree.getNodesCount())
println("Profile samples  : " + profile.size())
println("Best fit degree  : " + bestDegree)
println("Adjusted R^2     : " + bestRSq)
println("Sholl decay      : " + nStats.getShollDecay())
println("Sholl tracing analysis complete")
