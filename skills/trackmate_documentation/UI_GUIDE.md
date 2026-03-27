# TrackMate — GUI REFERENCE

This document covers every panel and control in the TrackMate wizard GUI.
Use it to understand what each setting does when running TrackMate interactively.

Launch: **Plugins ▶ Tracking ▶ TrackMate** (with a timelapse image open and selected).

---

## Navigation Buttons (always visible at the bottom)

| Button | Action |
|--------|--------|
| **Next ▶** | Advance to the next step; may trigger detection/tracking |
| **◀ Previous** | Go back one step without re-running computations |
| **Save** | Write the current session (model + settings) to an XML file |
| Log (toggle) | Show/hide the Log window with verbose output |
| Display settings (toggle) | Show/hide the display settings window for overlay colours |

> **Important:** Going back to the detector panel and pressing Next **re-runs detection**.
> Going back to the tracker panel and pressing Next **re-runs tracking** only.
> You can save at any time, even before tracking.

---

## Panel 1 — Start

**Purpose:** Verify the source image and its spatial/temporal calibration.

| Field | What it means |
|-------|--------------|
| Image name | The Fiji image that will be analysed |
| Pixel width / height | Spatial calibration (μm or other unit) |
| Voxel depth | Z spacing for 3D images |
| Time interval | Frame interval in physical units (s, min, etc.) |
| Spatial unit | Physical unit string (e.g. `µm`) |
| Time unit | Time unit string (e.g. `sec`) |
| **Refresh source** | Re-reads metadata from the image and reloads any drawn ROI |

> **Biologist tip:** If the calibration is wrong, fix it now with **Image ▶ Properties** (Shift+P)
> and then press Refresh source. All downstream distance parameters use physical units.
> A common mistake: the image loaded as a Z-stack instead of a timelapse. Correct this
> with Image ▶ Properties before pressing Next.

**ROI support:** Draw any closed ROI on the image before pressing Refresh source. TrackMate
will detect objects only within that region.

---

## Panel 2 — Select a Detector

**Purpose:** Choose the algorithm that will find objects in each frame.

| Detector | Use for |
|---------|---------|
| **LoG detector** | Well-separated round fluorescent spots; best accuracy |
| **DoG detector** | Same as LoG, faster; good for large images |
| **Mask detector** | Binary mask channel (pixels > 0 are objects) |
| **Threshold detector** | Intensity threshold on a grayscale channel |
| **Label image detector** | Integer label image channel (each label = one object) |
| **Manual detector** | No auto-detection; all spots placed manually |

Extended detectors (require additional update sites):
`StarDist detector`, `Cellpose detector`, `MorphoLibJ detector`, `Ilastik detector`, `Weka detector`

---

## Panel 3 — Detector Configuration

Settings depend on the chosen detector.

### LoG / DoG Detector
| Parameter | Description |
|-----------|------------|
| **Target channel** | Channel index (1-based) containing the signal |
| **Estimated blob radius** | Expected object radius in **physical units** (μm) — this is the single most important parameter |
| **Quality threshold** | Minimum LoG response to accept a spot; set to 0 to keep everything initially |
| **Sub-pixel localisation** | Refine spot position to sub-pixel accuracy (recommended: on) |
| **Median pre-filter** | Apply 3×3 median before detection (helps with salt-and-pepper noise) |
| **Preview** | Shows detected spots overlaid on the current frame; adjust radius/threshold in real time |

> **Biologist tip:** Start with Quality threshold = 0 (detect everything), look at the count
> shown after detection, then set the initial quality filter on Panel 5 to eliminate the worst
> spots. Leave the radius slightly larger than the actual object — it is more forgiving.

### Threshold Detector (v7+)
| Parameter | Description |
|-----------|------------|
| **Target channel** | Channel to segment |
| **Intensity threshold** | Pixel value cutoff; use "Auto" to let TrackMate suggest one |
| **Simplify contours** | Smooth polygon contours (recommended: on) |

