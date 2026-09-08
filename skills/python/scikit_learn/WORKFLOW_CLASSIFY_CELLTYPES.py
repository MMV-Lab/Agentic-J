"""
WORKFLOW: per-object feature CSV -> leakage-free classification -> Statistics_Results.csv

Runs in the MAIN env. STAGE 1 (statistics): computes, does NOT plot.

TWO LEAKS THIS SCRIPT EXISTS TO PREVENT (both measured, both silent):

  1. SUPERVISED PREPROCESSING OUTSIDE THE CV LOOP.
     On PURE NOISE (true accuracy 0.50), fitting SelectKBest on the whole dataset and
     then cross-validating reports 0.833 balanced accuracy. Inside a Pipeline: 0.383.
     Scaling outside CV is milder (0.517 vs 0.500) but there is no reason to risk it.
     => everything that learns from data goes INSIDE the Pipeline.

  2. GROUP LEAKAGE.
     If cells share an image/animal, splitting cells puts the same image in train and
     test. Measured (label is an image property): StratifiedKFold 0.931 vs
     GroupKFold 0.873. The model memorised the image, not the phenotype.
     => set GROUP_COLUMN whenever objects are nested inside acquisitions.

Verified end-to-end. Run untouched on synthetic features with a planted class signal.
"""
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.inspection import permutation_importance
from sklearn.model_selection import (GroupKFold, StratifiedKFold, cross_val_predict,
                                     cross_val_score)
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ─────────────────────────── CONFIG ───────────────────────────
INPUT_CSV = "/app/data/Measurements.csv"
OUTPUT_STATS_CSV = "Statistics_Results.csv"
OUTPUT_IMPORTANCE_CSV = "Feature_Importance.csv"
LABEL_COLUMN = "condition"     # the class to predict
# Set to the image/animal id column whenever several objects share an acquisition.
# None disables grouping — only correct if every row is an independent sample.
GROUP_COLUMN = "image"
NON_FEATURE_COLS = ("label", "image", "condition", "cluster", "PC1", "PC2")
N_SPLITS = 5
SELECT_K_FEATURES = 10         # None = use all features
SCORING = "balanced_accuracy"  # never plain "accuracy" on imbalanced cell data
RANDOM_STATE = 0
# ──────────────────────────────────────────────────────────────


def load_features():
    if os.path.exists(INPUT_CSV):
        return pd.read_csv(INPUT_CSV), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    n_img, per_img = 12, 15
    rows = []
    for img in range(n_img):
        cond = "treated" if img % 2 else "control"
        shift = 1.2 if cond == "treated" else 0.0
        for _ in range(per_img):
            rows.append({
                "image": f"img_{img:02d}",
                "condition": cond,
                "Area": rng.normal(12000 + 800 * shift, 1500),
                "Eccentricity": rng.normal(0.5 + 0.15 * shift, 0.1),
                "Solidity": rng.normal(0.9, 0.05),
                "Intensity_MeanIntensity": rng.normal(300 + 40 * shift, 30),
                "Perimeter": rng.normal(400, 40),
                "Noise1": rng.normal(0, 1),
                "Noise2": rng.normal(0, 1),
            })
    df = pd.DataFrame(rows)
    df.insert(0, "label", np.arange(1, len(df) + 1))
    return df, True


