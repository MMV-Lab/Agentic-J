# scikit-learn — Python Script API

Verified against **scikit-learn 1.9.0**, main env `/opt/conda/envs/local_imagent_J`.
Every number quoted below was measured by running the code, not taken from a tutorial.

## Version notes (1.9)

- `KMeans(n_init=...)` **defaults to `"auto"`**. You no longer need `n_init=10`; passing
  an integer is still accepted.
- `TSNE` takes **`max_iter`**, not `n_iter` (renamed).
- `StratifiedGroupKFold` exists — use it when you need stratification *and* groups.

## Input contract

sklearn consumes the per-object table your measurement stage produced: one row per
object, one column per feature — exactly what `regionprops_table` or `cp_measure` emits.

```python
feature_cols = [c for c in df.columns if c not in ("label", "image", "condition")]
X = df[feature_cols].to_numpy()
```

Every estimator raises on NaN. Drop or impute first:
```python
df = df.dropna(subset=feature_cols)              # or SimpleImputer(strategy="median")
```
cp_measure legitimately emits NaN for uniform objects, so this is not a rare case.

---

## Scaling: mandatory before any distance-based method

Raw morphology features span wildly different magnitudes: `Area` ~ 1e4 px²,
`Eccentricity` ~ 0.5. Euclidean methods (KMeans, PCA, TSNE, SVM, kNN) are then driven
almost entirely by `Area`.

**Measured** on 180 objects with three planted phenotypes and an `Area`-like column
at ~1e4, scoring the recovered clusters against the known truth
(`adjusted_rand_score`, 1.0 = perfect):

| | ARI vs planted truth | max \|corr(cluster, Area)\| |
|---|---|---|
| raw features | 0.767 | 0.735 |
| `StandardScaler` first | **1.000** | 0.511 |

Unscaled, the clusters are largely just "big" and "small" — KMeans never recovers the
real phenotypes. Always:
```python
Xs = StandardScaler().fit_transform(X)
```

---

## Leakage: what actually matters

The folklore says "always scale inside a Pipeline or you leak." That is good hygiene,
but it dramatically understates *which* step leaks. Measured on **pure noise**
(`X` = 60×2000 Gaussian, `y` = random labels, so the true balanced accuracy is **0.50**):

| Setup | Reported balanced accuracy |
|---|---|
| `StandardScaler` fit outside CV | 0.517 |
| `StandardScaler` inside `Pipeline` | 0.500 |
| **`SelectKBest` fit outside CV** | **0.833** |
| `SelectKBest` inside `Pipeline` | 0.383 |

**The scaler leak is small. Any SUPERVISED preprocessing done outside the CV loop is
catastrophic.** `SelectKBest` looked at `y` for all 60 samples, picked the 10 features
that happened to correlate with the labels, and then "cross-validated" on them —
reporting 83% accuracy on data with no signal whatsoever.

Rule: **anything that touches `y`, or that learns parameters from the data, goes inside
the `Pipeline`.** Feature selection, scaling, imputation, PCA, resampling — all of it.

```python
pipe = Pipeline([
    ("scale", StandardScaler()),
    ("select", SelectKBest(f_classif, k=10)),
    ("clf", RandomForestClassifier(n_estimators=500, random_state=0)),
])
scores = cross_val_score(pipe, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0),
                         scoring="balanced_accuracy")
```

### Group leakage

If several cells come from the same image or animal, cells from one image must not
appear in both train and test — otherwise the model memorises the image, not the
phenotype.

**Measured** on 12 images × 10 cells, where the label is a property of the *image*:

| CV splitter | Reported balanced accuracy |
|---|---|
| `StratifiedKFold` (splits cells) | 0.931 |
| `GroupKFold(groups=image_id)` | 0.873 |

```python
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
cross_val_score(pipe, X, y, cv=GroupKFold(n_splits=4), groups=df["image"], ...)
```

---

