# Sholl Analysis Groovy / Script API

## Container-Validated Calls

### 1. Direct image parsing

Use `ImageParser2D` or `ImageParser3D` for segmented or thresholdable images.

```groovy
import ij.IJ
import sc.fiji.snt.analysis.sholl.parsers.ImageParser2D
import sc.fiji.snt.analysis.sholl.parsers.ImageParser3D

def parser = imp.getNSlices() > 1 ? new ImageParser3D(imp) : new ImageParser2D(imp)
if (!(imp.isThreshold() || imp.getProcessor().isBinary()))
    IJ.setAutoThreshold(imp, "Otsu dark")

if (imp.getNSlices() > 1) {
    parser.setCenterPx(x, y, z)
    parser.setPosition(channel, frame)
    parser.setSkipSingleVoxels(true)
} else {
    parser.setCenterPx(x, y)
    parser.setPosition(channel, slice, frame)
}

parser.setRadii(startRadius, stepSize, endRadius)
parser.setHemiShells("none")
parser.parse()

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
```

Use `GROOVY_WORKFLOW_IMAGE_SHOLL_ANALYSIS.groovy` for a complete file-based workflow.

### 2. Tracing-based Sholl analysis

Use `Tree.fromFile` plus `TreeParser` for sampled profiles and `ShollAnalyzer` for single-value summary metrics.

```groovy
import sc.fiji.snt.Tree
import sc.fiji.snt.analysis.ShollAnalyzer
import sc.fiji.snt.analysis.TreeStatistics
import sc.fiji.snt.analysis.sholl.parsers.TreeParser

def tree = Tree.fromFile(inputTracingFile.absolutePath)
def parser = new TreeParser(tree)
parser.setCenter(tree.getRoot())
if (stepSize > 0)
    parser.setStepSize(stepSize)
parser.parse()

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()

def stats = new TreeStatistics(tree)
stats.summarize(false)

def sholl = new ShollAnalyzer(tree, stats)
sholl.setEnableCurveFitting(true)
sholl.setPolynomialFitRange(2, 30)
Map singleValueMetrics = sholl.getSingleValueMetrics()
```

Use `GROOVY_WORKFLOW_TRACING_SHOLL_ANALYSIS.groovy` for the validated export path.

### 3. Existing sampled profiles

Use `TabularParser` to load a sampled profile from a CSV or TXT table with one radius column and one count column.

```groovy
import sc.fiji.snt.analysis.sholl.parsers.TabularParser

def parser = new TabularParser(inputProfileFile, radiusColumn, countColumn)
parser.parse()

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
```

Use `GROOVY_WORKFLOW_PROFILE_STATS_FROM_CSV.groovy` to export fitted and normalized statistics from a saved profile table.

When launching this workflow with `fiji-linux-x64 --run`, quote string-valued parameters inside the argument block:

```text
/opt/Fiji.app/fiji-linux-x64 --headless --run /app/skills/sholl_analysis_documentation/GROOVY_WORKFLOW_PROFILE_STATS_FROM_CSV.groovy "inputProfileFile=\"/tmp/profile.csv\",radiusColumn=\"radius\",countColumn=\"count\",statsCsvFile=\"/tmp/profile_stats.csv\""
```

### 4. Curve fitting and normalized decay

Use `LinearProfileStats` and `NormalizedProfileStats` after obtaining a `Profile`.

```groovy
import sc.fiji.snt.analysis.sholl.math.LinearProfileStats
import sc.fiji.snt.analysis.sholl.math.NormalizedProfileStats
import sc.fiji.snt.analysis.sholl.math.ShollStats

def lStats = new LinearProfileStats(profile)
int bestDegree = lStats.findBestFit(2, 30, 0.70, 0.05)
double bestRSq = lStats.getRSquaredOfFit(true)
double ksPValue = lStats.getKStestOfFit()

def nStats = new NormalizedProfileStats(profile, ShollStats.AREA)
String methodDescription = nStats.getMethodDescription()
double shollDecay = nStats.getShollDecay()
double determinationRatio = nStats.getDeterminationRatio()
```

Useful `LinearProfileStats` getters:

- `getMin(sampledOrFitted)`
- `getMax(sampledOrFitted)`
- `getMean(sampledOrFitted)`
- `getMedian(sampledOrFitted)`
- `getSum(sampledOrFitted)`
- `getVariance(sampledOrFitted)`
- `getKurtosis(sampledOrFitted)`
- `getSkewness(sampledOrFitted)`
- `getRamificationIndex(sampledOrFitted)`
- `getEnclosingRadius(sampledOrFitted, 1)`
- `getPrimaryBranches(sampledOrFitted)`
- `getIntersectingRadii(sampledOrFitted)`

## Official-Doc Entry Points

- Direct image analysis is launched from `Analysis > Sholl > Sholl Analysis...`.
- Tracing analysis is launched from `Plugins > Neuroanatomy > Neuroanatomy Shortcut Window`, then `Sholl Analysis (Tracings)...`.
- The official documentation states that Sholl dialogs are macro-recordable. Use the Macro Recorder to capture a project-specific `run("Sholl Analysis ...", "...")` string.
- The official documentation also lists `Combine Sholl Profiles...` as a GUI tool for group averages and profile aggregation.

## Excluded / Unverified

- No checked-in workflow in this skill drives the full Sholl dialogs by replaying one large recorded macro string.
- `Combine Sholl Profiles...` is not wrapped in a headless workflow here.
- Plot display calls, ROI overlay visualization, and other display-bound outputs are not part of the checked-in automation path.
- Official tracing-file support includes multiple formats, but the validated file artifact in this repo is an SWC reconstruction.
