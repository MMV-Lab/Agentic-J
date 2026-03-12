# BigStitcher — Skill Quick Reference

## What BigStitcher Is

A Fiji plugin for stitching and fusing multi-tile, multi-angle, multi-TB
microscopy datasets. Stores all state in an XML project file; uses BigDataViewer
for interactive display. Primary use cases: cleared-tissue lightsheet stitching,
tiled confocal reconstruction, multi-view lightsheet registration.

**Publication:** Hörl et al., Nature Methods 2019. DOI: 10.1038/s41592-019-0501-0

---

## Can BigStitcher Be Automated via Groovy?

**YES — fully.** All BigStitcher processing steps are exposed as
macro-recordable commands under `Plugins › BigStitcher › Batch Processing`.
These are callable from Groovy (and any other Fiji scripting language) via
`IJ.run()`. The complete pipeline — dataset definition, phase correlation,
global optimization, fusion — can be run from the Fiji Script Editor:

```groovy
IJ.run("Calculate pairwise shifts ...", "select=/path/to/dataset.xml ...")
IJ.run("Optimize globally and apply shifts ...", "select=/path/to/dataset.xml ...")
IJ.run("Fuse dataset ...", "select=/path/to/dataset.xml ...")
```

Use the **Macro Recorder** (`Plugins › Macros › Record…`) to capture exact
parameter strings while working interactively — then paste them into your
Groovy script.

---

## Processing Pipeline (Stitching Mode)

```
IJ.run("Define dataset ...")           →  Import + re-save as HDF5
IJ.run("Calculate pairwise shifts ...") →  Phase correlation between tile pairs
IJ.run("Filter pairwise shifts ...")    →  Discard low-quality links (min_r ≥ 0.7)
IJ.run("Optimize globally ...")         →  Globally consistent registration
IJ.run("ICP Refinement ...")           →  (Optional) Affine aberration correction
IJ.run("Fuse dataset ...")             →  Write fused TIFF or HDF5
```

All steps operate on a shared XML file that records every registration state
change. Each IJ.run() call is **synchronous**.

---

## Key Parameters (Most Commonly Needed)

| Parameter | Typical value | Notes |
|---|---|---|
| `tiles_x`, `tiles_y` | dataset-specific | From acquisition settings |
| `overlap_x_(%)` | 10 | Match acquisition overlap |
| `grid_type` | `Snake: Right & Down      ` | Trailing spaces are part of the key |
| `downsample_in_x/y/z` | `2` | Use `4` for faster/coarser result |
| `min_r` | `0.7` | Cross-correlation threshold |
| `global_optimization_strategy` | `Two-Round using Metadata to align unconnected Tiles` | Use when empty-tile gaps exist |
| `fix_group_0-0,` | always | Trailing comma required |
| `pixel_type` in Fuse | `16-bit unsigned integer` | For fluorescence data |

---

## Critical Pitfalls

1. **Trailing whitespace in `grid_type`** — the exact string must match what
   the Macro Recorder captures. Always use Macro Recorder to verify.
2. **Trailing comma in `fix_group_0-0,`** — required; missing it breaks the
   global optimization reference frame.
4. **Re-save to a different path than input** — writing HDF5 into the same
   folder as raw files is allowed but can cause confusion; use a subdirectory.
5. **Fusion before optimization** — fusing with unregistered positions produces
   a broken output. Always run optimize → (ICP) → fuse in order.
6. **ICP requires sufficient shared signal** — if tiles share little overlap
   content, affine ICP will diverge. Use translation model as fallback.

---

## Automation Pathways Summary

| Pathway | Best for |
|---|---|
| BigStitcher GUI | Interactive exploration, visual QC, manual link curation |
| `IJ.run()` in Groovy | Scripted pipeline automation from the Fiji Script Editor |

---

## File Inventory

| File | Contents |
|---|---|
| `OVERVIEW.md` | Plugin description, pipeline, formats, automation pathways, installation |
| `UI_GUIDE.md` | Every dialog parameter with values and notes |
| `UI_WORKFLOW_STITCHING.md` | Step-by-step GUI walkthrough for tile stitching |
| `GROOVY_SCRIPT_API.md` | Full IJ.run() API reference with all pipeline commands |
| `WORKFLOW_TILE_STITCHING.groovy` | Ready-to-run Groovy pipeline script (Fiji Script Editor) |
| `SKILL.md` | This quick-reference card |
