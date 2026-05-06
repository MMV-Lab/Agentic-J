# Slices loaded as Z when they should be T (time)

**Symptom:**
- `[cellposeDetector] Image must be 2D over time, got an image with multiple Z.`
- TrackMate / TrackMate-Cellpose / TrackMate-StarDist refuses to run on the stack.
- Time-series operations (kymograph, plot Z-axis profile of intensity over time)
  return Z-axis data instead of time.

**Cause:** When ImageJ loads an image sequence (`File › Import › Image Sequence`)
or a multi-page TIFF/JPG stack, every plane is assigned to **Z** by default,
not **T**. So `imp.getNSlices() == N` but `imp.getNFrames() == 1` — TrackMate
(and any 2D+T plugin) sees this as a 3D z-stack and rejects it.

**Fix — force `C=1, Z=1, T=N` before any time-series plugin:**

```groovy
// imp loaded from File.Import.ImageSequence or BF — all planes currently in Z
def n = imp.getStackSize()
if (imp.getNFrames() == 1 && imp.getNSlices() > 1) {
    IJ.run(imp, "Properties...",
           "channels=1 slices=1 frames=" + n +
           " unit=pixel pixel_width=1 pixel_height=1 voxel_depth=1")
}
// Equivalent menu path: Image › Properties… (set Frames=N, Slices=1)
```

For multi-channel sequences, also use `Image › Hyperstacks › Stack to Hyperstack…`:

```groovy
IJ.run(imp, "Stack to Hyperstack...",
       "order=xyczt(default) channels=" + nC +
       " slices=1 frames=" + nT + " display=Composite")
```

**When loading via Bio-Formats**, set the time axis at import so this fix is
unnecessary:

```groovy
options.setSwapDimensions(true)
options.setInputOrder(0, "XYTCZ")     // tell BF planes are along T, not Z
```

**Caveat — the inverse mistake is also possible.** A z-stack opened as a movie
(every plane assigned to T) breaks 3D plugins the same way. Same `Properties…`
call swapped (`slices=N frames=1`) is the fix; don't blindly assume "always T".
Decide from the source: image sequence / `.avi` / `.mp4` → T;
`.czi` / `.lif` volume / `.lsm` → Z.
