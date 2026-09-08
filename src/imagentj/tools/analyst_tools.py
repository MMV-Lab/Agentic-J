import os
import pandas as pd
import re
import sys
import textwrap
import io
from langchain_core.tools import tool
import tempfile

from imagentj import run_control

# ---------------------------------------------------------------------------
# Conda envs the Python agent may execute in.
#
# The main env carries the data-science + measurement stack (pandas, seaborn,
# scipy, scikit-image, scikit-learn, cp_measure). brainglobe lives in its
# own env because it drags in napari + PyQt6 + vtk + keras, which collide with the
# main env's PySide6 GUI and force a pillow downgrade.
#
# napari-mcp is the isolated env that hosts the in-container napari viewer AND the
# micro_sam ("Segment Anything for Microscopy") stack (torch + segment-anything +
# micro_sam). The analyst runs micro_sam batch/automatic segmentation scripts here
# with `# imagentj-env: napari-mcp`; the SAME env backs the interactive napari
# widget the supervisor drives via mcp__napari_mcp__execute_code, so a mask made in
# a script and a mask made interactively come from an identical model.
#
# A script selects its env with a first-line magic comment:
#     # imagentj-env: brainglobe
# Absent the header, the main env is used.
# ---------------------------------------------------------------------------
_CONDA_ENVS: dict[str, str] = {
    "main": "/opt/conda/envs/local_imagent_J/bin/python",
    "brainglobe": "/opt/conda/envs/brainglobe/bin/python",
    "napari-mcp": "/opt/conda/envs/napari-mcp/bin/python",
    # cellpose v3 (3.1.1.2) + torch/cu126. The Python API is the FAST route for
    # segmenting a folder: the model is loaded once and stays resident, where the
    # Fiji/BIOP wrapper re-spawns bash+conda+python and reloads the model for every
    # cp.run(). Even a loop that rebuilds the model per image still beats the best
    # Fiji variant, which is why folder-scale cellpose is routed here —
    # see skills/python/cellpose/SKILL.md.
    # Self-sufficient for a whole pipeline: numpy, tifffile, scikit-image, scipy,
    # pandas, matplotlib, opencv (no seaborn — the non-main preamble doesn't import it).
    "cellpose": "/opt/conda/envs/cellpose/bin/python",
    # cellpose 4.1.1 — the cpsam (Cellpose-SAM) model only. Separate env because v4
    # drops model_type= and changes the eval signature; mixing them breaks both.
    "cellpose4": "/opt/conda/envs/cellpose4/bin/python",
}
_DEFAULT_ENV = "main"

_ENV_HEADER_RE = re.compile(r"^#\s*imagentj-env:\s*([A-Za-z0-9_.-]+)\s*$")


def _parse_env_header(code: str) -> str:
    """Return the env named by a `# imagentj-env: <name>` comment in the first 5 lines."""
    for line in code.splitlines()[:5]:
        match = _ENV_HEADER_RE.match(line.strip())
        if match:
            return match.group(1)
    return _DEFAULT_ENV


def _resolve_interpreter(env: str) -> tuple[str | None, str | None]:
    """Map an env name to its python binary. Returns (interpreter, error)."""
    if env not in _CONDA_ENVS:
        known = ", ".join(sorted(_CONDA_ENVS))
        return None, f"Error: unknown env '{env}'. Available envs: {known}."
    interpreter = _CONDA_ENVS[env]
    if not os.path.exists(interpreter):
        # Dev/host runs outside the container: fall back to the current interpreter
        # rather than failing, but only for the default env.
        if env == _DEFAULT_ENV:
            return sys.executable, None
        return None, (
            f"Error: env '{env}' is not installed in this container "
            f"(expected {interpreter}). Rebuild the image or use the 'main' env."
        )
    return interpreter, None

