# TrackMate — GUI WORKFLOW: Automated Particle Tracking

## Purpose
A complete, step-by-step GUI walkthrough for tracking fluorescent spots (nuclei, vesicles,
particles) in a 2D timelapse image using the LoG detector and the Simple LAP tracker.

This workflow is suitable for biologists without scripting experience.

---

## Test Image

Use the built-in sample:
**File ▶ Open Samples ▶ Tracks for TrackMate (807K)**

This is a 128×128 pixel, 50-frame 2D timelapse with 2–4 fluorescent spots per frame.
There are gap-closing, splitting, and merging events. Pixel calibration is 1 pixel = 1 pixel
(dummy values — units are in pixels).

---

## Prerequisites

- Fiji with TrackMate (included in core Fiji)
- A 2D+T fluorescence image (grayscale, TIFF or any Fiji-supported format)
- Image opened and selected in Fiji before starting

---

## Step 1 — Open the Image and Verify Calibration

1. Open your image: **File ▶ Open** (or use the sample above).
2. Check it has the right dimensions: **Image ▶ Properties** (Shift+P).
   - Make sure the number of time frames is > 1 and is shown as **Frames**, not Slices.
   - If the image loaded as a Z-stack (Slices = N, Frames = 1), swap them here.
   - Set the pixel size and frame interval if known (e.g. Pixel width = 0.5 µm, Frame interval = 5 s).
3. Click **OK** in Properties.

**Windows after this step:** one image window.

---

## Step 2 — Launch TrackMate

Menu: **Plugins ▶ Tracking ▶ TrackMate**

The **Start panel** opens next to the image.

Check:
- The image name is correct
- Pixel width, height, and time interval match your data
- Dimensionality: "2D time-lapse of N frames"

If anything is wrong, press **Refresh source** after fixing it in Image ▶ Properties.

Click **Next ▶**

---

## Step 3 — Select Detector

From the dropdown, choose: **LoG detector**
(Use **DoG detector** for large images where speed matters.)

Click **Next ▶**

---

## Step 4 — Configure the LoG Detector

| Parameter | Recommended starting value | Explanation |
|-----------|--------------------------|------------|
| Target channel | `1` | Use channel 1 (only channel for grayscale) |
| Estimated blob radius | `2.5` µm (or pixels if uncalibrated) | Match to actual object radius — inspect image to estimate |
| Quality threshold | `0` | Keep all spots for now; filter later |
| Sub-pixel localisation | ✓ (on) | Improves position accuracy |
| Median pre-filter | off | Only enable if image is very noisy |

**Press Preview** to see detected spots on the current frame as yellow circles.
- If circles are too small: increase radius
- If too few spots detected: lower the quality threshold
- If the circles look right: click **Next ▶** to run on all frames

---

## Step 5 — Detection (automatic)

TrackMate detects spots in all frames. Wait for the progress bar to complete.

Expected Log output:
```
Starting detection process using N threads.
Found XXXX spots.
Starting initial filtering process.
Computing spot features.
```

**Inspect:** Scroll through frames with the image slider. Spots appear as circles overlaid
on the image. At this stage there will likely be false positives.

Click **Next ▶**

---

## Step 6 — Spot Filtering (post-detection)

TrackMate versions differ slightly in how spot filtering is presented:

- In some versions you first see an **Initial Spot Filter** with a **QUALITY histogram** slider.
- In other versions you may see a **feature-based filter panel** immediately (an interface with an **Add filter (+)** button and options like "color spots by: Uniform color").

In either case, the goal is the same: remove obvious false-positive detections.

### Option A — Initial Spot Filter (Quality histogram)
If you see a histogram of quality values:

1. Drag the threshold slider to the first distinct **valley** in the histogram.
   For the sample image, a value around 30–50 is a good starting point.
2. The count display shows how many spots are kept.
3. Check the image: circles on real spots should remain; background noise circles should disappear.

### Option B — Spot Filtering (Feature-based)
If you see an **Add filter (+)** interface:

**Common useful filters:**
- **QUALITY above 30** — keep only high-confidence detections
- **SNR above 1.5** — remove spots with very low contrast
- **MEAN_INTENSITY above [background]** — remove very dim spots

To add a filter:
1. Click the **+** button
2. Choose the feature (e.g. QUALITY)
3. Set value (e.g. 30) and direction (Above)
4. The image updates live

For the sample image: leave this panel empty or add QUALITY > 30.

Click **Next ▶**

---

## Step 7 — Select Tracker

