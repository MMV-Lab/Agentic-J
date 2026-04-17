# Sholl Analysis — UI GUIDE

This document covers the Sholl dialogs shipped with SNT and how to drive them interactively. For scripted use see [SKILL.md](SKILL.md) and [GROOVY_SCRIPT_API.md](GROOVY_SCRIPT_API.md).

## Launching

| Task | Menu path |
|------|-----------|
| Direct image Sholl | `Analysis ▶ Sholl ▶ Sholl Analysis...` |
| Tracing-based Sholl + auxiliary tools | `Plugins ▶ Neuroanatomy ▶ Neuroanatomy Shortcut Window` |
| Grouped profile aggregation | `Combine Sholl Profiles...` (from the Shortcut Window) |
| Script templates | Script Editor: `Templates ▶ Neuroanatomy` |

---

## Direct Image Analysis

**Input:** a segmented or thresholdable single-cell 2D or 3D image. Use `Image ▶ Adjust ▶ Threshold...` first and confirm that the neuronal processes are foreground (not background).

**Startup ROI defines the analysis center** — the dialog reads whatever ROI is on the active image at launch time:

| ROI type | What it sets |
|----------|--------------|
| Straight line | Center (start of line) + ending radius (end of line) |
| Single point | Center only |
| Multipoint | Center (first point) + primary-branch count (remaining points) |

Launch `Analysis ▶ Sholl ▶ Sholl Analysis...` once the ROI is ready.

---

## Tracing Analysis

Use the Neuroanatomy Shortcut Window when you want tracing-based Sholl without opening the full SNT tracing interface. From the Shortcut Window choose `Sholl Analysis (Tracings)...`.

| Control | Accepted values / behaviour |
|---------|----------------------------|
| Input file | `.swc`, `.ndf`, `.json`, or `.traces` reconstructions |
| Center | Root node, or any soma-tagged node in the tree |
| Path filter | Restrict analysis to tagged subtrees (e.g. axon, dendrite) |

---

## Existing Profile Analysis

Previously sampled profiles are analyzed through scripting rather than a dedicated end-user dialog — see [GROOVY_WORKFLOW_PROFILE_STATS_FROM_CSV.groovy](GROOVY_WORKFLOW_PROFILE_STATS_FROM_CSV.groovy). The input table must contain one radius column and one count column, both named in the header row. Script templates under `Templates ▶ Neuroanatomy` include related examples.

---

## Key Parameters

### Shell sampling

| Control | Description |
|---------|-------------|
| **Profile type** | `intersections` (count shell crossings) or `intersected length` (sum of arbor length within each shell) |
| **Start radius** | Inner shell, physical units |
| **Step size** | Radius step between shells; small values approximate a continuous profile |
| **End radius** | Outer shell, physical units |
| **Hemishells** | Restrict sampling to sub-compartments (e.g. north / south / east / west hemisphere) |

### Image-based refinements

| Control | Applies to | Description |
|---------|-----------|-------------|
| **Samples per radius** | 2D | Number of concentric samples averaged per shell (noise reduction) |
| **Samples integration** | 2D | How per-sample counts combine (mean / median / mode) |
| **Ignore isolated voxels** | 3D | Drop single-voxel foreground islands before counting |

### Fitting and normalization

| Control | Description |
|---------|-------------|
| **Polynomial fit** | Manual degree, or best-fit search over a degree range with R² and p-value thresholds |
| **Normalization** | `semi-log` or `log-log` — selects the Sholl decay model |

### Output options

| Control | Produces |
|---------|---------|
| **Plots** | Linear profile + normalized profile |
| **Tables** | Detailed per-shell table + single-value summary table |
| **Annotation ROIs** | Sampling shells and intersection points (optional) |

---

## Outputs

- Linear profile and normalized profile (plot + table)
- Detailed per-shell table and single-value summary table
- Optional annotation ROIs (sampling shells, intersection points)
- Grouped plots and mean ± SD profiles via `Combine Sholl Profiles...`

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Dialog refuses to launch / complains about the image | No startup ROI, or the image is not thresholded | Draw a line/point/multipoint ROI on the arbor and threshold via `Image ▶ Adjust ▶ Threshold...` |
| Profile is empty or all zeros | Foreground and background inverted | Re-threshold with **Dark background** enabled (or use `Otsu dark` in scripts) |
| Center clearly off the arbor | Startup ROI placed off-target | Re-draw the ROI at the soma / branch point and relaunch |
| Very few samples in the profile | Step size too large for the radius range | Reduce **Step size**, or widen **Start radius** / **End radius** |
| Distal shells missing from the profile | End radius clipped by image bounds | Crop the image centered on the arbor, or accept `maxPossibleRadius` |
| Best-fit polynomial never converges | Noisy profile, or degree range too narrow | Widen the degree range; relax the R² floor or p-value ceiling |
| Tracing dialog reports "no tree" | File format not supported by SNT's `Tree.fromFile` | Save the reconstruction as `.swc`, `.ndf`, `.json`, or `.traces` |
| Grouped plot has no curves | Inconsistent column headers across input CSVs | Standardize the radius / count column names before running `Combine Sholl Profiles...` |