### Label Image Detector (v7+)
| Parameter | Description |
|-----------|------------|
| **Target channel** | Channel containing the label image (integer values per object) |
| **Simplify contours** | Smooth polygon contours |

> A label image must be provided as a separate channel in your multi-channel image.
> Each object must have a unique integer pixel value; background must be 0.

---

## Panel 4 — Detection Progress

Displays a progress bar while detection runs on all frames. The Log window shows:
- Number of frames processed
- Number of spots found per frame
- Total spots found

After detection, the spots appear as circles overlaid on the image.
Use the **HyperStack slider** to browse frames and inspect detections visually.

---

## Panel 5 — Initial Spot Filter

**Purpose:** Apply a single quality threshold to quickly discard obviously bad spots.
This is a coarse global filter applied before feature computation.

| Control | Description |
|---------|-------------|
| Quality histogram | Shows the distribution of quality values across all detected spots |
| Threshold slider | Drag to set the quality cutoff; spots below this value are discarded |
| Count display | Number of spots above (kept) and below (discarded) the threshold |

> **Tip:** Set this low enough to keep all potentially real spots — you can filter more
> precisely in Panel 7. A typical good value is anywhere from the first valley in the
> quality histogram to about 30–50% of the histogram range.

---

## Panel 6 — Select a View

**Purpose:** Choose how tracking results will be displayed.

| View | Description |
|------|-------------|
| **HyperStack displayer** | Default. Overlays circles/polygons and track lines on the image |
| **3D viewer** | Launches the ImageJ 3D viewer for volumetric display |

The HyperStack displayer is the standard choice for nearly all workflows.

---

## Panel 7 — Spot Filtering

**Purpose:** Filter detected spots by any computed feature to retain only true objects.
This is more selective than the initial quality filter in Panel 5.

**Available features for filtering:**
- QUALITY (detection confidence)
- POSITION_X, POSITION_Y, POSITION_Z (location)
- RADIUS (estimated size)
- MEAN_INTENSITY, MAX_INTENSITY, MIN_INTENSITY
- CONTRAST, SNR (signal-to-noise ratio)
- ESTIMATED_DIAMETER

**Adding a filter:**
1. Click the **+** button to add a new filter row
2. Choose the feature from the dropdown
3. Set the threshold value — choose **Above** or **Below**
4. The image overlay updates live to show which spots pass

> **Biologist tip:** Use QUALITY > 30 (or above the valley in the distribution) to remove
> low-confidence detections. Use CONTRAST or SNR to eliminate spots in background regions.
> Always visually inspect the result at several frames before proceeding.

---

## Panel 8 — Select a Tracker

**Purpose:** Choose the algorithm to link spots across frames into tracks.

| Tracker | Best for |
|---------|---------|
| **Simple LAP tracker** | Brownian motion; no gap closing, splits, or merges; fewest parameters |
| **LAP tracker** | Brownian motion + gap closing + splits + merges; most flexible |
| **Kalman tracker** | Linear/directed motion (constant velocity); good for fast-moving objects |
| **Nearest-neighbour tracker** | Minimal setup; not recommended for dense fields |
| **Overlap tracker** | Shape-based tracking; requires v7 contour objects |
| **Manual tracker** | Skip automated linking; assign links manually |

> **Biologist tip:** Start with the Simple LAP tracker. Only switch to the full LAP tracker
> if you need gap closing (missed detections) or want to detect cell divisions.

---

## Panel 9 — Tracker Configuration (LAP Tracker)

### Frame-to-frame linking
| Parameter | Description |
|-----------|------------|
| **Max linking distance** | Maximum distance a spot can travel between consecutive frames (in physical units). Spots further than this are never linked. |

### Gap closing (optional)
| Parameter | Description |
|-----------|------------|
| **Allow gap closing** | Enable bridging over frames with missed detections |
| **Max gap distance** | Maximum distance for a gap-closing link |
| **Max frame gap** | Maximum number of frames a spot can be absent and still be gap-closed |