Choose: **Simple LAP tracker**

This tracker links spots frame-by-frame using minimum-cost assignment. It does not
allow gap closing, splits, or merges — use the full **LAP tracker** if you need those.

Click **Next ▶**

---

## Step 8 — Configure the Simple LAP Tracker

| Parameter | Recommended value | Explanation |
|-----------|-----------------|------------|
| **Linking max distance** | 5–15 µm (or pixels) | Maximum distance a spot can travel between consecutive frames. Set this slightly above the largest expected displacement between frames. |

> **How to estimate linking distance:** Find two spots that represent the same object in
> consecutive frames, and measure the distance between them (hold Shift+click on two spots
> to see coordinates in the Results bar). Multiply by 1.5 as a safety margin.

Click **Next ▶** to run tracking.

---

## Step 9 — Tracking (automatic)

TrackMate links spots and builds tracks. The Log shows the number of tracks found.

Expected output: overlapping coloured track lines appearing on the image.

Click **Next ▶**

---

## Step 10 — Track Filtering

Optional. Add filters to remove short or uninteresting tracks.

**Common useful filters:**
- **NUMBER_SPOTS above 5** — remove very short stub tracks (missed detections from noise)
- **TRACK_DISPLACEMENT above 10** — remove immobile particles if you care only about moving cells

For the sample image: add NUMBER_SPOTS > 3.

Click **Next ▶**

---

## Step 11 — Display options / Select View

Some TrackMate versions show the **display options** after tracking/track filtering.

Choose: **HyperStack displayer** (default)

Click **Next ▶**

---

## Step 12 — Inspect and Export Results

You are now on the final **Actions** panel.

### Visual inspection
- Browse frames with the slider — coloured track lines and spot circles are overlaid
- Open **TrackScheme**: click the TrackScheme button — shows a timeline of all tracks;
  each row is one track, columns are frames

### Export tables
1. In the Actions dropdown, select **Export statistics to IJ tables**
2. Click **Execute**
3. Three Results tables open:
   - **Spots** — one row per detected spot: X, Y, Z, T, QUALITY, MEAN_INTENSITY, RADIUS
   - **Edges** — one row per link: VELOCITY, DISPLACEMENT, source/target spot IDs
   - **Tracks** — one row per track: TRACK_DURATION, TRACK_DISPLACEMENT, TRACK_MEAN_SPEED, NUMBER_SPOTS

4. Save each table: **File ▶ Save As...** in the Results window → CSV

### Create a tracking video
1. In the Actions dropdown, select **Capture overlay**
2. Click **Execute**
3. Set start frame = 1, end frame = last frame
4. A new image opens with the overlay burned in → save with **File ▶ Save As ▶ AVI** or TIFF

### Save the TrackMate session
Click the **Save** button → choose a `.xml` filename.
This XML file stores all spots, tracks, settings, and the path to the source image.
You can reload it later with **Plugins ▶ Tracking ▶ Load a TrackMate file**.

---

## Step 13 — Manual Correction (Optional)

Select the **TrackMate tool** in the Fiji toolbar.

To **add a missed spot:** press `A` at the spot location in the image
To **delete a false spot:** press `D` or `Delete` while the cursor is over the spot
To **create a link:** Shift+Click on spot 1, then Shift+Click on spot 2, then press `L`
To **delete a link:** Alt+Click on the connecting line in the image

Changes are reflected immediately in TrackScheme.

---

## Parameter Tuning Reference

| Observation | Likely cause | Fix |
|-------------|-------------|-----|
| Too many detected spots | Radius too small or quality too low | Increase radius or quality threshold |
| Real spots not detected | Radius too large, or quality too high | Decrease radius; set quality to 0 then re-filter |
| Tracks broken into short pieces | Linking distance too small, or gap closing needed | Increase linking distance; switch to LAP tracker with gap closing |
| One track per frame (no linking) | Spots too far apart between frames | Increase linking distance |
| Tracks cross and switch identity | Linking distance too large relative to particle density | Decrease linking distance |
| Tracks too short / long | Track filter threshold wrong | Adjust NUMBER_SPOTS filter |

---

## Windows / Tables After Completion

| Window | Contents |
|--------|---------|
| Image window | Original image with track overlay |
| TrackScheme | Timeline lineage graph |
| Results: Spots | Per-spot measurements |
| Results: Edges | Per-link velocity and displacement |
| Results: Tracks | Per-track statistics |
| (Optional) overlay video | Burned-in track overlay for export |
