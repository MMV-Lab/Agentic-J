# Coloc 2 in Batch — the RAM Leak and How to Fix It

## Symptom
A loop over many images (`for each image: IJ.run('Coloc 2', ...)`) makes heap usage climb
monotonically until the JVM thrashes or throws `OutOfMemoryError`. Closing the Coloc 2 result
windows by hand makes the RAM drop again.

## Root cause (verified by decompiling `Colocalisation_Analysis-3.1.0.jar`)
`Coloc_2.colocalise(...)` contains:

```java
boolean headless = Boolean.getBoolean("java.awt.headless");
SingleWindowDisplay swDisplay = headless ? null
                              : new SingleWindowDisplay(dataContainer, pdfWriter);
...
if (swDisplay != null) {
    swDisplay.process();
    swDisplay.addWindowListener(new WindowAdapter() {          // Coloc_2$2
        public void windowClosing(WindowEvent e) {
            WindowManager.removeWindow(swDisplay);
            swDisplay.dispose();
            swDisplay.removeWindowListener(this);
        }
    });
    WindowManager.addWindow(swDisplay);
}
```

Two facts follow:

1. **The result window is created on every run whenever the JVM is not headless.**
   It is *not* gated by the `display_images_in_result` checkbox — that flag only sets
   `SingleWindowDisplay.displayOriginalImages` on the already-constructed frame.
   Omitting the checkbox does **not** stop the window from being built.

2. **The only code path that frees it is `windowClosing`, which fires only on a human click.**
   The frame is a `JFrame` registered in `ij.WindowManager`, and it strongly retains:
   - `dataContainer` — both source images, the mask, and the Costes shuffled data,
   - `pdfWriter` — which holds the same `DataContainer` again,
   - `listOfImages` — every result image (scatterplot, Costes mask, regression plots),
   - `mapOf2DHistograms` — the 2D histograms.

   So each batch iteration pins one complete copy of both input channels plus all derived
   images for the lifetime of the JVM. That is the leak, and it is why manual closing helps.

## Fix: dispose the result window after every run
Do exactly what `windowClosing` does, programmatically, at the end of each loop iteration.

```groovy
import ij.IJ
import ij.WindowManager
import java.awt.Frame

/**
 * Close and dispose every Coloc 2 result window (SingleWindowDisplay).
 * Call once after each IJ.run('Coloc 2', ...) in a batch loop.
 * Returns the number of windows disposed.
 */
int disposeColoc2ResultWindows() {
    int n = 0
    // Frame.getFrames() is used rather than WindowManager.getNonImageWindows() because
    // it also catches frames that failed to register, and it never returns null.
    for (Frame f : Frame.getFrames()) {
        if (f == null) continue
        if (!f.getClass().getName().startsWith('sc.fiji.coloc.results.SingleWindowDisplay')) continue
        // getFrames() keeps returning already-disposed frames until they are collected,
        // so skip those or the count is misleading.
        if (!f.isDisplayable()) continue
        try {
            WindowManager.removeWindow(f)   // drop ImageJ's strong reference
        } catch (Exception ignored) {
        }
        f.setVisible(false)
        f.dispose()                         // release native peer + AWT's reference
        n++
    }
    return n
}
```

Use it like this:

```groovy
for (File imageFile : imageFiles) {
    // ... open, split, run ...
    IJ.run('Coloc 2', args)

    // ... harvest results from IJ.getLog() / ResultsTable BEFORE cleanup ...

    disposeColoc2ResultWindows()

    // also close the images this iteration opened
    IJ.run('Close All', '')
    IJ.freeMemory()          // hint the GC; optional but useful for long batches
}
```

**Order matters:** harvest the numbers first, dispose second. `dispose()` tears down the frame
that renders the results.

`IJ.freeMemory()` is only a `System.gc()` hint — it is not required for correctness, but on
long batches it makes the heap curve flat instead of sawtoothed, which makes it obvious the
fix is working.

## Alternative: make the window never exist
If the run genuinely needs no GUI, set the property Coloc 2 reads before invoking it:

```groovy
System.setProperty('java.awt.headless', 'true')
IJ.run('Coloc 2', args)
```

Coloc 2 calls `Boolean.getBoolean("java.awt.headless")` fresh on each run (not
`GraphicsEnvironment.isHeadless()`, which is cached at first AWT use), so flipping the property
at runtime does suppress the window without re-initialising AWT.

Two caveats:
- **Never combine this with `display_images_in_result`.** In the headless branch `swDisplay`
  is `null`, but the `displayImages` code path dereferences it unconditionally
  (`swDisplay.displayOriginalImages = true`) → `NullPointerException`.
- The property is global. Other plugins in the same JVM may consult it and change behaviour.

For a GUI-driven Fiji (the normal case here), prefer `disposeColoc2ResultWindows()` — it is
local, has no side effects on other plugins, and keeps the window visible long enough to be
screenshotted if desired.

## Measured on this stack
5 Coloc 2 runs on 384×384 16-bit pairs, Fiji GUI on `DISPLAY=:1`, heap sampled after
`System.gc()` (`skills/coloc2_documentation` test, Coloc 2 3.1.0 / IJ 1.54p / Java 21):

| iteration | without fix | live result windows | with fix | live result windows |
|:--|:--|:--|:--|:--|
| baseline | 81 MB | 0 | 91 MB | 0 |
| 0 | 88 MB | 1 | 91 MB | 0 |
| 1 | 92 MB | 2 | 91 MB | 0 |
| 2 | 93 MB | 3 | 91 MB | 0 |
| 3 | 95 MB | 4 | 91 MB | 0 |
| 4 | 96 MB | 5 | 91 MB | 0 |

Without the fix the window count rises by exactly one per run and the heap rises with it.
With the fix the heap is flat. The retained bytes scale with input size, so on real
multi-megapixel stacks the same curve fills several GB in a few dozen iterations.

## Not the cause
- `show_save_pdf_dialog` — this blocks the loop waiting for a human, but does not leak.
- `display_images_in_result` — costs a little extra work per run, but omitting it does not
  prevent the window or the retention.
- Leaving `ImagePlus` windows open — a real but much smaller leak, fixed by `Close All`.
  If RAM still climbs after disposing the Coloc 2 windows, check for un-closed split channels.
