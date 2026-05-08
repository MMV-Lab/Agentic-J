# Screenshots to capture

The site shows polished placeholders for now. Replace each placeholder by
dropping a real PNG into `website/images/` with the **exact filename**
listed below — `index.html` already references those paths, no other edits
needed.

> Tip — capture at **1600 × 1000 px** (or 16:10 of any size). The CSS scales
> them, but a wide capture looks best in the cards. Save as PNG. Keep each
> file under ~600 KB; trim or compress at <https://squoosh.app/> if needed.

---

## How to swap a placeholder for a real screenshot

For each shot below, the page currently shows a styled placeholder (it
hard-codes the target filename in the placeholder box). To replace:

1. Take the screenshot following the recipe in the section.
2. Save it under `website/images/<filename>.png`.
3. Open `website/index.html`, find the matching `<figure class="shot">`
   block, and replace the inner `<div class="placeholder">…</div>` with:
   ```html
   <img src="images/<filename>.png" alt="<short alt text>" />
   ```
4. Reload the page — done.

Alternatively, drop **all four** images into `website/images/` and run the
small swap script at the bottom of this file, which rewrites the four
placeholder blocks at once.

---

## Shot 1 — `01_chat_and_fiji.png`

**What it shows:** the full Agentic-J workspace. Chat panel on the left,
a real Fiji desktop on the right with an image open.

**How to capture (recommended):**

1. `docker compose up` and open <http://localhost:6080/vnc.html>.
2. In the chat, ask:
   > "Open `/app/data/benchmark_images/blobs.jpg`, run **Process → Find
   > Maxima…** with a noise tolerance of 10, and overlay the maxima."
3. Wait until the agent finishes — you should now see:
   - the chat panel populated with planning + tool-call messages,
   - Fiji showing `blobs.jpg` with overlaid maxima (or a labelled mask).
4. Browser fullscreen (`F11`), then take a **window screenshot** of the
   noVNC tab so the entire virtual desktop is captured.
5. Save as `01_chat_and_fiji.png`.

**Composition tip:** Make sure you can see (a) the conversation, (b) the
Fiji image, and (c) at least one tool-call snippet — those three together
sell the product.

---

## Shot 2 — `02_generated_script.png`

**What it shows:** a real Groovy script the agent produced, open in Fiji's
Script Editor.

**How to capture:**

1. After the agent has finished a task (Shot 1's session is fine), open
   `Plugins → Scripting → Script Editor` inside Fiji.
2. `File → Open…` and navigate to the project's
   `data/projects/<your_project>/scripts/imagej/` folder. Open the most
   recent `.groovy` file.
3. Resize the editor so ~30–40 lines are visible, including the
   plugin-import lines at the top and a couple of `IJ.run(...)` calls.
4. Capture **just the editor window** (Alt+PrtSc on Linux, Cmd+Shift+4
   then space on macOS).
5. Save as `02_generated_script.png`.

**Composition tip:** A script with comments visible reads better than a
dense one — pick a script that has a header docstring if available.

---

## Shot 3 — `03_results_plots.png`

**What it shows:** publication-quality output the Python Analyst produces.

**How to capture (option A — image viewer):**

1. After a finished run, open the project's `figures/` folder on the host
   (it's just `./data/projects/<project>/figures/`).
2. Open the best plot (a boxplot, scatter, or histogram) in your image
   viewer.
3. Capture the image at native resolution and save as
   `03_results_plots.png`.

**How to capture (option B — collage in Fiji):**

1. Inside Fiji, open 2–3 plots from the `figures/` folder.
2. `Image → Stacks → Tools → Make Montage…` (2 cols, 2 rows).
3. Take a window screenshot of the montage. Save as
   `03_results_plots.png`.

---

## Shot 4 — `04_setup_wizard.png`

**What it shows:** the first-run setup wizard that appears when no API key
is present.

**How to capture:**

1. Stop the container: `docker compose down`.
2. Temporarily rename your env file: `mv .env .env.bak`.
3. Start fresh: `docker compose up`.
4. Open <http://localhost:6080/vnc.html> — the wizard appears before Fiji
   launches. Capture the wizard window.
5. Save as `04_setup_wizard.png`.
6. Restore your env: `mv .env.bak .env`.

**Composition tip:** The wizard is small. Take a window screenshot
(not full-screen) so the wizard fills the frame.

---

## Optional extras

If you want to add more shots later, the four cards in the screenshots
section are a `<figure class="shot">` pattern that you can copy/paste in
`index.html`. Some good additions:

- **Plugin install flow** — chat asking the agent to install a plugin and
  the Plugin Manager confirming. → `05_plugin_install.png`
- **Dialog vision** — Fiji dialog open + chat showing the agent's
  parameter explanations. → `06_dialog_vision.png`
- **QA report** — the rendered `QA_Checklist_Report.md` open in a
  preview. → `07_qa_report.png`

---

## Bulk swap script (zsh / bash)

Once all four images are saved in `website/images/`, run this from the
project root to replace every placeholder at once:

```bash
cd website
python3 - <<'PY'
import re, pathlib
html = pathlib.Path("index.html").read_text()
mapping = {
  "01_chat_and_fiji.png":   "The full Agentic-J workspace",
  "02_generated_script.png":"A generated Groovy script",
  "03_results_plots.png":   "Stats and plots",
  "04_setup_wizard.png":    "First-run setup wizard",
}
for fname, alt in mapping.items():
    pattern = re.compile(
        r'<div class="placeholder">[\s\S]*?<code>website/images/' + re.escape(fname) + r'</code>[\s\S]*?</div>'
    )
    html = pattern.sub(f'<img src="images/{fname}" alt="{alt}" />', html)
pathlib.Path("index.html").write_text(html)
print("done")
PY
```
