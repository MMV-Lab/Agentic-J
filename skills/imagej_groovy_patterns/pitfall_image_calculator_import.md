# `ImageCalculator` — easy-to-forget import

**Symptom:** `unable to resolve class ImageCalculator` at compile time.

**Cause:** `ImageCalculator` is in `ij.plugin` and is NOT auto-imported by
the Groovy script runner.

**Fix A — add the import:**

```groovy
import ij.plugin.ImageCalculator
def ic = new ImageCalculator()
def diff = ic.run("Subtract create", impA, impB)
```

**Fix B — use the no-import string form (GUI sessions only):**

```groovy
IJ.run(impA, "Image Calculator...",
       "image1=" + impA.getTitle() +
       " operation=Subtract image2=" + impB.getTitle() +
       " create")
def diff = IJ.getImage()
```

Fix B depends on window titles and on the result becoming the active image.
It does not work headless. With images that were never shown it fails with
`Macro canceled`. After `show()` on both inputs, `IJ.getImage()` returns an
input image, not the result. Use Fix A in scripts.
