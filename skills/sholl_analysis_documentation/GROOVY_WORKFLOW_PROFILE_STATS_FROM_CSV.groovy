// Load a sampled Sholl profile from CSV or TXT and export fitted plus normalized summary statistics.
#@ File(label = "Input sampled profile CSV/TXT") inputProfileFile
#@ String(label = "Radius column header", value = "radius") radiusColumn
#@ String(label = "Count column header", value = "count") countColumn
#@ File(label = "Output Sholl stats CSV", style = "save", value = "/data/sholl_validation/profile_sholl_stats.csv") statsCsvFile

import sc.fiji.snt.analysis.sholl.math.LinearProfileStats
import sc.fiji.snt.analysis.sholl.math.NormalizedProfileStats
import sc.fiji.snt.analysis.sholl.math.ShollStats
import sc.fiji.snt.analysis.sholl.parsers.TabularParser

void requireReadableProfile(File file) {
    if (file == null || !file.exists() || !file.isFile()) {
        throw new IllegalArgumentException("Input profile file not found: " + file)
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

void writeStatsCsv(File file, File inputFile, String radiusColumn, String countColumn, def profile, def lStats, int bestDegree, double bestRSq, double ksPValue, def nStats) {
    def profileDimensions = profile.nDimensions() > 0 ? profile.nDimensions() : "unknown"
    file.withWriter("UTF-8") { writer ->
        writer.println("metric,sampled,fitted")
        writer.println(csvCell("input_profile_file") + "," + csvCell(inputFile.absolutePath) + ",")
        writer.println(csvCell("radius_column") + "," + csvCell(radiusColumn) + ",")
        writer.println(csvCell("count_column") + "," + csvCell(countColumn) + ",")
        writer.println(csvCell("profile_dimensions") + "," + csvCell(profileDimensions) + ",")
        writer.println(csvCell("profile_size") + "," + profile.size() + ",")
        writer.println(csvCell("start_radius") + "," + profile.startRadius() + ",")
        writer.println(csvCell("step_size") + "," + profile.stepSize() + ",")
        writer.println(csvCell("end_radius") + "," + profile.endRadius() + ",")

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

requireReadableProfile(inputProfileFile)
requireFreshOutput(statsCsvFile, "Sholl stats CSV")

println("Sholl profile statistics from table")
println("Input profile    : " + inputProfileFile.absolutePath)
println("Radius column    : " + radiusColumn)
println("Count column     : " + countColumn)
println("Stats CSV        : " + statsCsvFile.absolutePath)

def parser = new TabularParser(inputProfileFile, radiusColumn, countColumn)
parser.parse()
if (!parser.successful()) {
    throw new IllegalStateException("TabularParser failed for: " + inputProfileFile.absolutePath)
}

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
if (profile == null || profile.isEmpty()) {
    throw new IllegalStateException("Profile table contains no usable Sholl samples: " + inputProfileFile.absolutePath)
}

def lStats = new LinearProfileStats(profile)
int bestDegree = lStats.findBestFit(2, 30, 0.70, 0.05)
double bestRSq = lStats.getRSquaredOfFit(true)
double ksPValue = lStats.getKStestOfFit()
def nStats = new NormalizedProfileStats(profile, ShollStats.AREA)

writeStatsCsv(statsCsvFile, inputProfileFile, radiusColumn, countColumn, profile, lStats, bestDegree, bestRSq, ksPValue, nStats)

if (!statsCsvFile.exists() || statsCsvFile.length() == 0) {
    throw new IllegalStateException("Could not save Sholl stats CSV: " + statsCsvFile.absolutePath)
}

println("Profile samples  : " + profile.size())
println("Best fit degree  : " + bestDegree)
println("Adjusted R^2     : " + bestRSq)
println("Sholl decay      : " + nStats.getShollDecay())
println("Sholl profile statistics complete")