@tool
def inspect_csv_header(file_path: str):
    """
    Returns the COMPLETE schema of a CSV — every column name and dtype — plus a 5-row
    sample preview. This is a SCHEMA tool, not a data loader: it intentionally truncates
    to the first 5 rows (the remaining rows are NOT shown and you do NOT need them). The
    column names and dtypes it returns are the full, exhaustive set — that is everything
    required to write pandas code against this file.

    Call this exactly ONCE per file, BEFORE writing code. The schema never changes while
    you work, so re-calling it (or re-reading the script) returns identical output and
    just wastes turns. Your Python script will read the full data at run time via
    pd.read_csv — you do not need to see the remaining rows here.

    Input MUST be a valid absolute file path (e.g., 'C:/Users/Name/data.csv').
    """
    try:
        # No more path joining; use the path directly
        if not os.path.exists(file_path):
            return f"Error: The file path '{file_path}' does not exist on this PC."

        df = pd.read_csv(file_path, nrows=5)

        buffer = io.StringIO()
        df.info(buf=buffer)
        info_str = buffer.getvalue()

        # Total row count so the model knows the sample is deliberate, not all the data.
        try:
            with open(file_path, "rb") as _f:
                total_rows = max(sum(1 for _ in _f) - 1, 0)  # minus header
            total_str = f"{total_rows} data rows"
        except Exception:
            total_str = "unknown row count"

        base = (
            f"Structure of {os.path.basename(file_path)} ({len(df.columns)} columns, {total_str}):\n"
            f"{info_str}\n"
            f"Sample preview — first 5 of {total_str} (truncated on purpose; the column list "
            f"above is COMPLETE and is all you need to write your code):\n{df.to_string()}\n"
            f"You now have the full schema. Do NOT inspect or re-read again — write your script."
        )
        return base
    except Exception as e:
        return f"Error reading file at {file_path}: {str(e)}"


# ---------------------------------------------------------------------------
# Deliverable measurement — the plausibility check the QA reporter lacked.
#
# Every gate in this pipeline used to check FORM (filename, schema, file count)
# and none checked MAGNITUDE. A benchmark run delivered 681 cell centroids across
# 21 images for a task whose prompt said "up to 2,000+ cells per image", and the
# QA reporter, the handoff and the harness validator all passed it — because 21
# correctly-named CSVs with an X,Y header is exactly what they were looking for.
#
# This tool measures CONTENT deterministically so the reporter compares numbers
# instead of eyeballing a 5-row preview.
# ---------------------------------------------------------------------------

# Above this many bytes we take max(label) as the object count instead of a full
# np.unique — exact for sequentially-labelled masks, and O(n) rather than O(n log n)
# on a 400 MB volume.
_BIG_ARRAY_BYTES = 64 * 1024 * 1024
_MAX_FILES_MEASURED = 60


def _measure_one(path: str) -> dict:
    """Measure a single deliverable. Returns {} if the type isn't measurable."""
    import numpy as np

    ext = os.path.splitext(path)[1].lower()
    out: dict = {"name": os.path.basename(path)}

    if ext in (".csv", ".tsv"):
        sep = "\t" if ext == ".tsv" else ","
        with open(path, "rb") as f:
            n_lines = sum(1 for _ in f)
        out["kind"] = "table"
        out["count"] = max(n_lines - 1, 0)          # minus header
        try:
            head = pd.read_csv(path, sep=sep, nrows=0)
            out["columns"] = list(head.columns)
        except Exception:
            out["columns"] = []
        return out

    if ext in (".tif", ".tiff", ".png"):
        try:
            if ext == ".png":
                from PIL import Image
                arr = np.array(Image.open(path))
            else:
                import tifffile
                arr = tifffile.imread(path)
        except Exception as e:
            return {"name": out["name"], "kind": "image", "error": str(e)[:80]}
        out["kind"] = "image"
        out["shape"] = tuple(int(x) for x in arr.shape)
        out["dtype"] = str(arr.dtype)
        if arr.dtype.kind in "iub":
            mx = int(arr.max()) if arr.size else 0
            if arr.nbytes > _BIG_ARRAY_BYTES:
                out["count"] = mx                    # max label id
                out["count_method"] = "max_label"
            else:
                out["count"] = int(len(np.unique(arr))) - 1   # minus background
                out["count_method"] = "unique"
            out["max_label"] = mx
        else:
            out["count"] = None                      # float image: not a label mask
        return out

    return {}


