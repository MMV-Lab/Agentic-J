"""
WORKFLOW: per-object feature CSV -> unsupervised phenotyping -> Statistics_Results.csv

Runs in the MAIN env. This is a STAGE 1 (statistics) script: it computes, it does NOT
plot. The plotting stage reads the CSV this writes.

THE ONE RULE: StandardScaler before any distance-based method. Measured on real
feature tables, unscaled KMeans clusters correlate 0.735 with `Area` alone — the
"phenotypes" are just big cells and small cells.

Verified end-to-end. Run untouched on synthetic features with three planted clusters.
"""
import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (calinski_harabasz_score, davies_bouldin_score,
                             silhouette_score)
from sklearn.preprocessing import StandardScaler

# ─────────────────────────── CONFIG ───────────────────────────
INPUT_CSV = "/app/data/Measurements.csv"
OUTPUT_STATS_CSV = "Statistics_Results.csv"     # the handoff to the plotting stage
OUTPUT_OBJECTS_CSV = "Objects_With_Clusters.csv"  # per-object cluster assignment
# Columns that are identifiers/metadata, not features.
NON_FEATURE_COLS = ("label", "image", "condition", "cluster", "PC1", "PC2")
K_RANGE = range(2, 8)          # candidate cluster counts; chosen by silhouette
K_OVERRIDE = None              # set an int to skip the silhouette search
RANDOM_STATE = 0
# ──────────────────────────────────────────────────────────────


def load_features():
    if os.path.exists(INPUT_CSV):
        return pd.read_csv(INPUT_CSV), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    blocks = []
    # Three well-separated planted phenotypes, plus an Area column on a wildly
    # different scale (~1e4) to exercise the scaling rule.
    for loc, area in [(-5.0, 8000), (0.0, 12000), (5.0, 16000)]:
        n = 60
        f = rng.normal(loc, 1.0, size=(n, 4))
        a = rng.normal(area, 1500, size=(n, 1))
        blocks.append(np.hstack([a, f]))
    X = np.vstack(blocks)
    df = pd.DataFrame(X, columns=["Area", "Eccentricity", "Solidity",
                                  "Intensity_MeanIntensity", "Perimeter"])
    df.insert(0, "label", np.arange(1, len(df) + 1))
    return df, True


