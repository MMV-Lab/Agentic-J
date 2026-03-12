# BigStitcher Skill

BigStitcher is a Fiji workflow plugin for aligning and fusing very large multi-tile and multi-view microscopy datasets (commonly light-sheet). In scripting contexts, the most reliable automation path is to use the plugin’s macro-recordable **Batch Processing** commands, then adapt recorded parameter strings for your dataset. In this environment, BigStitcher is currently not installed, so this skill includes an installation note plus a validated preflight Groovy template that safely checks command availability and logs outcomes.

## Quick command reference

| Command string | Purpose |
|---|---|
| `"Define dataset ..."` | Import/build BigStitcher dataset project |
| `"Calculate pairwise shifts ..."` | Compute pairwise tile/view translations |
| `"Filter pairwise shifts ..."` | Remove weak/implausible links |
| `"Optimize globally and apply shifts ..."` | Solve global transforms and apply |
| `"Fuse dataset ..."` | Export fused output image(s) |

## 3 common pitfalls (and prevention)
1. **Exact command/parameter tokens are brittle**  
   Use Macro Recorder to generate the exact token string first; then modify only paths/values.
2. **Bad import pattern or voxel metadata**  
   Validate filename parsing and voxel size before stitching to avoid geometric mismatch.
3. **Assuming plugin exists in every Fiji install**  
   Verify installation via updater and menu presence before running scripts.

## File map
- `OVERVIEW.md` — capabilities, inputs/outputs, installation, citation.
- `GROOVY_API.md` — evidence-backed command strings and known parameters.
- `UI_GUIDE.md` — full GUI checklist workflow with expected outputs.
- `GROOVY_WORKFLOW.groovy` — tested preflight + batch template script.
