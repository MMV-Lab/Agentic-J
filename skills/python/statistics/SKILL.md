---
name: statistics
description: >-
  Statistical rigor standards for the Python agent's hypothesis-testing scripts (STAGE 1:
  STATISTICAL ANALYSIS). Never assume normality, but note Shapiro-Wilk is over-powered above
  n~100 and powerless below n~8. ALWAYS use Welch (equal_var=False): scipy's ttest_ind default
  equal_var=True gives 33% false positives when the smaller group has the larger variance. Cells
  nested in images are NOT independent — pooling them turned p=0.057 into p=9e-10 on the same
  data. Screening many features needs Benjamini-Hochberg (stats.false_discovery_control). Report
  an effect size and CI, never a bare p-value; scipy's default nan_policy='propagate' silently
  returns a NaN p-value. Defines the data handoff (p-values, N, means, SD go to
  Statistics_Results.csv, which the plotting stage reads), the IQR outlier rule, and the
  fail-loudly verification policy. PROHIBITION: statistics scripts contain NO plotting code.
---

# Statistical Analysis Standards (MANDATORY)

> **STAGE SEPARATION.** Statistics is STAGE 1. NEVER combine statistics and plotting in
> the same script. Do NOT include any plotting code here. The Supervisor runs this
> script and only calls you for plotting AFTER `Statistics_Results.csv` exists.

## Core philosophy

1. **VERIFY FIRST**: Always use `inspect_csv_header` ONCE on the input you were given.
   If a column looks wrong, write the script defensively (e.g. print `df.columns` near
   the top) and hand off — do NOT re-inspect or loop; you cannot see execution output.
2. **RIGOR FIRST**: Never assume data is normal. But do not let a normality test decide
   for you at the wrong sample size — see below.
3. **PROJECT STATE**: If a "PROJECT STATE" section is included in your input, use it for
   the scientific goal, image calibration (so reported units are μm² not px²), and
   experimental conditions (for group labels).

## The four rules, each measured

**1. Welch, always.** `stats.ttest_ind(a, b)` defaults to `equal_var=True` (Student's).
Over 4000 simulations with *no real difference*, Student reports a significant result
**33.1%** of the time when the smaller group has the larger variance. Welch reports
5.2% — correct. When variances are equal, Welch costs nothing (0.051 vs 0.052).
→ `stats.ttest_ind(a, b, equal_var=False)`

**2. Shapiro-Wilk is only informative in the middle.** On mildly skewed data a t-test
handles fine, Shapiro rejects normality at n=100 (p=0.043), n=1000 (p=4e-12),
n=5000 (p=3e-28). Below n≈8 it has almost no power. Use it as a guard for
**8 ≤ n ≲ 50**; above that judge by shape, below that take the rank test.

**3. Cells nested in images are not independent samples.** Simulated: 240 cells in 8
images, real effect plus real between-image variability.
Pooling all cells → **p = 9.35e-10**. Averaging per image (N=8) → **p = 0.057**.
Same data. State your unit of replication.

**4. Screening many features needs FDR.** cp_measure gives 271 features; at α=0.05 about
14 come out "significant" from pure noise. On 50 noise comparisons, 2 passed raw
p<0.05 and **0** survived Benjamini-Hochberg.
→ `stats.false_discovery_control(pvalues, method="bh")`

## Test selection

| Design | Normal-ish | Non-normal / ordinal |
|---|---|---|
| 2 independent groups | `ttest_ind(a, b, equal_var=False)` | `mannwhitneyu(a, b)` |
| 2 paired measurements | `ttest_rel(a, b)` | `wilcoxon(a, b)` |
| 3+ groups | `f_oneway(*groups)` | `kruskal(*groups)` |
| Correlation | `pearsonr(x, y)` | `spearmanr(x, y)` |
| Counts | `chi2_contingency(t)` | `fisher_exact(t)` |

Report which test you chose **and** the normality p-value that justified it.

## A p-value is not a result

Always report magnitude and uncertainty: Cohen's d (t-test family) or rank-biserial r
(Mann-Whitney), plus the 95% CI — `res.confidence_interval()` on a scipy t-test result.
A significant result with d=0.05 at n=10000 is real and meaningless. Say so.

## NaN

scipy's default `nan_policy='propagate'` returns a **NaN p-value with no error**.
cp_measure legitimately emits NaN. Drop the rows or pass `nan_policy='omit'` — never let
a NaN p-value reach the CSV.

## Data handoff contract

- **Output**: a script that performs hypothesis testing and SAVES all results
  (p-values, N, means, SD, effect size, CI) into `Statistics_Results.csv`.
- That CSV is the ONLY channel to the plotting stage. Anything the figure needs must be
  a column in it.
- **PROHIBITION**: no plotting code in this script.

## Coding rules

- Use the pre-initialized `pd`, `np`, `stats` — do NOT re-import them.
- ALWAYS use raw strings for Windows paths: `r'C:\Users\...'`
- ALWAYS explicitly print the p-value and test statistic to stdout.
- **HANDLE OUTLIERS**: if data looks noisy, calculate and report the number of outliers
  using the IQR method. Print the count detected before deciding on removal logic.

## Documentation requirement

Your script description must be short and precise, and must include output file names
and processing parameters — e.g. "IQR outlier removal with threshold=1.5",
"Mann-Whitney U test, p=0.023".

## Result verification — fail loudly, not silently

A clean run must mean the RESULT IS REAL, not merely that nothing threw.

**RAISE** — `raise ValueError("VERIFICATION FAILED: <what>")` — ONLY on conditions
ALWAYS true for a correct run, NEVER on guesses about the data:
- the output was written: the stats file exists and is non-empty; the output DataFrame
  has ≥ 1 row when the input had rows;
- the expected STRUCTURE is present: the columns you read/wrote exist;
- MATHEMATICAL / definitional invariants: a p-value within [0,1]; a correlation within
  [-1,1]; n and counts ≥ 0; a BH-adjusted p ≥ its raw p. These fail only on a real bug.

**DANGER** — do NOT raise on assumptions about the DATA; that rejects VALID results.
LOG a warning (`print("WARNING: ...")`) and continue for:
- small sample sizes, group counts, or "no significant result";
- effect-size or magnitude expectations;
- NaN values — a NaN can be legitimate (e.g. correlation or variance of a constant or
  single-value group), so report it; do not assert it away.

## Files

| File | What it covers |
|---|---|
| `TEST_SELECTION.md` | The Welch-vs-Student simulation, Shapiro at every N, the full test menu, effect sizes, FDR, pseudoreplication — all with measured numbers |
| `WORKFLOW_TWO_GROUP_STATS.py` | Two-group comparison: nesting check → normality guard → Welch or Mann-Whitney → effect size + CI → `Statistics_Results.csv`. Prints what pseudoreplication would have claimed |
| `WORKFLOW_CORRELATION_STATS.py` | Pearson + Spearman with outlier reporting, plus BH-corrected screening of many features |

Both workflows run untouched on synthetic data.
