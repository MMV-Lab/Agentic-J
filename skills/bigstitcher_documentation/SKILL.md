---
name: bigstitcher_documentation
description: A Fiji plugin for stitching and fusing multi-tile, multi-angle, multi-TB microscopy datasets.Stores all state in an XML project file; uses BigDataViewer for interactive display. Primary use cases are cleared-tissue lightsheet stitching, tiled confocal reconstruction, multi-view lightsheet registration. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---


# BigStitcher — Skill Quick Reference

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
// NOTE: In many BigStitcher versions the fusion command is recorded as "Image Fusion" (not "Fuse dataset ...").
// Always confirm the exact command name via Plugins › Macros › Record…
IJ.run("Image Fusion", "select=/path/to/dataset.xml ...")
```

Use the **Macro Recorder** (`Plugins › Macros › Record…`) to capture exact
parameter strings while working interactively — then paste them into your
Groovy script.

---

## Processing Pipeline (Stitching Mode)

```
Step 1 — Define dataset         →  IJ.run("Define Multi-View Dataset") *(or similar; command name is version-dependent — use Macro Recorder)*
Step 2 — Calculate pairwise shifts  →  IJ.run("Calculate pairwise shifts ...")
Step 3 — Filter links               →  IJ.run("Filter pairwise shifts ...")
Step 4 — Global optimization        →  IJ.run("Optimize globally and apply shifts ...")
Step 5 — ICP refinement (optional)  →  IJ.run("ICP Refinement ...")
Step 6 — Fuse / Image Fusion         →  IJ.run("Image Fusion")  *(command name depends on BigStitcher version; use Macro Recorder)*
```

All steps are fully automatable via `IJ.run()`. Each call is synchronous and
operates on the shared XML project file.

---

## Key Parameters (All Steps)

| Parameter | Typical value | Notes |
|---|---|---|
| `GRID_TYPE` | `[Snake: Right & Down      ]` | **6 trailing spaces required** — use Macro Recorder if changing this |
| `tiles_x`, `tiles_y` | dataset-specific | From acquisition settings |
| `overlap_x_(%)` | `10` | Match your acquisition overlap |
| `downsample_in_x/y/z` | `2` | Use `4` for faster/coarser result |
| `min_r` | `0.7` | Cross-correlation threshold for link filtering |
| `global_optimization_strategy` | `Two-Round using metadata to align unconnected Tiles` *(exact capitalization varies by BigStitcher version)* | Always copy exactly from the Macro Recorder dropdown (**case/spacing sensitive**). In Fiji 2.16.0/1.54p (Java 21) we observed 5 valid strings: `One-Round`; `One-Round with iterative dropping of bad links`; `Two-Round using metadata to align unconnected Tiles`; `Two-Round using Metadata to align unconnected Tiles and iterative dropping of bad links`; `NO global optimization, just store the corresponding interest points`. |
| `fix_group_0-0,` | always | Trailing comma required |
| `pixel_type` in Fuse | `16-bit unsigned integer` | For fluorescence data |

---

## Critical Pitfalls

1. **`grid_type` trailing spaces cause "unrecognized command"** — this is the
   most common failure with Define Dataset. The value `[Snake: Right & Down      ]`
   has exactly 6 trailing spaces. Missing even one produces a silent mismatch.
   Use the Macro Recorder once to capture the exact value for your scan direction.
2. **Trailing comma in `fix_group_0-0,`** — required; missing it breaks the
   global optimization reference frame.
3. **Re-save to a different path than input** — writing HDF5 into the same
   folder as raw files is allowed but can cause confusion; use a subdirectory.
4. **Fusion before optimization** — fusing with unregistered positions produces
   a broken output. Always run optimize → (ICP) → fuse in order.
5. **ICP requires sufficient shared signal** — if tiles share little overlap
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