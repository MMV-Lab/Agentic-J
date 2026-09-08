---
name: scikit_learn
description: >-
  scikit-learn (`import sklearn`) is available in the MAIN env (local_imagent_J). Use it to turn
  a per-object measurement table (from regionprops_table or cp_measure) into biology —
  unsupervised phenotyping (StandardScaler + PCA + KMeans, silhouette to choose k), supervised
  classification of cell types with cross-validation, permutation feature importance, and outlier
  detection. MANDATORY: StandardScaler before ANY distance-based method (KMeans, PCA, TSNE, SVM,
  kNN) — measured, unscaled KMeans recovers planted clusters at ARI 0.77 versus 1.00 scaled,
  because Area (~1e4 px) dwarfs Eccentricity (~0.5). MANDATORY: put every fitted step inside a
  Pipeline — supervised feature selection done outside the CV loop reports 0.83 balanced accuracy
  on PURE NOISE (true 0.50). MANDATORY: use GroupKFold when cells share an image or animal, and
  report cross_val_score mean ± SD, never a single split. Use for
  classification/clustering/dimensionality reduction; use the `statistics` skill for hypothesis
  testing.
---

# scikit-learn — Documentation Index

Main env (`local_imagent_J`). Version **1.9.0**. Import as `sklearn`.

**Use it for**: phenotyping (clustering), cell-type classification, dimensionality
reduction, feature importance, outlier detection.
**Do NOT use it for**: hypothesis testing (p-values, group comparisons) — that is the
`statistics` skill and `scipy.stats`.

## Input contract

One row per object, one column per feature — exactly what
`skimage.measure.regionprops_table` or `cp_measure` emits.

```python
feature_cols = [c for c in df.columns if c not in ("label", "image", "condition")]
X = df[feature_cols].to_numpy()
df = df.dropna(subset=feature_cols)     # every estimator raises on NaN
```
cp_measure legitimately emits NaN for uniform objects, so NaN handling is not optional.

## Rule 1 — scale before any distance-based method

`Area` ~ 1e4 px², `Eccentricity` ~ 0.5. Euclidean methods (KMeans, PCA, TSNE, SVM, kNN)
are then driven almost entirely by `Area`, and the "phenotypes" are just big cells and
small cells.

Measured on 180 objects with three planted phenotypes, scored against the known truth:

| | ARI vs truth (1.0 = perfect) |
|---|---|
| raw features | 0.767 |
| `StandardScaler` first | **1.000** |

## Rule 2 — every fitted step goes inside the Pipeline

The usual advice is "scale inside a Pipeline or you leak". True, but it misses which
step actually leaks. Measured on **pure noise** (60×2000 Gaussian, random labels, so the
honest answer is 0.50 balanced accuracy):

| Setup | Reported |
|---|---|
| `StandardScaler` outside CV | 0.517 |
| **`SelectKBest` outside CV** | **0.833** |
| both inside `Pipeline` | 0.50 / 0.383 |

The scaler leak is small. **Supervised preprocessing outside the CV loop is
catastrophic** — `SelectKBest` peeked at every label, kept the 10 features that happened
to correlate, and then reported 83% accuracy on data with no signal at all.

Anything that touches `y`, or learns parameters from the data, goes inside the Pipeline:
selection, scaling, imputation, PCA, resampling.

## Rule 3 — group your splits

If cells share an image or animal, cells from one image must not appear in both train
and test. Measured, where the label is a property of the image:

| Splitter | Reported |
|---|---|
| `StratifiedKFold` (splits cells) | 0.931 |
| `GroupKFold(groups=image_id)` | 0.873 |

## Rule 4 — report mean ± SD, and the right scorer

Never a single train/test split — with the small N typical of imaging, one split is
noise. Use `balanced_accuracy` or `f1_macro` for imbalanced classes; plain `accuracy` on
a 90/10 split reports 0.90 for a model that always predicts one class.

## Choosing k, and reading PCA honestly

Pick `k` by `silhouette_score`, don't guess. Always print
`pca.explained_variance_ratio_` — a PCA scatter where PC1+PC2 explain 12% of the
variance is not evidence of anything, and must be reported as such.

`TSNE` is for **visualisation only**. Distances between its clusters are not meaningful,
and it must never feed a downstream classifier. (1.9 renamed its `n_iter` → `max_iter`.)

## Feature importance

Prefer `permutation_importance` on held-out data over `clf.feature_importances_`: Gini
importance is biased toward high-cardinality continuous features. Note that permutation
importance also *under-reports* correlated features — with cp_measure's 271 heavily
correlated columns the model just leans on the twin. Say so when you report it.

## Handing off

Clustering and classification belong to the STATISTICS stage. Write results (cluster per
object, silhouette, CV mean/SD, PC coordinates, explained variance) into
`Statistics_Results.csv`. The plotting script reads that CSV and never refits a model.

## Verification

RAISE on definitional invariants: `silhouette_score` in [-1, 1]; accuracy in [0, 1];
`explained_variance_ratio_.sum() <= 1 + 1e-6`; cluster labels equal rows.
WARN, never raise, on low accuracy, poor silhouette, a tiny cluster, or N < features —
those may be the real biology.

## Files

| File | What it covers |
|---|---|
| `SCRIPT_API.md` | Measured leakage and scaling numbers, scorer table, cluster metrics, 1.9 API changes |
| `WORKFLOW_PHENOTYPE_CLUSTERING.py` | Feature CSV → scale → choose k by silhouette → KMeans + PCA → `Statistics_Results.csv` |
| `WORKFLOW_CLASSIFY_CELLTYPES.py` | Feature CSV → leakage-free `Pipeline` → `GroupKFold` → permutation importance → `Statistics_Results.csv` |

Both workflows run untouched on synthetic data with a planted signal, so you can see
them recover it.
