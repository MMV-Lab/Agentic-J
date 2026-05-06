# `IJ.setAutoThreshold` direction — never hardcode `" dark"`

**Symptom:** mask is inverted; downstream measurements report 0 objects or
the mask fills the entire frame.

**Cause:** `IJ.setAutoThreshold(imp, "Otsu dark")` and
`IJ.setAutoThreshold(imp, "Otsu")` produce **opposite** masks. The `" dark"`
suffix means "background is dark" → foreground = bright pixels above the
threshold. Without it, foreground = dark pixels below the threshold.

| Image type | Suffix |
|------------|--------|
| Fluorescence (bright signal on black BG) | `"Otsu dark"` |
| Brightfield / H&E / phase-contrast (dark cells on bright BG) | `"Otsu"` |

**Fix — pick the suffix at runtime from image stats:**

```groovy
def s = imp.getStatistics()
def darkBg = s.median <= (s.min + s.max) / 2.0
IJ.setAutoThreshold(imp, "Otsu" + (darkBg ? " dark" : ""))
IJ.run(imp, "Convert to Mask", "")
```

If PROJECT STATE includes `background_mode` (`"dark"` / `"bright"`), prefer
that over the runtime check — it was computed from the full image, not the
active slice.
