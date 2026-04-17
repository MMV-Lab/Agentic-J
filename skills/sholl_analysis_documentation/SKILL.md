---
name: sholl_analysis_documentation
description: Sholl Analysis in this Fiji environment is provided through SNT and supports radial analysis of segmented images, traced morphologies, and pre-sampled Sholl profiles. Use this skill for image-based Sholl profiles from binary 2D or 3D images, tracing-based Sholl measurements from SWC reconstructions, and polynomial fit or decay statistics from CSV profile tables.
---

# Sholl Analysis - Documentation Index

Sholl Analysis is distributed through SNT in this Fiji runtime. All scripting uses the SNT Sholl Java API directly (`ImageParser2D`, `ImageParser3D`, `TreeParser`, `TabularParser`, `LinearProfileStats`, `NormalizedProfileStats`, `ShollAnalyzer`) — not `IJ.run()` or dialog-driving macros.

---

## Scripting in Groovy — The Three Entry Points

Every Sholl run has the same shape: pick a **parser** that matches your input, produce a **`Profile`**, then report statistics through **`LinearProfileStats`** (polynomial fit + descriptive metrics) and **`NormalizedProfileStats`** (semi-log / log-log decay).

### 1. Segmented image → profile

```groovy
import ij.IJ
import sc.fiji.snt.analysis.sholl.parsers.ImageParser2D
import sc.fiji.snt.analysis.sholl.parsers.ImageParser3D

def imp = IJ.getImage()
def parser = imp.getNSlices() > 1 ? new ImageParser3D(imp) : new ImageParser2D(imp)

if (!(imp.isThreshold() || imp.getProcessor().isBinary()))
    IJ.setAutoThreshold(imp, "Otsu dark")

if (imp.getNSlices() > 1) {
    parser.setCenterPx(x, y, z)
    parser.setPosition(channel, frame)          // 3D: 2 args
    parser.setSkipSingleVoxels(true)
} else {
    parser.setCenterPx(x, y)
    parser.setPosition(channel, slice, frame)   // 2D: 3 args
}

parser.setRadii(startRadius, stepSize, endRadius)
parser.setHemiShells("none")
parser.parse()
assert parser.successful()

def profile = parser.getProfile()
profile.trimNaNCounts()
profile.trimZeroCounts()
```

### 2. Tracing (SWC / traces) → profile + single-value metrics

```groovy
import sc.fiji.snt.Tree
import sc.fiji.snt.analysis.ShollAnalyzer
import sc.fiji.snt.analysis.TreeStatistics
import sc.fiji.snt.analysis.sholl.parsers.TreeParser

def tree = Tree.fromFile("/path/to/reconstruction.swc")
def parser = new TreeParser(tree)
parser.setCenter(tree.getRoot())
parser.setStepSize(stepSize)           // 0 = auto / continuous
parser.parse()
def profile = parser.getProfile()
profile.trimNaNCounts(); profile.trimZeroCounts()

def sholl = new ShollAnalyzer(tree, new TreeStatistics(tree))
sholl.setEnableCurveFitting(true)
sholl.setPolynomialFitRange(2, 30)
Map singleValueMetrics = sholl.getSingleValueMetrics()
```

### 3. Pre-sampled profile (CSV / TXT) → statistics only

```groovy
import sc.fiji.snt.analysis.sholl.parsers.TabularParser

def parser = new TabularParser(new File("/path/to/profile.csv"),
                               "radius", "count")
parser.parse()
def profile = parser.getProfile()
```

### Fit and decay — always last

```groovy
import sc.fiji.snt.analysis.sholl.math.LinearProfileStats
import sc.fiji.snt.analysis.sholl.math.NormalizedProfileStats
import sc.fiji.snt.analysis.sholl.math.ShollStats

def lStats = new LinearProfileStats(profile)
int bestDegree = lStats.findBestFit(2, 30, 0.70, 0.05)
double rSq     = lStats.getRSquaredOfFit(true)
double ksP     = lStats.getKStestOfFit()

def nStats = new NormalizedProfileStats(profile, ShollStats.AREA)
double decay  = nStats.getShollDecay()
double detRat = nStats.getDeterminationRatio()
```

---

## Parameters at a Glance

### Shell sampling

| Parameter | Groovy type | Typical | Meaning |
|-----------|-------------|---------|---------|
| `startRadius` | `double` | `0` | Inner shell (physical units) |
| `stepSize` | `double` | `5` | Radius step between shells; `0` = continuous (tracing) or per-pixel (image) |
| `endRadius` | `double` | `0` | Outer shell; `<= 0` → `parser.maxPossibleRadius()` (image) |
| `hemiShells` | `String` | `"none"` | Restrict sampling to sub-compartments |
| `skipSingleVoxels` | `boolean` | `true` | 3D only — ignore isolated foreground voxels |

### Center definition

| Source | Call |
|--------|------|
| Pixel coordinates (2D) | `parser.setCenterPx(x, y)` |
| Pixel coordinates (3D) | `parser.setCenterPx(x, y, z)` |
| Tracing root / soma node | `parser.setCenter(tree.getRoot())` |

