---
name: coloc2_documentation
description: Coloc 2 is the standard Fiji plugin for pixel-based colocalization analysis. It implements validated algorithms including Pearson’s, Manders’ (with and without threshold), Costes’ significance test, and Li’s ICQ. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls.
---

### Documentation Files
- [OVERVIEW.md](./OVERVIEW.md): Biological context and metric definitions.
- [GROOVY_API.md](./GROOVY_API.md): Strict parameter syntax for headless execution.
- [GROOVY_WORKFLOW.groovy](./GROOVY_WORKFLOW.groovy): Production-ready script template.
- [BATCH_MEMORY.md](./BATCH_MEMORY.md): **Read before writing any batch loop.** Coloc 2 leaks one
  full result window (both source images + all derived images) per run; the heap fills until the
  JVM dies. Contains the cause and the `disposeColoc2ResultWindows()` fix.
- [UI_GUIDE.md](./UI_GUIDE.md): Menu navigation and parameter descriptions.
- [UI_WORKFLOW.md](./UI_WORKFLOW.md): Manual verification and result interpretation.

### Verified Against
The macro parameter syntax in `GROOVY_API.md` / `GROOVY_WORKFLOW.groovy` (bare-key checkboxes,
e.g. `spearman's_rank_correlation`, not `statistic_5=true`) was confirmed by decompiling the
plugin dialog **and** by a live Coloc 2 run on this exact stack:

| Component | Version |
|:---|:---|
| Coloc 2 plugin (`Colocalisation_Analysis`) | **3.1.0** |
| ImageJ 1.x (`ij`) | **1.54p** |
| Fiji / imagej2 | **2.17.1-SNAPSHOT / 2.16.0** (`ij.getVersion()` → `2.16.0/1.54p`) |
| Java | **OpenJDK 21.0.10-internal** |
| Groovy | **4.0.23** |

Matches `data/environment/container_snapshot.md`. ImageJ's macro parser silently ignores unknown
keys, so if a future Coloc 2 update renames a checkbox label, re-verify by decompiling
`addCheckbox(...)` labels in `Coloc_2.class` (or recording a macro from the GUI) — do not assume.