### Track splitting (optional)
| Parameter | Description |
|-----------|------------|
| **Allow track splitting** | Enable detection of one object splitting into two (cell division) |
| **Max split distance** | Maximum distance from end of one segment to start of two daughter segments |

### Track merging (optional)
| Parameter | Description |
|-----------|------------|
| **Allow track merging** | Enable detection of two objects merging into one |
| **Max merge distance** | Maximum distance for a merge event |

> **Biologist tip:** Start with gap closing off. If you see too many short "stub" tracks
> where one real trajectory gets broken into 2–3 pieces, enable gap closing with
> Max frame gap = 2 and Max gap distance ≈ your linking distance.

---

## Panel 9 — Tracker Configuration (Kalman Tracker)

| Parameter | Description |
|-----------|------------|
| **Initial search radius** | Search radius (in physical units) to initialise new tracks |
| **Search radius** | Search radius to extend existing tracks using the Kalman prediction |
| **Max frame gap** | Number of frames a track can persist without a detected spot |

---

## Panel 10 — Tracking Progress

Displays progress while linking runs. The Log window shows timing and number of tracks found.

---

## Panel 11 — Track Filtering

**Purpose:** Filter entire tracks by track-level features. Tracks that fail the filters are
hidden (they still exist in the session and can be restored).

**Common track features for filtering:**

| Feature key | Description |
|-------------|-------------|
| `TRACK_DURATION` | Total duration of the track (s or min) |
| `TRACK_DISPLACEMENT` | Straight-line distance from first to last spot |
| `TRACK_MEAN_SPEED` | Mean speed averaged over all edges |
| `TRACK_MAX_SPEED` | Maximum instantaneous speed |
| `NUMBER_SPOTS` | Number of spots in the track |
| `NUMBER_GAPS` | Number of gap-closed frames |
| `NUMBER_SPLITS` | Number of splitting events |
| `NUMBER_MERGES` | Number of merging events |

> **Tip:** Filter by NUMBER_SPOTS > 5 to remove very short stub tracks. Filter by
> TRACK_DISPLACEMENT > X to remove immobile objects (if you only care about moving cells).

---

## Panel 12 — TrackScheme and Display Settings

After tracking and filtering, TrackMate shows the tracking overlay on your image.
From here you can:

### From the main panel (Actions dropdown):
| Action | Description |
|--------|------------|
| **Export statistics to IJ tables** | Opens Results tables for spots, edges, and tracks; all feature values |
| **Capture overlay** | Creates a new image with the track overlay burned in (for export/publication) |
| **Save to XML** | Saves the session |
| **Close gaps in tracks** | Inserts interpolated or detected spots into gap-closed positions |

### TrackScheme
Click **TrackScheme** to open the lineage viewer:
- Rows = tracks, columns = frames
- Spots shown as icons; edges as lines
- **Edit mode**: click-and-drag to create/delete links; double-click spot to rename
- Right-click for context menu (link, unlink, remove, annotate)
- Export the graph as a picture from File ▶ Export image

---

## Manual Editing in the HyperStack Displayer

With the **TrackMate tool** selected in the Fiji toolbar:

| Key / action | Effect |
|-------------|--------|
| `A` + mouse position | Add a new spot at the cursor |
| `D` or `Delete` + mouse over spot | Delete the spot |
| `Space` + drag over spot | Move the spot |
| `Q` / `E` + mouse over spot | Decrease / increase spot radius |
| `Shift+Q` / `Shift+E` | Large radius change |
| `Shift+Click` on spot | Add/remove from selection |
| `L` (with 2 spots selected) | Create a link between the two selected spots |
| `Alt+Click` on edge | Remove the edge |

---

## Saving and Loading Sessions

- **Save** (button or Ctrl+S): Writes a `.xml` file containing all spots, tracks, settings,
  and a path to the source image. **The image itself is not saved in the XML.**
- **Load**: Plugins ▶ Tracking ▶ Load a TrackMate file — restores the session, including
  re-opening the source image from the stored path.
- **Best practice:** Pre-process, crop, and save your image as a `.tif` before launching
  TrackMate, so the XML path always resolves correctly.
