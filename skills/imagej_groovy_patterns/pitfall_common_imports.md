# Other commonly-missed imports

**Symptom:** `unable to resolve class <X>` at compile time.

**Cause:** Groovy does not auto-import `ij.plugin.*` or `ij.measure.*`
classes. Each used class needs its own `import` line.

**Fix — add the matching import:**

| Class | Import |
|-------|--------|
| `Duplicator` | `import ij.plugin.Duplicator` |
| `ChannelSplitter` | `import ij.plugin.ChannelSplitter` |
| `RoiManager` | `import ij.plugin.frame.RoiManager` |
| `ResultsTable` | `import ij.measure.ResultsTable` |
| `Measurements` | `import ij.measure.Measurements` |
| `WindowManager` | `import ij.WindowManager` |

If a `pitfall_<class>_import.md` already exists for a specific class
(e.g. `pitfall_image_calculator_import.md`), prefer that file — it has
the no-import string-form alternative as well.