### `LinearProfileStats.findBestFit(minDeg, maxDeg, minRsq, maxPvalue)`

| Arg | Typical | Meaning |
|-----|---------|---------|
| `minDeg` | `2` | Minimum polynomial degree to try |
| `maxDeg` | `30` | Maximum polynomial degree to try |
| `minRsq` | `0.70` | Adjusted R² floor for an acceptable fit |
| `maxPvalue` | `0.05` | K-S goodness-of-fit p-value ceiling |

Returns the chosen degree. If no degree in the range satisfies both thresholds the call fails to converge — see Pitfall 4.

### Normalization (`NormalizedProfileStats` second argument)

| Constant | Use for |
|----------|---------|
| `ShollStats.AREA` | 2D profiles (the verified choice in every workflow in this skill) |

Other normalization constants (volume, perimeter, surface) exist in the SNT API — consult the JavaDoc before using them and match the constant to the dimensionality of the profile.

### Useful `LinearProfileStats` getters

All accept a `boolean sampledOrFitted` argument (`false` = sampled profile, `true` = fitted polynomial):

`getMin`, `getMax`, `getMean`, `getMedian`, `getSum`, `getVariance`, `getKurtosis`, `getSkewness`, `getRamificationIndex`, `getPrimaryBranches`, `getIntersectingRadii`. `getEnclosingRadius` additionally takes a cutoff count (`getEnclosingRadius(sampledOrFitted, 1)`).

---

## Critical Pitfalls

### Pitfall 1 — Always trim before computing stats
`LinearProfileStats` and `NormalizedProfileStats` on a raw profile will treat NaN shells and leading/trailing zeros as real data. Every workflow in this skill does:
```groovy
profile.trimNaNCounts()
profile.trimZeroCounts()
```
Do the same. Skipping these silently skews the mean, median, and decay.

### Pitfall 2 — Image must be binary or thresholded before `parse()`
`ImageParser2D` / `ImageParser3D` decide foreground from the active threshold. If the image is neither binary nor thresholded, either call `parser.setThreshold(lower, upper)` or `IJ.setAutoThreshold(imp, "Otsu dark")` first — otherwise the parser may count nothing and `successful()` will still return `true`.

### Pitfall 3 — Check `parser.successful()` after `parse()`
`parse()` returns `void`. The only reliable completion signal is `parser.successful()`. Treat `false` as a hard failure (wrong center, empty foreground, step size too large for the radius range, no startup ROI in the GUI case).

### Pitfall 4 — `findBestFit` can fail silently
No polynomial in the requested degree range may meet the R² and K-S thresholds. When that happens, `getRSquaredOfFit(true)` and the fitted-mode getters still return numbers — but those numbers describe a non-converged fit and are meaningless. Guard with `if (bestDegree >= 2)` before reporting fitted columns, or widen the degree range / relax the thresholds.

### Pitfall 5 — 2D vs 3D parser signatures differ
`ImageParser2D.setPosition(channel, slice, frame)` takes three ints; `ImageParser3D.setPosition(channel, frame)` takes two. Using the wrong arity fails with `MissingMethodException`. Always branch on `imp.getNSlices() > 1`.

### Pitfall 6 — `Combine Sholl Profiles` is GUI-only
The Neuroanatomy Shortcut Window's grouped-profile merger has no scripted equivalent in this skill. For batch averaging, run the per-sample workflow in a loop and aggregate the exported CSVs downstream.

---

## Files

| File | What it covers |
|------|----------------|
| `GROOVY_SCRIPT_API.md` | Verified scripting entry points, macro boundary, and excluded surfaces |
| `GROOVY_WORKFLOW_IMAGE_SHOLL_ANALYSIS.groovy` | Segmented 2D or 3D image to sampled profile CSV and summary metrics CSV |
| `GROOVY_WORKFLOW_TRACING_SHOLL_ANALYSIS.groovy` | Tracing file to sampled profile CSV and summary metrics CSV |
| `GROOVY_WORKFLOW_PROFILE_STATS_FROM_CSV.groovy` | Sampled profile CSV or TXT to polynomial fit and normalized decay statistics CSV |
| `UI_GUIDE.md` | Launch paths, startup ROI rules, key parameters, and output options |
| `UI_WORKFLOW_IMAGE_AND_TRACING_ANALYSIS.md` | Step-by-step GUI walkthrough for direct image analysis and tracing analysis |

## Functional Coverage

| Capability | Headless workflow | UI documented |
|------------|:-----------------:|:-------------:|
| Direct image Sholl analysis | ✓ | ✓ |
| Tracing-based Sholl analysis | ✓ | ✓ |
| Existing sampled profile statistics | ✓ | ✓ |
| Macro-recorder entry points | — | ✓ |
| Combine Sholl Profiles | — | ✓ |

## Automation Boundary

- Headless-safe workflows in this skill export CSV outputs without opening plots or dialogs.
- GUI workflows use the Sholl dialogs reachable from `Analysis > Sholl` and the `Neuroanatomy Shortcut Window`.
- Recorder-driven macros are documented as official entry points, but this skill does not check in one large generic dialog-string wrapper for every Sholl prompt.
- Grouped profile combination is documented as a GUI capability only.