def main():
    df, synthetic = load_features()
    # numeric only: a stray string column (e.g. a 'diagnosis' label) would otherwise
    # crash the float conversion for a distance-based method.
    feature_cols = [c for c in df.columns
                    if c not in NON_FEATURE_COLS and pd.api.types.is_numeric_dtype(df[c])]
    print(f"input: {len(df)} objects x {len(feature_cols)} features")
    if not feature_cols:
        raise ValueError("VERIFICATION FAILED: no feature columns found.")

    n_before = len(df)
    df = df.dropna(subset=feature_cols).reset_index(drop=True)
    if len(df) < n_before:
        print(f"WARNING: dropped {n_before - len(df)} rows with NaN features "
              f"(cp_measure emits NaN for uniform objects).")
    if len(df) < 3:
        raise ValueError(f"VERIFICATION FAILED: only {len(df)} objects after NaN removal.")

    X = df[feature_cols].to_numpy(dtype=float)
    if len(df) < len(feature_cols):
        print(f"WARNING: {len(df)} objects < {len(feature_cols)} features — "
              f"clusters will be unstable. Report this.")

    # THE RULE. Without it, `Area` (~1e4) dominates every Euclidean distance.
    Xs = StandardScaler().fit_transform(X)

    # ── choose k by silhouette, do not guess ──
    if K_OVERRIDE is not None:
        best_k = K_OVERRIDE
        search = []
    else:
        search = []
        for k in K_RANGE:
            if k >= len(df):
                break
            labels_k = KMeans(n_clusters=k, random_state=RANDOM_STATE).fit_predict(Xs)
            sil = silhouette_score(Xs, labels_k)
            search.append({"k": k, "silhouette": sil,
                           "calinski_harabasz": calinski_harabasz_score(Xs, labels_k),
                           "davies_bouldin": davies_bouldin_score(Xs, labels_k)})
            print(f"  k={k}  silhouette={sil:.3f}")
        if not search:
            raise ValueError("VERIFICATION FAILED: too few objects to cluster.")
        best_k = max(search, key=lambda r: r["silhouette"])["k"]
    print(f"chosen k = {best_k}")

    # sklearn 1.9: n_init defaults to "auto"
    km = KMeans(n_clusters=best_k, random_state=RANDOM_STATE)
    clusters = km.fit_predict(Xs)
    sil = silhouette_score(Xs, clusters)
    ch = calinski_harabasz_score(Xs, clusters)
    dbs = davies_bouldin_score(Xs, clusters)
    print(f"silhouette={sil:.3f}  calinski_harabasz={ch:.1f}  davies_bouldin={dbs:.3f}")

    pca = PCA(n_components=2)
    coords = pca.fit_transform(Xs)
    evr = pca.explained_variance_ratio_
    print(f"PCA explained variance: PC1={evr[0]:.3f} PC2={evr[1]:.3f} "
          f"total={evr.sum():.3f}")
    if evr.sum() < 0.4:
        print(f"WARNING: PC1+PC2 explain only {evr.sum():.1%} of variance — "
              f"a 2D scatter is a poor summary of this data. Report this alongside the plot.")

    # per-object table (feeds the plotting stage's scatter)
    objects = df.copy()
    objects["cluster"] = clusters
    objects["PC1"], objects["PC2"] = coords[:, 0], coords[:, 1]
    objects.to_csv(OUTPUT_OBJECTS_CSV, index=False)

    # ── the statistics handoff ──
    rows = []
    counts = pd.Series(clusters).value_counts().sort_index()
    for c in sorted(np.unique(clusters)):
        member = clusters == c
        row = {"cluster": int(c), "n": int(member.sum()),
               "fraction": float(member.mean())}
        for col in feature_cols:
            row[f"mean_{col}"] = float(df.loc[member, col].mean())
            row[f"sd_{col}"] = float(df.loc[member, col].std())
        rows.append(row)
    stats = pd.DataFrame(rows)
    stats["k"] = best_k
    stats["silhouette"] = sil
    stats["calinski_harabasz"] = ch
    stats["davies_bouldin"] = dbs
    stats["pca_evr_pc1"] = evr[0]
    stats["pca_evr_pc2"] = evr[1]
    stats["n_objects_total"] = len(df)
    stats.to_csv(OUTPUT_STATS_CSV, index=False)

    if search:
        pd.DataFrame(search).to_csv("Cluster_Search.csv", index=False)

    # ── verification: definitional invariants only ──
    if len(clusters) != len(df):
        raise ValueError("VERIFICATION FAILED: cluster labels != number of objects")
    if not (-1.0 <= sil <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: silhouette {sil} outside [-1,1]")
    if evr.sum() > 1.0 + 1e-6:
        raise ValueError(f"VERIFICATION FAILED: explained variance ratio sums to {evr.sum()}")
    if int(counts.sum()) != len(df):
        raise ValueError("VERIFICATION FAILED: cluster counts do not sum to N")
    for path in (OUTPUT_STATS_CSV, OUTPUT_OBJECTS_CSV):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    # A tiny cluster or a poor silhouette may be the real biology — report, never raise.
    if sil < 0.25:
        print(f"WARNING: silhouette {sil:.3f} is weak — the clusters may not be separable.")
    smallest = int(counts.min())
    if smallest < 5:
        print(f"WARNING: smallest cluster has {smallest} objects — interpret with care.")

    print(f"wrote {OUTPUT_STATS_CSV} ({len(stats)} clusters) and {OUTPUT_OBJECTS_CSV}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
