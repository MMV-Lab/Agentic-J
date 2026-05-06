# LUTs cannot be applied to RGB images

**Symptom:**
- `LUTs cannot be assigned to RGB Images.`
- Macro / Groovy script aborts with `Macro canceled`.

**Cause:** A LUT (look-up table — `Red`, `Green`, `Fire`, `glasbey`, …) is a
colormap that maps single-channel intensity values to display colors. It can
only be applied to a grayscale image (8/16/32-bit). A 24-bit RGB image already
encodes color in three channels, so there is nothing for a LUT to map; Fiji
refuses the operation outright.

The mistake usually appears in preview/overlay code:

```groovy
IJ.run(maskImp, "RGB Color", "")           // 1. converts to 24-bit RGB
IJ.run(maskImp, "Red", "")                 // 2. applies LUT — fails here
```

**Fix A — drop the LUT step; use an Overlay instead (recommended for masks):**

```groovy
import ij.gui.ImageRoi
import ij.gui.Overlay

// Keep the mask 8-bit binary (0/255). Add it as a coloured, semi-transparent
// overlay on top of the original — no RGB conversion, no LUT on the original.
def overlay = new Overlay()
def roi = new ImageRoi(0, 0, maskImp.getProcessor())
roi.setOpacity(0.5)
roi.setZeroTransparent(true)               // background pixels fully transparent
overlay.add(roi)
originalImp.setOverlay(overlay)
```

`ImageRoi` accepts a `LUT` via `roi.setProcessor(maskWithLut.getProcessor())`
if you want a coloured mask — apply the LUT to the GRAYSCALE mask first, then
hand its processor to the `ImageRoi`.

**Fix B — apply the LUT BEFORE converting to RGB:**

```groovy
IJ.run(maskImp, "Red", "")                 // 1. LUT on the still-grayscale image
IJ.run(maskImp, "RGB Color", "")           // 2. flatten to RGB only after
```

Use this when you actually need a flat RGB output (e.g. saving a coloured
preview PNG). For interactive overlay, prefer Fix A — the original image
stays editable and the mask remains independent.

**Detect the problem before triggering it:**

```groovy
if (imp.getType() != ImagePlus.COLOR_RGB) {
    IJ.run(imp, "Red", "")                 // safe — grayscale
} else {
    IJ.log('[SKIP] Image is RGB; LUT not applicable.')
}
```
