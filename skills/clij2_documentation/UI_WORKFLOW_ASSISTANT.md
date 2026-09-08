# GUI walkthrough — segmenting and counting objects with the CLIJ2-Assistant

The Assistant is the interactive face of CLIJ2: you build a chain of GPU operations by
clicking, see every intermediate result update live, and then **export the finished chain as
a script**. Use it to find parameters; use the exported script for the actual analysis.

The Groovy equivalent of this walkthrough is `GROOVY_WORKFLOW_NUCLEI_SEGMENTATION.groovy`.

---

## 0. Check that a GPU is present (30 seconds, saves confusion later)

`Plugins ▸ ImageJ on GPU (CLIJ2) ▸ Macro tools ▸ CLIJ2 ClInfo`

The Log must list an NVIDIA device. If the only entry is `cpu-haswell-AMD EPYC 7742…`, every
"on GPU" command below will run on the CPU via POCL and be *slower* than plain ImageJ — stop
and fix the OpenCL ICD registration first (`OVERVIEW.md`).

## 1. Open the image and start the Assistant

1. `File ▸ Open…` → select the image (single channel; convert RGB with `Image ▸ Type ▸ 8-bit`).
2. `Plugins ▸ ImageJ on GPU (CLIJ2) ▸ Start CLIJ2-Assistant`.

The image window is now the head of an Assistant chain. A small panel is attached to it with
the operation's parameters and navigation buttons.

## 2. Build the chain

With the **result window of the previous step selected**, pick the next operation from the
menu. Each click adds a linked window; changing a parameter recomputes everything downstream.

Menu labels below are the exact strings in the installed build.

| Step | Menu | Parameters (start here) |
|---|---|---|
| 1. Even out the background | `… (CLIJ2) ▸ Filter ▸ Top-hat (Box) on GPU` | radius_x/y = 15 (must exceed the object radius), radius_z = 0 for 2D |
| 2. Segment | `… (CLIJ2) ▸ Labeling ▸ Voronoi-Otsu-Labeling on GPU` | spot_sigma = 3, outline_sigma = 1 |
| 3. Drop border objects | `… (CLIJ2) ▸ Labeling ▸ Processing ▸ Exclude labels touching image edges on GPU` | — |
| 4. Drop debris | `… (CLIJ2) ▸ Labeling ▸ Processing ▸ Exclude labels outside size range` | minimum = 50, maximum = 1000000 |
| 5. Measure | `… (CLIJ2) ▸ Measure ▸ Statistics of label map excluding background on GPU` | opens a Results table, one row per object |

**Tuning `spot_sigma` is the whole game:** larger = fewer, merged objects; smaller = more,
possibly split objects. Watch the label image update as you change it. `outline_sigma`
smooths the object boundaries only.

The number of objects is the largest value in the label image — read it from
`Analyze ▸ Measure` (Max) on the label window, or from the row count of the statistics table.

## 3. Watch GPU memory

`Plugins ▸ ImageJ on GPU (CLIJ2) ▸ GPU Memory Display` lists every buffer currently on the
device. Each Assistant step holds its result, so a long chain on a big stack can fill the
device; closing a window frees its buffer.

## 4. Export the workflow as a script (the important step)

With any window of the chain selected:

`Plugins ▸ ImageJ on GPU (CLIJ2) ▸ Interoperability ▸ …` or the Assistant panel's script
button. The installed build can generate: **ImageJ macro, Groovy, Jython, JavaScript,
Matlab, Icy protocol/JavaScript**, a human-readable protocol (methods-section text), and
markdown.

Take the **Groovy** export — it is the reproducible artefact and can be edited into a batch
script. Note that the export uses the `Ext.CLIJ2_*` macro style for the macro/IJM target;
that style **must not** be wrapped in `IJ.runMacro()` from a Groovy script (it aborts with a
blocking "Macro Error" dialog — see `GROOVY_API.md` §8). Convert it to the Java API, or start
from `GROOVY_WORKFLOW_NUCLEI_SEGMENTATION.groovy`.

`File ▸ Save As ▸ CLIJ2 Image Data Flow (save)` stores the chain itself so it can be reloaded
later with `File ▸ Import ▸ CLIJ2 Image Data Flow (load)`.

## 5. Apply to a folder

The Assistant is single-image. For a folder, export the chain to Groovy and drop it into the
loop skeleton in `GROOVY_WORKFLOW_BATCH_FOLDER.groovy`, which adds the two things the export
lacks: `release()` inside the loop and per-file error handling.

---

### GUI notes specific to this container

- The Assistant's **documentation "?" button** throws
  `UnsupportedOperationException: Desktop API is not supported on the current platform` — no
  browser is installed for `java.awt.Desktop`. Harmless; ignore it.
- `Plugins ▸ ImageJ on GPU (CLIJx) ▸ Start CLIJx-Assistant (experimental)` offers extra
  generators (clEsperanto Jupyter notebook, napari, Maven plugin project) but is experimental.
- Applying a CLIJ2 menu command from a script (`IJ.run(imp, "Gaussian blur 2D on GPU", …)`)
  works, but the result lands in a window with a generated title such as
  `gaussian_blur-1828107390`, so scripts cannot reliably pick it up. Script the Java API.
