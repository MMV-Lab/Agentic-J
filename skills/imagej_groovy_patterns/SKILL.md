---
name: imagej_groovy_patterns
description: Index of recurring Groovy / ImageJ coding pitfalls and their canonical fixes. Each entry below points to ONE small markdown file in this folder — read only the file(s) whose symptom or topic matches your script. Do not read every entry. The imagej_coder reads the matching file before writing a script that touches the topic; the imagej_debugger searches by symptom string when a script fails. Add new pitfalls as new files; never inline them into agent prompts.
---

# ImageJ Groovy Patterns & Pitfalls — Index

**Reading rule:** scan the table below, then `smart_file_reader` ONLY the
file(s) whose Topic or Symptom matches your script. Do not read the whole
folder.

| File | Topic | Symptom (debugger search key) |
|------|-------|-------------------------------|
| [`pitfall_thresholding_direction.md`](pitfall_thresholding_direction.md) | `IJ.setAutoThreshold` direction (`" dark"` suffix) | inverted mask / 0 objects / mask fills frame |
| [`pitfall_rgb_vs_multichannel.md`](pitfall_rgb_vs_multichannel.md) | RGB vs composite — `getNChannels()` lies for RGB | `getNChannels() == 1` for an RGB image; only red band processed |
| [`pitfall_image_calculator_import.md`](pitfall_image_calculator_import.md) | `ImageCalculator` arithmetic | `unable to resolve class ImageCalculator` |
| [`pitfall_common_imports.md`](pitfall_common_imports.md) | Other commonly-missed `ij.plugin.*` / `ij.measure.*` imports | `unable to resolve class <X>` for `Duplicator`, `RoiManager`, `ResultsTable`, `Measurements`, `ChannelSplitter`, `WindowManager` |
| [`pitfall_z_vs_t_dimensions.md`](pitfall_z_vs_t_dimensions.md) | Image-sequence planes loaded as Z instead of T (time) | `Image must be 2D over time, got an image with multiple Z` (TrackMate); `getNFrames() == 1` on a timelapse |
| [`pitfall_lut_on_rgb.md`](pitfall_lut_on_rgb.md) | Applying a LUT to a 24-bit RGB image | `LUTs cannot be assigned to RGB Images.`; `Macro canceled` after `RGB Color` followed by a LUT command |

---

## Adding a new pitfall

1. Create `pitfall_<short_topic>.md` in this folder using the template below.
2. Append one row to the Index table — Topic + Symptom keywords matter most;
   the debugger searches the Symptom column.
3. Do NOT update agent prompts. The prompts already point at this index.

### Template (`pitfall_<short_topic>.md`)

```markdown
# <One-line title>

**Symptom:** <what the user sees in logs / output>

**Cause:** <one-paragraph explanation, ideally citing the API quirk>

**Fix:**
\`\`\`groovy
<minimal copy-pasteable snippet>
\`\`\`

<optional 1–2 lines of caveats / when-not-to-apply>
```