## Choosing the scorer

`get_scorer_names()` lists them all. The ones that matter here:

| Scorer | Use when |
|---|---|
| `balanced_accuracy` | imbalanced classes — the default choice for cell data |
| `f1_macro` | imbalanced, and you care about per-class precision/recall |
| `matthews_corrcoef` | single robust number for binary, imbalance-safe |
| `roc_auc` / `roc_auc_ovr` | ranking quality, binary / multiclass |
| `accuracy` | **only** when classes are balanced |

Plain `accuracy` on a 90/10 split reports 0.90 for a model that always predicts one
class. Never report it for cell data without also reporting the class balance.

**Always report `mean ± SD across folds`**, never a single train/test split — with the
small N typical of imaging experiments, one split is noise.

---

## Unsupervised phenotyping

```python
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score

Xs = StandardScaler().fit_transform(X)

for k in range(2, 8):                      # choose k by silhouette, do not guess
    labels_k = KMeans(n_clusters=k, random_state=0).fit_predict(Xs)
    print(k, silhouette_score(Xs, labels_k))

pca = PCA(n_components=2)
coords = pca.fit_transform(Xs)
print(pca.explained_variance_ratio_, pca.explained_variance_ratio_.sum())
```

| Metric | Range | Better |
|---|---|---|
| `silhouette_score` | [-1, 1] | higher |
| `calinski_harabasz_score` | [0, ∞) | higher |
| `davies_bouldin_score` | [0, ∞) | lower |

**Always print `explained_variance_ratio_`.** A PCA scatter where PC1+PC2 explain 12% of
the variance is not evidence of anything, and must be reported as such.

`TSNE` is for **visualisation only** — distances between clusters in a t-SNE plot are
not meaningful, and it must never be fed into a downstream classifier. Run PCA to ~30
components first, then `TSNE(n_components=2, perplexity=30, max_iter=1000)`.

---

## Feature importance

```python
from sklearn.inspection import permutation_importance
pipe.fit(X_train, y_train)
r = permutation_importance(pipe, X_test, y_test, n_repeats=20, random_state=0,
                           scoring="balanced_accuracy")
```

Prefer `permutation_importance` over `clf.feature_importances_`. The built-in Gini
importance is biased toward high-cardinality continuous features, and cp_measure's 271
features are heavily correlated, which splits importance arbitrarily among near-duplicate
columns. Note permutation importance on *correlated* features also under-reports each of
them (the model can lean on the twin) — say so when you report it.

Compute it on **held-out** data. On training data it measures memorisation.

---

## Verification — fail loudly, not silently

RAISE on definitional invariants only:
- `silhouette_score` within [-1, 1]; accuracy/balanced_accuracy within [0, 1]
- `pca.explained_variance_ratio_.sum() <= 1.0 + 1e-6`
- number of cluster labels equals number of rows
- the output CSV exists and is non-empty

WARN, never raise, on:
- low accuracy, poor silhouette, a cluster with few members — that may be the real biology
- CV standard deviation larger than the mean effect
- fewer samples than features (report it; it is the norm for cp_measure output)

## Handing off

Clustering and classification belong to the STATISTICS stage. Write results (cluster
label per object, silhouette, CV mean/SD, PC coordinates, explained variance) into
`Statistics_Results.csv`. The plotting script reads that CSV and never refits a model.
See the `statistics` and `plotting` skills.

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | When to use sklearn, the scaling rule, the leakage rule |
| `SCRIPT_API.md` | This file — measured leakage numbers, scorer table, 1.9 API changes |
| `WORKFLOW_PHENOTYPE_CLUSTERING.py` | Feature CSV → scale → choose k by silhouette → KMeans + PCA → `Statistics_Results.csv` |
| `WORKFLOW_CLASSIFY_CELLTYPES.py` | Feature CSV → leakage-free `Pipeline` → grouped CV → permutation importance → `Statistics_Results.csv` |