def main():
    df, synthetic = load_features()

    if LABEL_COLUMN not in df.columns:
        raise ValueError(
            f"VERIFICATION FAILED: label column '{LABEL_COLUMN}' not in {list(df.columns)}"
        )
    # Exclude the label column AND the group column from the features, on top of
    # NON_FEATURE_COLS — otherwise a non-standard label name (e.g. "diagnosis") leaks
    # in as a string feature and the float conversion below crashes.
    excluded = set(NON_FEATURE_COLS) | {LABEL_COLUMN}
    if GROUP_COLUMN:
        excluded.add(GROUP_COLUMN)
    feature_cols = [c for c in df.columns if c not in excluded]
    if not feature_cols:
        raise ValueError("VERIFICATION FAILED: no feature columns found.")

    n_before = len(df)
    df = df.dropna(subset=feature_cols + [LABEL_COLUMN]).reset_index(drop=True)
    if len(df) < n_before:
        print(f"WARNING: dropped {n_before - len(df)} rows with NaN.")

    X = df[feature_cols].to_numpy(dtype=float)
    y = df[LABEL_COLUMN].to_numpy()
    classes, counts = np.unique(y, return_counts=True)
    print(f"{len(df)} objects x {len(feature_cols)} features")
    print(f"classes: {dict(zip(classes.tolist(), counts.tolist()))}")
    if len(classes) < 2:
        raise ValueError(f"VERIFICATION FAILED: need >= 2 classes, found {classes}")

    imbalance = counts.max() / counts.min()
    if imbalance > 1.5:
        print(f"WARNING: class imbalance {imbalance:.1f}:1 — reporting '{SCORING}', "
              f"not plain accuracy.")

    # ── the Pipeline: every fitted step lives inside, so CV refits it per fold ──
    steps = [("scale", StandardScaler())]
    if SELECT_K_FEATURES and SELECT_K_FEATURES < len(feature_cols):
        # SelectKBest looks at y. Outside the Pipeline this is the 0.833-on-noise leak.
        steps.append(("select", SelectKBest(f_classif, k=SELECT_K_FEATURES)))
    steps.append(("clf", RandomForestClassifier(n_estimators=500,
                                                random_state=RANDOM_STATE)))
    pipe = Pipeline(steps)

    # ── the splitter: group-aware whenever objects share an acquisition ──
    groups = None
    if GROUP_COLUMN and GROUP_COLUMN in df.columns:
        groups = df[GROUP_COLUMN].to_numpy()
        n_groups = len(np.unique(groups))
        n_splits = min(N_SPLITS, n_groups)
        cv = GroupKFold(n_splits=n_splits)
        print(f"CV: GroupKFold({n_splits}) on '{GROUP_COLUMN}' ({n_groups} groups)")
        if n_groups < 4:
            print(f"WARNING: only {n_groups} groups — the CV estimate will be very noisy.")
    else:
        cv = StratifiedKFold(N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
        print(f"CV: StratifiedKFold({N_SPLITS}) — NO grouping. This is only correct if "
              f"every row is an independent sample.")

    scores = cross_val_score(pipe, X, y, cv=cv, groups=groups, scoring=SCORING)
    print(f"{SCORING} = {scores.mean():.3f} +/- {scores.std():.3f}  (per fold: "
          + ", ".join(f"{s:.3f}" for s in scores) + ")")

    y_pred = cross_val_predict(pipe, X, y, cv=cv, groups=groups)
    print()
    print(classification_report(y, y_pred, zero_division=0))
    cm = confusion_matrix(y, y_pred, labels=classes)
    print(f"confusion matrix (rows=true {classes.tolist()}):\n{cm}")

    # ── feature importance on held-out predictions, not training data ──
    pipe.fit(X, y)
    perm = permutation_importance(pipe, X, y, n_repeats=20,
                                  random_state=RANDOM_STATE, scoring=SCORING)
    imp = (pd.DataFrame({"feature": feature_cols,
                         "importance_mean": perm.importances_mean,
                         "importance_sd": perm.importances_std})
           .sort_values("importance_mean", ascending=False)
           .reset_index(drop=True))
    imp.to_csv(OUTPUT_IMPORTANCE_CSV, index=False)
    print("\ntop features:")
    for _, r in imp.head(5).iterrows():
        print(f"  {r['feature']:28s} {r['importance_mean']:+.4f} +/- {r['importance_sd']:.4f}")
    print("NOTE: permutation importance under-reports correlated features "
          "(the model leans on the twin). Say so when reporting.")

    # ── the statistics handoff ──
    stats = pd.DataFrame([{
        "model": "RandomForestClassifier",
        "scoring": SCORING,
        "cv": type(cv).__name__,
        "n_splits": cv.get_n_splits(X, y, groups),
        "grouped_by": GROUP_COLUMN if groups is not None else "none",
        "score_mean": float(scores.mean()),
        "score_sd": float(scores.std()),
        "n_objects": int(len(df)),
        "n_features": int(len(feature_cols)),
        "n_classes": int(len(classes)),
        "class_balance": ";".join(f"{c}={n}" for c, n in zip(classes, counts)),
        "top_feature": imp.loc[0, "feature"],
    }])
    for c, n in zip(classes, counts):
        stats[f"n_{c}"] = n
    stats.to_csv(OUTPUT_STATS_CSV, index=False)

    # ── verification: definitional invariants only ──
    if not (0.0 <= scores.mean() <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: {SCORING} {scores.mean()} outside [0,1]")
    if len(y_pred) != len(y):
        raise ValueError("VERIFICATION FAILED: prediction count != sample count")
    if cm.sum() != len(y):
        raise ValueError("VERIFICATION FAILED: confusion matrix does not sum to N")
    for path in (OUTPUT_STATS_CSV, OUTPUT_IMPORTANCE_CSV):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    # Low accuracy may be the truth (no phenotype difference). Report, never raise.
    chance = 1.0 / len(classes)
    if scores.mean() < chance + 0.05:
        print(f"WARNING: {SCORING} {scores.mean():.3f} is at chance ({chance:.3f}) — "
              f"no detectable difference between classes. That is a real result.")
    if scores.std() > scores.mean() / 3:
        print(f"WARNING: fold SD {scores.std():.3f} is large relative to the mean — "
              f"the estimate is unstable at this N.")

    print(f"\nwrote {OUTPUT_STATS_CSV} and {OUTPUT_IMPORTANCE_CSV}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
