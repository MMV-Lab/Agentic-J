# Statistics — Test Selection Reference

Verified against **scipy 1.17.1** (`from scipy import stats`, pre-imported as `stats`),
main env. Every number below was produced by simulation, not quoted from a textbook.
`statsmodels 0.14.6` is also available; `pingouin` is **not** installed.

---

## 1. Always use Welch's t-test. `equal_var=True` is scipy's default and it is wrong.

`stats.ttest_ind(a, b)` defaults to `equal_var=True` — Student's t, which assumes the
two groups share a variance. Cell data almost never does.

False-positive rate over 4000 simulations where **there is no real difference**
(α = 0.05, so a correct test reports ≈ 0.05):

| Situation | Student (`equal_var=True`) | Welch (`equal_var=False`) |
|---|---|---|
| small group has **larger** variance (n=10, sd=4 vs n=50, sd=1) | **0.331** | 0.052 |
| small group has smaller variance (n=10, sd=1 vs n=50, sd=4) | 0.000 | 0.049 |
| equal variance, equal n | 0.052 | 0.051 |

Student's t calls a third of pure-noise comparisons "significant" in the unlucky case,
and is badly over-conservative in the other. **Welch is correct in all three and costs
nothing when the assumptions do hold.**

```python
stats.ttest_ind(a, b, equal_var=False)      # ALWAYS
```

There is no reason to run Levene's/Bartlett's test to "decide" whether to use Welch.
Just use Welch.

---

## 2. Don't let Shapiro-Wilk decide anything at large N

`stats.shapiro` tests "is this *exactly* normal", and at large N it detects deviations
too small to matter. On mildly skewed data (gamma, shape 9) that a t-test handles fine:

| N | Shapiro p | verdict |
|---|---|---|
| 20 | 0.28 | ok |
| 100 | 0.043 | **rejects normality** |
| 1000 | 4e-12 | rejects |
| 5000 | 3e-28 | rejects |

Above N≈5000 scipy itself warns: *"For N > 5000, computed p-value may not be accurate"*.

**Practical rule:**
- **N < ~50 per group** → Shapiro is a reasonable guard. Non-normal → Mann-Whitney.
- **N large** → Shapiro will almost always reject. Judge by the *shape* (skew, outliers,
  bounded data) and by whether the mean is the quantity you care about. Welch's t-test
  on n≥30 per group is robust to moderate non-normality.
- Never report "we tested normality and it passed" as if it proved normality. Failing to
  reject is not proof.

---

## 3. The test menu

| Design | Normal-ish | Non-normal / ordinal |
|---|---|---|
| 2 independent groups | `ttest_ind(a, b, equal_var=False)` | `mannwhitneyu(a, b)` |
| 2 paired measurements | `ttest_rel(a, b)` | `wilcoxon(a, b)` |
| 3+ independent groups | `f_oneway(*groups)` | `kruskal(*groups)` |
| Correlation | `pearsonr(x, y)` | `spearmanr(x, y)` / `kendalltau(x, y)` |
| Counts / proportions | `chi2_contingency(table)` | `fisher_exact(table)` (2×2, small n) |
| No parametric form fits | `stats.permutation_test` | `stats.bootstrap` (CIs) |

**"Paired" means the same object measured twice** (before/after on the same cell). Two
different cells in the same image are *not* paired — they are nested, which is a
different problem (see §6).

---

## 4. NaN silently poisons the result

scipy's default is `nan_policy='propagate'` — a single NaN makes the p-value `nan`,
with no error.

```python
stats.ttest_ind(x, y)                      # -> pvalue = nan
stats.ttest_ind(x, y, nan_policy='omit')   # -> 0.322
```

cp_measure legitimately emits NaN (texture of a uniform object). Decide explicitly:
drop the rows, or pass `nan_policy='omit'`. Never let a `nan` p-value reach the CSV.

---

## 5. A p-value without an effect size is not a result

Always report the magnitude and its uncertainty alongside `p`.

```python
# Cohen's d (pooled SD) — for the t-test family
sp = np.sqrt(((nx-1)*a.var(ddof=1) + (ny-1)*b.var(ddof=1)) / (nx+ny-2))
d = (b.mean() - a.mean()) / sp                       # 0.2 small, 0.5 medium, 0.8 large

# rank-biserial correlation — the Mann-Whitney effect size
U = stats.mannwhitneyu(a, b).statistic
r_rb = 1 - 2*U/(nx*ny)

# 95% CI of the mean difference — scipy gives it directly
res = stats.ttest_ind(a, b, equal_var=False)
ci = res.confidence_interval()                       # ConfidenceInterval(low=, high=)
```

A "significant" result with d = 0.05 and n = 10000 is a real but meaningless difference.
Say so.

---

## 6. Multiple comparisons

cp_measure hands you 271 features. Testing all of them at α=0.05 yields ~14 "significant"
results from pure noise.

Measured on **50 pure-noise comparisons** (no real effect anywhere):

| | count "significant" |
|---|---|
| raw p < 0.05 | 2 / 50 |
| Benjamini-Hochberg adjusted < 0.05 | **0 / 50** |

The smallest raw p was 0.0047 — which BH correctly inflates to 0.233.

```python
adjusted = stats.false_discovery_control(pvalues, method="bh")   # scipy >= 1.11
```
Use BH (FDR) when screening many features. Use Bonferroni (`method` unavailable in
`false_discovery_control`; just `p * n_tests`, capped at 1) only for a handful of
pre-planned confirmatory tests.

**Report both** the raw and adjusted p-values in `Statistics_Results.csv`.

---

## 7. Nesting: cells are not independent samples

If you measured 300 cells across 6 images (3 per condition), your N is **6**, not 300.
Treating cells as independent replicates ("pseudoreplication") is the single most common
error in bioimage statistics.

**Measured** on simulated data with a real treatment effect *and* real between-image
variability — 240 cells across 8 images:

| Analysis | N | p |
|---|---|---|
| pool all cells as if independent | 240 | **9.35e-10** |
| average per image, then test (correct) | 8 | **0.057** |

Seven orders of magnitude, from the same data. The pooled analysis is measuring how
many cells you imaged, not whether the treatment did anything.

The defensible options, cheapest first:
1. **Average per image**, then test on the image means (N = number of images). Simple,
   honest, and what most reviewers expect.
2. **Hierarchical / mixed-effects model** with image as a random effect — use
   `statsmodels.formula.api.mixedlm`.

Whichever you do, **state the unit of replication explicitly** in the output.

---

## 8. Verification — fail loudly, not silently

RAISE `ValueError("VERIFICATION FAILED: ...")` only on things always true for a correct
run:
- the output file exists and is non-empty; the DataFrame has ≥ 1 row when the input had rows
- the columns you read/wrote exist
- **definitional invariants**: p-value within [0,1]; correlation within [-1,1]; n ≥ 0;
  adjusted p ≥ raw p

WARN (`print("WARNING: ...")`) and continue for:
- small sample sizes, group counts, "no significant result"
- effect-size or magnitude expectations
- NaN values — a NaN can be legitimate (variance of a single-value group), so report it;
  do not assert it away

---

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | The mandatory standards: stage separation, handoff contract, verification policy |
| `TEST_SELECTION.md` | This file — Welch vs Student simulation, Shapiro at large N, the test menu, effect sizes, FDR, pseudoreplication |
| `WORKFLOW_TWO_GROUP_STATS.py` | Two-group comparison: normality check → Welch or Mann-Whitney → effect size + CI → `Statistics_Results.csv` |
| `WORKFLOW_CORRELATION_STATS.py` | Correlation with the right coefficient, plus BH-corrected screening of many features |