def _same_bytes(a: str, b: str, chunk: int = 1 << 20) -> bool:
    """True if two files have identical content. Only ever called on candidates
    that already matched on name AND size, so this is a confirmation step, not a
    scan — it keeps the report's claim of identity honest rather than inferred."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                ba, bb = fa.read(chunk), fb.read(chunk)
                if ba != bb:
                    return False
                if not ba:
                    return True
    except OSError:
        return False


def _fmt_stats(values: list) -> str:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return "no measurable values"
    n = len(vals)
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return (f"min={vals[0]}  median={median}  max={vals[-1]}  "
            f"total={sum(vals)}  zero/empty_files={sum(1 for v in vals if v == 0)}")


@tool
def summarize_deliverables(
    output_dir: str,
    pattern: str = "*",
    expected_per_file: float = 0.0,
    input_dir: str = "",
) -> str:
    """
    MEASURE the actual content of deliverable files and return hard numbers:
    per-file object/row counts, dtype, shape, and aggregate min/median/max/total.

    Use this in every QA audit BEFORE judging whether a result is correct. Reading a
    file's header or a 5-row preview tells you the FORMAT is right; it cannot tell you
    the RESULT is right. A folder of perfectly-named, perfectly-schema'd CSVs can still
    hold a hundred times too few rows, and that is invisible to every other check.

    Args:
        output_dir: Absolute path to the deliverable directory (e.g. '/benchmark/output').
        pattern: Glob for the deliverables, e.g. '*.csv', '*_seg.tif', '*nuclei*.tif'.
                 Searched recursively. Default '*' measures every measurable file, which
                 is almost always TOO BROAD — see STRUCTURE below.
        expected_per_file: OPTIONAL but strongly preferred. If the user's request states
                 an expected number of objects per image/file (e.g. "up to 2,000 cells
                 per image"), pass that number. Pass 0.0 only if no quantity is stated.
        input_dir: OPTIONAL but strongly preferred. The folder the images were read FROM.
                 Enables two checks that need no stated quantity: whether a deliverable
                 was produced for every input, and whether the "deliverables" being
                 measured are really just the input images copied into the output folder.

    STRUCTURE: the checks below run whether or not a quantity was supplied, because most
    real requests never state one. They catch the failures that per-file statistics hide:
    a label mask that was never labelled, a set that is really inputs copied through, a
    glob that mixed two kinds of file, or a batch that silently stopped early.

    Returns a text report ending in a PLAUSIBILITY line you must copy into your findings.
    """
    import glob as _glob

    if not os.path.isdir(output_dir):
        return f"Error: '{output_dir}' is not a directory."

    paths = sorted(
        p for p in _glob.glob(os.path.join(output_dir, "**", pattern), recursive=True)
        if os.path.isfile(p)
    )
    if not paths:
        return (f"NO FILES matched pattern '{pattern}' under {output_dir}.\n"
                f"PLAUSIBILITY VERDICT: FAIL — the deliverable is missing entirely.")

    total_matched = len(paths)
    sampled = paths
    note = ""
    if total_matched > _MAX_FILES_MEASURED:
        step = total_matched / _MAX_FILES_MEASURED
        sampled = [paths[int(i * step)] for i in range(_MAX_FILES_MEASURED)]
        note = (f"  (measured an even sample of {len(sampled)} of {total_matched} files; "
                f"statistics below are from the sample)\n")

    rows, counts, kinds, dtypes, errors = [], [], set(), set(), []
    measured = []          # keep the raw measurements for the structural checks below
    for p in sampled:
        m = _measure_one(p)
        if not m:
            continue
        if m.get("error"):
            errors.append(f"{m['name']}: {m['error']}")
            continue
        m["path"] = p
        measured.append(m)
        kinds.add(m.get("kind", "?"))
        if m.get("dtype"):
            dtypes.add(m["dtype"])
        c = m.get("count")
        counts.append(c)
        if m["kind"] == "table":
            rows.append(f"  {m['name']}: {c} rows, columns={m.get('columns')}")
        else:
            rows.append(f"  {m['name']}: {c} objects, shape={m.get('shape')}, "
                        f"dtype={m.get('dtype')}")

    if not counts:
        return (f"{total_matched} file(s) matched '{pattern}' but none were measurable "
                f"(not CSV/TIF/PNG, or unreadable). Errors: {errors[:3]}")

    head = "\n".join(rows[:25])
    more = f"\n  … {len(rows) - 25} more file(s) not listed" if len(rows) > 25 else ""

    report = (
        f"DELIVERABLE MEASUREMENT — {output_dir}  (pattern: '{pattern}')\n"
        f"files matched: {total_matched}   kinds: {sorted(kinds)}"
        f"{('   dtypes: ' + str(sorted(dtypes))) if dtypes else ''}\n"
        f"{note}\n"
        f"PER FILE:\n{head}{more}\n\n"
        f"AGGREGATE (objects per file): {_fmt_stats(counts)}\n"
    )
    if errors:
        report += f"UNREADABLE: {len(errors)} file(s) — {errors[:3]}\n"

    numeric = sorted(c for c in counts if c is not None)
    if not numeric:
        return report + "\nPLAUSIBILITY VERDICT: NOT APPLICABLE (no countable content)."

    n = len(numeric)
    median = numeric[n // 2] if n % 2 else (numeric[n // 2 - 1] + numeric[n // 2]) / 2
    empties = sum(1 for c in numeric if c == 0)

    # ---------------------------------------------------------------- verdict
    # Findings are gathered as (severity, message) and the worst one becomes the
    # verdict. Two things follow from that shape, and both were bugs before:
    #
    #  - The structural checks run even when expected_per_file IS supplied. They
    #    used to sit in an `else`, so a median that happened to land in range
    #    returned a clean PASS while half the files were empty or every mask held
    #    a single object. A quantity check and a structural check answer different
    #    questions and neither substitutes for the other.
    #  - They run when no quantity is supplied, which is the common case: across
    #    the five benchmark tasks only ONE stated a number, so an expectation-only
    #    gate is inert on 4 of 5 real jobs. Measured on eight finished task
    #    folders, the previous version returned "NO EXPECTATION SUPPLIED" on seven.
    FAIL, SUSPECT = 3, 2
    findings: list = []

    skew = (numeric[-1] / median) if median else float("inf")
    label_masks = [m for m in measured
                   if m.get("kind") == "image" and m.get("max_label") is not None]

    if empties * 2 >= n:
        findings.append((FAIL, f"{empties} of {n} files contain ZERO objects. A deliverable "
                               f"that is mostly empty is wrong regardless of what was "
                               f"expected."))
    elif empties:
        # One empty mask in a batch is not noise — it is one image where the
        # pipeline silently produced nothing.
        findings.append((SUSPECT, f"{empties} of {n} files contain ZERO objects. Name them "
                                  f"and confirm each is genuinely empty rather than a "
                                  f"silent per-image failure."))

    if len(label_masks) >= 3 and all(m.get("max_label") == 1 for m in label_masks):
        findings.append((FAIL, f"every one of the {len(label_masks)} label masks has a "
                               f"maximum label of 1, i.e. ONE object covering the whole "
                               f"image. This is a binary mask that was never labelled — "
                               f"the objects were never separated. Connected-component "
                               f"labelling or watershed is missing from the pipeline."))

    if len(kinds) > 1:
        findings.append((SUSPECT, f"the glob '{pattern}' matched more than one kind of file "
                                  f"({sorted(kinds)}), so the aggregate above mixes table "
                                  f"rows with mask object counts and means nothing. "
                                  f"Re-measure each deliverable kind with its own narrower "
                                  f"pattern before scoring."))

    if n > 3 and len(set(numeric)) == 1:
        findings.append((SUSPECT, f"all {n} files report exactly {numeric[0]} objects. "
                                  f"Identical counts across different images are not "
                                  f"biologically plausible — check whether one result was "
                                  f"written repeatedly, or the same image processed twice."))

    if n > 3 and skew > 20:
        findings.append((SUSPECT, f"the spread is implausible for one kind of deliverable: "
                                  f"median {median} but max {numeric[-1]} ({skew:.0f}x). The "
                                  f"glob has most likely matched two different kinds of file "
                                  f"(e.g. per-image results plus a combined summary), so this "
                                  f"measurement is not what the user asked for."))

    if input_dir and os.path.isdir(input_dir):
        _IMG = (".tif", ".tiff", ".png", ".jpg", ".jpeg", ".nd2", ".czi", ".lif")
        in_paths = [p for p in _glob.glob(os.path.join(input_dir, "**", "*"), recursive=True)
                    if os.path.isfile(p)]
        in_names = {os.path.basename(p) for p in in_paths}
        in_images = [p for p in in_paths if os.path.splitext(p)[1].lower() in _IMG]

        # Copies of the input are NOT by themselves a failure — the pipeline
        # legitimately stages raw images into the project workspace, and flagging
        # that as a defect would fire on every well-behaved run. What IS wrong is
        # measuring them: a statistic computed over the inputs describes the input,
        # not the result. So this is a measurement-validity finding, like the
        # mixed-kind one, and it asks for a re-measure rather than a re-run.
        by_size = {}
        for p in in_paths:
            by_size.setdefault((os.path.basename(p), os.path.getsize(p)), p)
        echoed = []
        for m in measured:
            src = by_size.get((m["name"], os.path.getsize(m["path"])))
            if src and _same_bytes(src, m["path"]):
                echoed.append(m)
        if echoed:
            findings.append((SUSPECT, f"{len(echoed)} of the {len(measured)} measured files are "
                                      f"identical copies of the INPUT images (e.g. "
                                      f"{', '.join(m['name'] for m in echoed[:3])}), verified by "
                                      f"content. Staging inputs into the workspace is normal, "
                                      f"but measuring them is not: the statistics above partly "
                                      f"describe the input rather than the result. Re-measure "
                                      f"with a pattern that selects only produced files."))

        # A batch that silently stopped early is a genuine failure, and comparing
        # produced files against input IMAGES (not every stray .txt) is the check.
        #
        # But it rests on a premise that is only sometimes true: that the deliverable is
        # PER-IMAGE, one output per input. That holds for masks and per-image tables; it
        # is simply false for an AGGREGATE deliverable — one summary CSV distilled from a
        # whole dataset is the correct and complete answer to "measure colocalization
        # across these movies", and counting it as "1 file for 244 images" failed runs
        # that had produced exactly what was asked for. Per-image artefacts are the case
        # this check was built for, so that is the case it now fires on; for tables the
        # premise is unknowable from the files alone, so it asks instead of failing.
        n_in = len(in_images)
        produced = [m for m in measured if m["name"] not in in_names]
        per_image_kind = [m for m in produced if m.get("kind") == "image"]
        if n_in and len(produced) < n_in:
            if not produced:
                # Nothing was produced AT ALL, yet files matched the pattern — so
                # every measured file is one of the inputs. The aggregate-deliverable
                # argument does not reach this case: it defends ONE summary distilled
                # from many inputs, and there is no summary here. Kept ahead of the
                # branches below because both test what the produced files ARE, and an
                # empty list answers neither. (The "no files matched" FAIL earlier in
                # this function does not cover it: files DID match, they are just all
                # echoed inputs.)
                findings.append((FAIL, f"NO produced files for {n_in} input image(s) — every "
                                       f"measured file is one of the inputs. The run has not "
                                       f"delivered anything; a missing deliverable is a failure, "
                                       f"not a caveat."))
            elif per_image_kind:
                findings.append((FAIL, f"only {len(produced)} produced file(s) for {n_in} input "
                                       f"image(s), and they are per-image artefacts "
                                       f"({len(per_image_kind)} mask/image file(s)) — one is "
                                       f"expected per input. The batch stopped early or skipped "
                                       f"images; a partial deliverable is a failure, not a "
                                       f"caveat."))
            elif len(produced) > 1:
                findings.append((SUSPECT, f"{len(produced)} produced table(s) for {n_in} input "
                                          f"image(s). If these are per-image tables the batch "
                                          f"stopped early and this is a FAIL; if they are "
                                          f"aggregate summaries over the whole dataset it is "
                                          f"correct. State which, from the requested "
                                          f"deliverable, before judging."))
            # A single aggregate table over many inputs is the normal shape of a summary
            # deliverable — no finding. Its content is still checked by every other rule
            # here (empties, expected_per_file, echoed inputs).

    quantity = None
    if expected_per_file and expected_per_file > 0:
        ratio = (median / expected_per_file) if expected_per_file else 0.0
        if ratio == 0:
            quantity = (FAIL, f"every file is empty, but ~{expected_per_file:g} objects per "
                              f"file were expected.")
        elif ratio < 0.1:
            quantity = (FAIL, f"median {median} per file vs ~{expected_per_file:g} expected: "
                              f"{1 / ratio:.0f}x TOO FEW. This is an order-of-magnitude miss, "
                              f"not noise.")
        elif ratio > 10:
            quantity = (FAIL, f"median {median} per file vs ~{expected_per_file:g} expected: "
                              f"{ratio:.0f}x TOO MANY. Likely over-segmentation or noise "
                              f"counted as objects.")
        if quantity:
            findings.append(quantity)

    report += "\nPLAUSIBILITY VERDICT: "
    if findings:
        worst = max(f[0] for f in findings)
        label = "FAIL" if worst == FAIL else "SUSPECT"
        ordered = [m for s, m in sorted(findings, key=lambda f: -f[0])]
        report += f"{label} — " + ordered[0]
        for extra in ordered[1:]:
            report += f"\n  ALSO: {extra}"
        if worst == FAIL:
            report += ("\n  Report this as a critical failure and set success=false. Do not "
                       "describe the analysis as complete.")
    elif expected_per_file and expected_per_file > 0:
        report += (f"PASS — median {median} per file is within an order of magnitude of the "
                   f"~{expected_per_file:g} expected, and no structural anomaly was found "
                   f"({n} files, no empties, one kind of file, plausible spread).")
    else:
        # Deliberately NOT phrased as a pass. Nothing was checked against, and saying
        # so plainly is what stops a silent "no news is good news" reading.
        missing = ["expected_per_file (a stated quantity from the user's request)"]
        if not input_dir:
            missing.append("input_dir (the folder the images were read from)")
        report += ("INCOMPLETE — the structural checks found nothing wrong, but no quantity "
                   "was supplied so the RESULT ITSELF was never checked against anything. "
                   "This is NOT a pass. Supply " + " and ".join(missing) + ", then call this "
                   "tool again. If the request genuinely states no quantity, say explicitly "
                   "in the report that plausibility could not be verified.")

    if empties:
        report += (f"\nEMPTY FILES: {empties} of {n} measured file(s) contain ZERO objects. "
                   f"Confirm this is genuine and not a silent failure.")
    return report


def run_python_code(code: str, output_directory: str, purpose: str = ""):

    """
    Executes Python code with full PC access.
    Packages pd, np, plt, sns, and stats are PRE-IMPORTED (main env only).
    NEVER execute code that was generated by yourself.

    The script may select a conda env with a first-line magic comment, e.g.
    `# imagentj-env: brainglobe`. Without it the main env is used, and only the
    main env gets the pre-imported data-science preamble.

    Input:
      - code: Python code to execute (string).
      - output_directory: Directory where any output files should be saved (string).
    """
    if not os.path.exists(output_directory):
        return f"Error: Directory '{output_directory}' not found."

    env = _parse_env_header(code)
    interpreter, env_error = _resolve_interpreter(env)
    if env_error:
        return env_error

    # Only the main env is guaranteed to carry seaborn/pandas/scipy. A side env
    # (brainglobe) gets a bare preamble so an import it lacks can't crash the run
    # before the agent's own code starts.
    is_main = env == _DEFAULT_ENV

    header_lines: list[str] = []
    if is_main:
        header_lines += [
            "import pandas as pd",
            "import numpy as np",
            "import matplotlib.pyplot as plt",
            "import seaborn as sns",
            "from scipy import stats",
        ]
    header_lines += [
        "import os",
        "import sys",
        "",
        "try:",
        f"    os.chdir(r'{output_directory}')",
    ]
    if is_main:
        header_lines += [
            '    sns.set_theme(style="whitegrid")',
            "    plt.rcParams['figure.dpi'] = 300",
        ]
    header_lines.append("    # --- AGENT CODE START ---")
    header = "\n".join(header_lines)

    footer = textwrap.dedent("""
            # --- AGENT CODE END ---
            print("\\n--- EXECUTION FINISHED SUCCESSFULLY ---")
        except Exception as e:
            print(f"\\nPYTHON TRACEBACK ERROR: {str(e)}", file=sys.stderr)
            sys.exit(1)
    """).strip()
    
    # Indent the agent's code by 4 spaces to align with the 'try' block
    indented_code = textwrap.indent(code, "    ")
    
    full_script = f"{header}\n{indented_code}\n{footer}"

    script_path = os.path.join(tempfile.gettempdir(), "supervisor_py_exec.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(full_script)

    try:
        run = run_control.SupervisedProcess(
            [interpreter, script_path], language="python", code=code, purpose=purpose,
        )
    except Exception as e:
        return f"SYSTEM ERROR: {str(e)}"

    with run:
        try:
            run.wait()
            stdout, stderr = run.stdout, run.stderr

            if run.handle.terminated:
                return (
                    f"{run_control.stop_headline(run.handle)} (env='{env}').\n"
                    f"{run_control.stop_guidance(run.handle)}\n"
                    f"Partial STDOUT before termination:\n{stdout[-2000:]}\n"
                    f"Partial STDERR:\n{stderr[-1000:]}"
                )

            if run.returncode != 0:
                return (
                    f"CRASH DETECTED IN PYTHON (env='{env}'):\n"
                    f"STDOUT: {stdout}\nSTDERR: {stderr}"
                )
            # The leading "SUCCESS:" is load-bearing: learned_memory._run_succeeded gates the
            # background Librarian on out.lstrip().startswith("SUCCESS:"). Keep the colon
            # immediately after SUCCESS or Python runs stop being learned as recipes.
            return f"SUCCESS: (env='{env}')\n{stdout}"
        except Exception as e:
            return f"SYSTEM ERROR: {str(e)}"



python_analyst_tools = [inspect_csv_header, run_python_code]