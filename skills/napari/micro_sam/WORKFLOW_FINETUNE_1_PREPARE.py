# imagentj-env: napari-mcp
"""
micro_sam fine-tuning — STAGE 1 of 4: build the annotation task.

Turns a folder of images into a small set of SMALL SQUARE TILES that a human can annotate
completely in a few minutes each, and pre-segments every tile with the stock model so the
human CORRECTS a first guess instead of drawing from scratch.

WHY TILES: micro_sam can only train its automatic-instance-segmentation (AIS) decoder on
DENSELY annotated data — every object inside the annotated field must be labelled, because
anything left unlabelled is taught to the decoder as background. Annotating every cell in a
full field is hours of work. Annotating every cell inside a 512x512 tile is 1-3 minutes, and
a tile IS dense. So the user never annotates all cells in an image; they annotate all cells
in a few small squares. That is the whole trick, and it is what makes this workflow tractable.
(micro_sam's own docs: "It's okay to use sparse segmentations ... for just finetuning Segment
Anything WITHOUT the additional decoder" — sparse costs you AIS, i.e. hands-off batch
segmentation. Tiles keep AIS.)

WHO PICKS THE TILES: the human, by clicking (PICK_MODE = "interactive", the default). A napari
window walks through one sample field per group — per well, per condition, per plate, whatever
GROUP_REGEX says — and the user clicks where the tile should sit. Two or three minutes, and it
removes the single biggest failure mode of this workflow: an automatic content score CANNOT
tell a 2 um dust speck from a 12 um nucleus, so on real slides it happily hands the annotator
a field of stain precipitate (many "objects", zero cells) or an out-of-focus haze. A human
sees the difference in half a second. Set PICK_MODE = "auto" only for unattended runs, and
then LOOK at previews/ before letting anyone annotate.

Outputs (all under TASK_DIR):
    tiles/tile_00000.tif            the 8-bit image crops the human will annotate
    presegmentation/tile_00000.tif  stock-model first guess, loaded into the annotator
    previews/tile_00000.png         raw + outline overlay, so the agent can look at it
    annotations/                    EMPTY — stage 2 fills it, one TIFF per finished tile
    manifest.json                   everything stages 2/3/4 need. Do not hand-edit.
    ANNOTATION_INSTRUCTIONS.md      the human-facing instructions, with real numbers in them

Next: WORKFLOW_FINETUNE_2_ANNOTATE.py

Run in the `napari-mcp` env (the `# imagentj-env` header selects it). Edit CONFIG, execute.
"""
import os
import re
import glob
import json
import datetime

import numpy as np
import tifffile
from skimage.filters import gaussian, threshold_otsu
from skimage.measure import label as cc_label
from skimage.segmentation import find_boundaries

# ---- CONFIG -----------------------------------------------------------------
INPUT_DIR = "/app/data/projects/demo/raw_images"
TASK_DIR = "/app/data/projects/demo/microsam_finetune"

PICK_MODE = "interactive"   # "interactive" = the USER clicks the tiles (default, and what
                            #   makes this reliable). "auto" = content heuristic, no window;
                            #   ONLY for unattended runs, and its tiles must be reviewed.
GROUP_REGEX = None     # How to split the folder into groups the picker walks through, so the
                       # tile set covers the experiment instead of one lucky corner of it.
                       #   None      -> group by sub-folder, or one group if the folder is flat
                       #   r"(V\\d+)"  -> one group per well token in the filename (V1, V2, ...)
                       #   r"(pos|neg)" -> one group per condition
                       # The groups are PRINTED before the window opens — check them there.
N_TILES = None         # total tiles the human annotates. None = auto: one per group, at least
                       # 6 overall. 6-10 is the sweet spot (~20 min of work, enough objects to
                       # move the model); below 4 there is not enough left for a validation split.
TILE_SIZE = None       # px, or None = MEASURED from the data (recommended). The script segments
                       # one field per group with the stock model, works out how densely packed
                       # the objects are, and picks the tile size that holds about
                       # TARGET_OBJECTS_PER_TILE of them — clamped to [256, 1024] and to the
                       # smallest image. A fixed 512 is right for a confluent monolayer and
                       # far too small for a sparse blood smear, which is why this is measured.
TARGET_OBJECTS_PER_TILE = 25   # what a tile should hold: enough to teach, few enough to finish.
SHOW_PRESEG = "auto"   # show the stock model's CURRENT segmentation on each field in the picker,
                       # so the user can aim at the places it gets WRONG — which is what actually
                       # teaches the model. "auto" = on with a GPU, off on CPU (minutes per
                       # field). True / False force it.
AUTO_ADVANCE = True    # move to the next group by itself once this group's quota is picked, so
                       # covering ten wells is ten clicks. The picker has a button to turn this
                       # off mid-session when you want several tiles from one field.
MODEL_TYPE = None      # None = auto (vit_b_lm on GPU, vit_t_lm on CPU). This is BOTH the
                       # pre-segmentation model AND the fine-tuning starting point — stage 3
                       # reads it from the manifest, so set it once, here.
SEGMENT_BACKEND = "micro_sam"   # WHICH MODEL the user is shown and will end up training.
                       # "micro_sam" -> stages 3/4 are skills/napari/micro_sam/WORKFLOW_FINETUNE_3,4
                       # "cellpose"  -> stages 3/4 are skills/python/cellpose/
                       #                WORKFLOW_FINETUNE_CP_3,4 (cpsam). Stages 1 and 2 are
                       # SHARED either way: the picker and the SAM-assisted annotator do not care
                       # what gets trained, and SAM-assisted clicking is the fastest way to
                       # produce masks whichever model consumes them. Set this to match the model
                       # you intend to fine-tune, so the user corrects THAT model's mistakes.
CP_MODEL = "cpsam"     # SEGMENT_BACKEND="cellpose" only: WHICH cellpose model the picker
                       # segments with — and therefore which model's mistakes the user
                       # corrects. It is recorded in the manifest and stage 3 fine-tunes from
                       # the SAME model by default, so the two cannot drift apart. "cpsam"
                       # (cellpose 4) or any v3 zoo name ("nuclei", "cyto3", ...); the worker
                       # re-execs into whichever env has it. Match it to the model you intend
                       # to fine-tune: showing the user cpsam's errors and then training
                       # `nuclei` throws away the whole point of letting them pick.
BASE_CHECKPOINT = "auto"   # ROUND 2 AND LATER. "auto" = if this data has already been fine-tuned
                       # once, start from THAT model instead of the stock one: the picker then
                       # shows what the CURRENT model gets wrong, so the user spends their tiles
                       # on the remaining errors instead of re-fixing what is already learned.
                       # Stage 3 continues training from it and measures against it, so "did it
                       # improve?" means "better than last round", not "better than stock".
                       # None = always start from stock. A path = use that .pt.
CHANNEL = None         # 2D grayscale / RGB input: leave None.
                       # 3D input (C,Y,X) or (Z,Y,X): REQUIRED — an int index, or "max" for a
                       # maximum projection. The script refuses to guess; training on the
                       # wrong channel is silent and wastes the human's annotation time.
EXTS = (".tif", ".tiff", ".png", ".jpg", ".jpeg")   # matched CASE-INSENSITIVELY (".TIF" too)
RECURSIVE = False      # True also searches sub-folders. Auto-enabled if the flat scan is empty.
MAX_TILES_PER_IMAGE = None   # auto mode only. None = auto (spreads tiles over as many source
                             # images as possible, which generalises better than N from one field)
MAX_IMAGES_SCANNED = 40      # auto mode only: cap on how many images are opened to look for
                             # good tile positions.
SEED = 0
ADVANCE_DELAY_MS = 500   # interactive mode: how long the square you just placed stays
                         # on screen before the picker moves to the next group. 0 = instant.
# -----------------------------------------------------------------------------

os.environ.setdefault("TQDM_MININTERVAL", "30")   # keep progress bars out of the transcript

TILE_STEM = "tile_{:05d}"


def ensure_model_cache(fallback_dir):
    """Point MICROSAM_CACHEDIR somewhere writable, and say so.

    micro_sam downloads its checkpoints with pooch into MICROSAM_CACHEDIR (default
    ~/.cache/micro_sam). In a container whose home is a named volume older than the image,
    that path can survive as a root-owned directory this process cannot write, and every
    model load then dies with `PermissionError: .../micro_sam/models` — a traceback that
    points at pooch and never mentions the volume. Probe it for real (mkdir + write, not a
    permission bit), fall back into the task folder, and carry over any weights already
    downloaded so the fallback costs no extra download."""
    import shutil

    current = os.environ.get("MICROSAM_CACHEDIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "micro_sam")
    models = os.path.join(current, "models")
    try:
        os.makedirs(models, exist_ok=True)
        probe = os.path.join(models, ".writable")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return current
    except OSError as exc:
        why = exc.strerror or str(exc)      # bind it: `exc` itself is gone after the block

    os.makedirs(os.path.join(fallback_dir, "models"), exist_ok=True)
    os.environ["MICROSAM_CACHEDIR"] = fallback_dir
    os.environ.setdefault("XDG_CACHE_HOME", os.path.dirname(fallback_dir))
    print(f"[prepare] model cache {current} is not writable ({why}) -> using {fallback_dir}")
    if os.path.isdir(models):
        for f in os.listdir(models):                       # reuse anything already downloaded
            src, dst = os.path.join(models, f), os.path.join(fallback_dir, "models", f)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.copy(src, dst)
                    print(f"[prepare]   carried over cached weight {f}")
                except OSError:
                    pass
    return fallback_dir


def list_images(input_dir, exts=None, recursive=False):
    """Every image under input_dir, matching extensions CASE-INSENSITIVELY.

    Microscope exports are routinely written as `.TIF`. Globbing "*.tif" on a case-sensitive
    filesystem matches none of them and the script dies claiming the folder is empty."""
    wanted = {e.lower() for e in (exts if exts is not None else EXTS)}
    found = []
    if recursive:
        for root, _, files in os.walk(input_dir):
            found += [os.path.join(root, f) for f in files
                      if os.path.splitext(f)[1].lower() in wanted]
    else:
        found = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                 if os.path.splitext(f)[1].lower() in wanted
                 and os.path.isfile(os.path.join(input_dir, f))]
    return sorted(found)


def natural_key(s):
    """Sort key that orders V2 before V10 (plain string sort does not)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def group_images(paths, input_dir, regex=None):
    """{group label: [paths]} — the units the picker walks through, in natural order."""
    groups = {}
    for p in paths:
        if regex:
            m = re.search(regex, os.path.basename(p))
            # EVERY capture group, joined: r"(V\d+)[-_](pos|neg)" gives "V1 neg", so the picker
            # walks well AND condition. With only the well captured it walks wells, and the
            # user clicking the first field each time can land the whole training set on one
            # condition — which happened on a real pos-vs-neg comparison.
            key = ((" ".join(g for g in m.groups() if g) if m.groups() else m.group(0))
                   if m else "unmatched")
        else:
            rel = os.path.relpath(os.path.dirname(p), input_dir)
            key = "all images" if rel in (".", "") else rel
        groups.setdefault(key, []).append(p)
    return {k: groups[k] for k in sorted(groups, key=natural_key)}


def to_uint8(arr):
    """8-bit, [0,255]. micro_sam's loader check REJECTS anything outside that range, and the
    human must see exactly what the model trains on — so the conversion happens once, here."""
    arr = np.asarray(arr)
    if arr.dtype == np.uint8:
        return arr
    a = arr.astype(np.float32)
    lo, hi = np.percentile(a, 0.1), np.percentile(a, 99.9)
    if hi <= lo:
        lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return np.zeros(a.shape, np.uint8)
    return np.clip((a - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def read_image(path):
    """Read one image and reduce it to what the annotator shows: 2D grayscale or HxWx3 RGB."""
    if path.lower().endswith((".tif", ".tiff")):
        img = tifffile.imread(path)
    else:
        import imageio.v3 as imageio
        img = imageio.imread(path)
    img = np.squeeze(np.asarray(img))

    if img.ndim == 2:
        pass
    elif img.ndim == 3 and img.shape[-1] in (3, 4):
        img = img[..., :3]                                  # RGB (drop alpha)
    elif img.ndim == 3:
        if CHANNEL is None:
            raise ValueError(
                f"{os.path.basename(path)} is 3D with shape {img.shape} (channels or z-slices), "
                f"so CHANNEL must be set. Use an int 0..{img.shape[0] - 1} to pick the plane the "
                f"objects are visible in, or \"max\" for a maximum projection. Refusing to guess: "
                f"annotating the wrong channel wastes the whole session."
            )
        img = img.max(axis=0) if CHANNEL == "max" else img[int(CHANNEL)]
    else:
        raise ValueError(f"{os.path.basename(path)}: unsupported shape {img.shape} (ndim={img.ndim}).")
    return to_uint8(img)


def as_gray(img):
    return img.mean(axis=-1) if img.ndim == 3 else img


def clamp_tile(y, x, tile, shape):
    """A tile CENTRED on (y, x), pushed back inside the image. Returns (y0, x0)."""
    h, w = shape[:2]
    y0 = int(round(y - tile / 2))
    x0 = int(round(x - tile / 2))
    return max(0, min(y0, h - tile)), max(0, min(x0, w - tile))


def overlaps(cand, chosen, tile, limit=0.25):
    """True if cand covers more than `limit` of an already-chosen tile from the same image."""
    for o in chosen:
        if o["path"] != cand["path"]:
            continue
        dy = tile - abs(cand["y0"] - o["y0"])
        dx = tile - abs(cand["x0"] - o["x0"])
        if dy > 0 and dx > 0 and (dy * dx) > limit * tile * tile:
            return True
    return False


def foreground_mask(gray):
    """Boolean object mask, working for BOTH polarities.

    Otsu splits the histogram; which side holds the objects depends on the modality —
    fluorescence is bright-on-dark, brightfield/histology is dark-on-bright. Assuming
    bright-is-signal (the usual default) inverts the score on every brightfield slide, so
    the "best" tile becomes the emptiest one. Objects are the minority class either way,
    so take whichever side covers less of the frame."""
    sm = gaussian(gray.astype(np.float32), 2, preserve_range=True)
    thr = threshold_otsu(sm)                # raises ValueError on a flat image — caller handles
    bright = sm > thr
    frac = float(bright.mean())
    return bright if frac <= 0.5 else ~bright


def rank_tiles(img, tile):
    """auto mode only. Cheap content score per candidate tile position: how many separate
    blobs it holds. Only used to AVOID handing the human empty sky or one giant saturated
    smear. It counts BLOBS, not cells — debris scores exactly like a nucleus, which is why
    PICK_MODE = "interactive" is the default."""
    gray = as_gray(img).astype(np.float32)
    try:
        fg_full = foreground_mask(gray)
    except ValueError:
        return []
    h, w = gray.shape
    out = []
    # 50 % overlap: a stride of a full tile can straddle every dense region unluckily.
    step = max(tile // 2, 1)
    for y0 in range(0, max(h - tile, 0) + 1, step):
        for x0 in range(0, max(w - tile, 0) + 1, step):
            patch = fg_full[y0:y0 + tile, x0:x0 + tile]
            frac = float(patch.mean())
            if frac < 0.005 or frac > 0.85:      # empty, or one saturated blob / artefact
                continue
            out.append({"y0": int(y0), "x0": int(x0), "score": int(cc_label(patch).max()), "frac": frac})
    out.sort(key=lambda d: -d["score"])
    return out


def measure_tile_size(probe_segs, min_dim, target=None, floor=256, ceil=1024):
    """Pick the tile size from how densely the objects actually sit, not from a guess.

    `probe_segs` is [(label image, its area in px)] from the stock model on one field per
    group. A tile should hold about `target` objects: at density d objects per px^2 that is
    a side of sqrt(target / d). Clamped to [floor, ceil] — below the floor a tile is too
    small to give SAM context, above 1024 it is being downscaled anyway, since SAM resizes
    whatever it is handed to 1024 — and to the smallest image, then rounded to a multiple of 64.

    Returns (tile, why) so the choice can be printed and put in the manifest.
    """
    target = target or TARGET_OBJECTS_PER_TILE
    n = sum(int(lab.max()) for lab, _ in probe_segs)
    area = sum(a for _, a in probe_segs)
    if not n or not area:
        t = int(min(512, min_dim))
        return t, f"no objects found on the probe fields; falling back to {t} px"
    density = n / area
    ideal = (target / density) ** 0.5
    t = int(round(min(max(ideal, floor), ceil, min_dim) / 64.0)) * 64
    t = int(min(max(t, 64), min_dim))
    per_tile = density * t * t
    why = (f"{n} objects over {area / 1e6:.1f} MP on the probe fields = 1 per "
           f"{1 / density / 1000:.0f}k px; {target} of them need ~{ideal:.0f} px, "
           f"using {t} px (~{per_tile:.0f} objects per tile)")
    if per_tile < 0.5 * target:
        # The objects are too sparse to reach the target within a tile SAM can still see
        # properly (it resizes everything to 1024, so a bigger tile only shrinks them).
        # More tiles is the answer, not a bigger one — say so rather than quietly under-deliver.
        why += (f". These objects are sparse: even at the {ceil} px ceiling a tile holds only "
                f"~{per_tile:.0f}. Raise N_TILES to about "
                f"{max(6, int(round(target * 6 / max(per_tile, 1))))} so the whole set still "
                f"carries enough objects to train on")
    return t, why


class MicroSamBackend:
    """Stock micro_sam AIS. `segment(img, tile)` is the whole interface the picker needs."""

    label = "micro_sam"

    def __init__(self, model_type, checkpoint, device, is_tiled):
        from micro_sam.automatic_segmentation import get_predictor_and_segmenter
        self.predictor, self.segmenter = get_predictor_and_segmenter(
            model_type=model_type, checkpoint=checkpoint, device=device,
            segmentation_mode="ais", is_tiled=is_tiled,
        )

    def segment(self, img, tile_shape=None):
        return segment_field(self.predictor, self.segmenter, img, tile_shape)

    def close(self):
        pass


class CellposeBackend:
    """Cellpose reached across the conda-env boundary by a resident subprocess.

    cellpose and napari cannot share an interpreter here — `napari-mcp` has napari and
    micro_sam but no cellpose, and `cellpose4` has cellpose but no napari, no skimage and no
    imageio. The picker must run where napari is, so segmentation crosses as a subprocess over
    TIFFs. The worker is kept ALIVE in `--serve` mode: cpsam takes ~10 s to load and the picker
    segments a new field every time the user asks for one, so a process per field would make it
    unusable.

    Note what this backend does NOT do: tiling. cpsam has no fixed input resolution to fight, so
    a field is segmented whole and `tile_shape` is accepted and ignored.
    """

    label = "cellpose"
    WORKER = ("/app/skills/python/cellpose/"
              "WORKFLOW_FINETUNE_CP_SEGMENT_WORKER.py")
    PYTHON = "/opt/conda/envs/cellpose4/bin/python"

    def __init__(self, checkpoint, work_dir, diameter=None, cp_model="cpsam"):
        import subprocess
        import tempfile

        if not os.path.exists(self.WORKER):
            raise SystemExit(f"Cellpose backend needs {self.WORKER}, which is missing.")
        self._tmp = tempfile.mkdtemp(prefix="cpseg_", dir=work_dir)
        setup = os.path.join(self._tmp, "setup.json")
        with open(setup, "w") as f:
            # A round-2 checkpoint wins over the stock name; otherwise the configured model.
            json.dump({"pretrained_model": checkpoint or cp_model, "diameter": diameter}, f)
        self.proc = subprocess.Popen(
            [self.PYTHON, self.WORKER, "--serve", setup],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )
        ready = self._read_until("model_ready")
        print(f"[prepare] cellpose worker up: {ready.get('pretrained')} "
              f"({'GPU' if ready.get('gpu') else 'CPU'})")
        self._n = 0

    def _read_until(self, event):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SystemExit("The cellpose worker died before it was ready. Check that the "
                                 "cellpose4 env exists and that a GPU/CPU torch is importable.")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("event") == event:
                return msg

    def segment(self, img, tile_shape=None):
        self._n += 1
        src = os.path.join(self._tmp, f"in_{self._n}.tif")
        dst = os.path.join(self._tmp, f"out_{self._n}.tif")
        tifffile.imwrite(src, img)
        self.proc.stdin.write(json.dumps({"pairs": [[src, dst]]}) + "\n")
        self.proc.stdin.flush()
        self._read_until("summary")
        out = tifffile.imread(dst) if os.path.exists(dst) else np.zeros(img.shape[:2], np.uint16)
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
        return np.asarray(out)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def build_backend(name, model_type, checkpoint, device, is_tiled, work_dir, cp_model="cpsam"):
    if name == "cellpose":
        return CellposeBackend(checkpoint, work_dir, cp_model=cp_model)
    if name == "micro_sam":
        return MicroSamBackend(model_type, checkpoint, device, is_tiled)
    raise SystemExit(f'SEGMENT_BACKEND must be "micro_sam" or "cellpose", got {name!r}')


def find_base_checkpoint(task_dir, model_type, setting="auto"):
    """The fine-tuned model to build on, or None to start from stock.

    Iterating matters more than any single round: round 1 teaches the obvious cases, and the
    tiles worth annotating in round 2 are the ones the ROUND-1 model still gets wrong. Showing
    the stock model's guess again wastes the user's time on errors that are already fixed.

    "auto" looks in this task folder first, then in sibling folders (people run round 2 in a
    new directory), taking the newest round whose stage 3 actually promoted a checkpoint. It
    prints what it found: silently training on top of a different model than the user expects
    is the failure this must never cause.
    """
    if setting is None:
        return None
    if setting != "auto":
        if not os.path.exists(setting):
            raise SystemExit(f"BASE_CHECKPOINT does not exist: {setting}")
        return setting

    cands = []
    here = sorted(glob.glob(os.path.join(task_dir, "model", f"*_{model_type}.pt")))
    cands += [(os.path.getmtime(p), p, task_dir) for p in here]
    parent = os.path.dirname(os.path.abspath(task_dir))
    for ev in glob.glob(os.path.join(parent, "*", "evaluation.json")):
        if os.path.dirname(os.path.abspath(ev)) == os.path.abspath(task_dir):
            continue
        try:
            with open(ev) as f:
                data = json.load(f)
        except Exception:
            continue
        ckpt = data.get("recommended_checkpoint")
        if ckpt and os.path.exists(ckpt) and data.get("model_type") == model_type:
            cands.append((os.path.getmtime(ckpt), ckpt, os.path.dirname(ev)))
    if not cands:
        return None
    _, best, where = max(cands)
    print(f"[prepare] ROUND 2+: starting from the model fine-tuned in {where}\n"
          f"          {best}\n"
          f"          The picker will show what THAT model gets wrong, not the stock model.")
    return best


def segment_field(predictor, segmenter, img, tile_shape=None):
    """Stock segmentation of a whole field, tiled at `tile_shape` when the field is bigger.

    Same tiling rule as stage 4: SAM resizes whatever it is given to 1024 px, so a field fed
    whole shows its objects at a different size than a tile does, and the outlines the user is
    judging would not be the ones the model produces on the tiles.

    `tile_shape=None` means NEVER tile — that is the per-tile pre-segmentation, where the crop
    is already at the scale the model will be trained and applied at and tiling it again would
    only add seams.
    """
    from micro_sam.automatic_segmentation import automatic_instance_segmentation
    kw = {}
    if tile_shape is not None:
        # No second size test here. The segmenter object was built tiled-or-not from this
        # same flag, and micro_sam accepts tiled embeddings ONLY in the Tiled* class and
        # untiled ones only in the plain class — so a per-image test that disagreed with
        # the caller broke both ways ('batch_size'/'Group'.ndim one way, .attrs the other).
        # A tile_shape larger than the image is harmless: micro_sam clips it to one tile.
        kw = dict(tile_shape=(tile_shape, tile_shape), halo=(max(tile_shape // 8, 32),) * 2)
    return np.asarray(automatic_instance_segmentation(
        predictor=predictor, segmenter=segmenter, input_path=img, ndim=2,
        verbose=False, **kw)).astype(np.uint32)


def overlay_png(img, labels, path):
    rgb = np.repeat(as_gray(img).astype(np.uint8)[..., None], 3, axis=-1) if img.ndim == 2 else img.copy()
    rgb = rgb.astype(np.uint8)
    if labels is not None and labels.max() > 0:
        rgb[find_boundaries(labels, mode="outer")] = (255, 60, 60)
    import imageio.v3 as imageio
    imageio.imwrite(path, rgb)


# ==============================================================================
#  INTERACTIVE TILE PICKER
# ==============================================================================
def pick_tiles_interactive(groups, tile, n_tiles, segment=None, preseg_cache=None):
    """Open napari, walk the user through one field per group, return the clicked tiles.

    `segment(img) -> label image` (optional) is the stock model. When given, every field is
    shown WITH the model's current segmentation on it, computed off the Qt thread so the
    window stays responsive, and the user is told to aim at the places it gets wrong — a tile
    where the model is already right teaches it nothing.

    Returns [{path, y0, x0, group}], in click order. BLOCKS until the window is closed.
    """
    import time

    import napari
    from concurrent.futures import ThreadPoolExecutor
    from qtpy.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
    from qtpy.QtCore import Qt, QTimer

    preseg_cache = dict(preseg_cache or {})
    pool = ThreadPoolExecutor(max_workers=1) if segment else None
    pending = {}                                          # path -> Future

    keys = list(groups)
    per_group = max(1, int(np.ceil(n_tiles / max(len(keys), 1))))

    print(f"\n[prepare] {len(keys)} group(s); target {n_tiles} tiles "
          f"(~{per_group} per group). Opening the picker ...")
    for k in keys:
        print(f"[prepare]   {k:<24} {len(groups[k])} image(s)")

    st = {"gi": 0, "fi": {k: 0 for k in keys}, "picks": [],
          "img": None, "path": None, "layer": None, "seg": None, "n_seg": 0,
          "auto": AUTO_ADVANCE, "t0": time.time()}

    viewer = napari.Viewer(title="ImagentJ — pick the tiles to annotate")
    # Edge width is in DATA units, so it has to scale with the tile or the box is a hairline
    # on a 2048 px field; and the boxes need a translucent FACE — an outline alone is easy to
    # lose against textured tissue, and the square is the one thing the user is aiming with.
    edge = max(5.0, tile / 48.0)
    # The fill only has to say "this region"; keep it faint, because the cells the user is
    # judging are INSIDE it and a strong tint hides exactly what they came to look at.
    ghost = viewer.add_shapes(name="tile under cursor", face_color=[1.0, 0.83, 0.0, 0.09],
                              edge_color="#ffc400", edge_width=edge, opacity=1.0)
    placed = viewer.add_shapes(name="picked tiles", face_color=[0.0, 1.0, 0.53, 0.12],
                               edge_color="#00e87a", edge_width=edge, opacity=1.0)
    seg_layer = None
    if segment:
        seg_layer = viewer.add_labels(np.zeros((2, 2), np.uint32),
                                      name="what the model does now", opacity=0.45)

    # Hide napari's own layer list and layer controls: this window has exactly one job, and
    # every control in them is a way to break it (hiding the field, editing a box by hand).
    # They stay reachable from the View menu.
    for dock in ("dockLayerList", "dockLayerControls"):
        try:
            getattr(viewer.window._qt_viewer, dock).setVisible(False)
        except AttributeError:
            pass
    # Open full-screen. The whole task is judging which patch of a 2048 px field holds good
    # cells, and a window manager's default ~1000 px window shows them at a quarter size.
    try:
        viewer.window._qt_window.showMaximized()
    except Exception:
        pass

    def show_field(img):
        """Put `img` on screen, under the two box layers.

        An Image layer is created grayscale or RGB and cannot switch afterwards, and a folder
        can mix the two — so replace the layer whenever the kind changes, and push it back to
        the bottom so the tile boxes stay visible on top of it."""
        lay, rgb = st.get("layer"), img.ndim == 3
        if lay is None or bool(lay.rgb) != rgb:
            if lay is not None:
                viewer.layers.remove(lay)
            lay = viewer.add_image(img, name="field", rgb=rgb)
            viewer.layers.move(viewer.layers.index(lay), 0)
            st["layer"] = lay
        else:
            lay.data = img
        viewer.layers.selection.active = lay              # so scroll = zoom, drag = pan

    # ---- widgets -------------------------------------------------------------
    panel = QWidget()
    lay = QVBoxLayout(panel)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(6)

    def _label(txt, size=11, bold=False, colour=None, wrap=False):
        w = QLabel(txt)
        w.setWordWrap(wrap)
        style = f"font-size:{size}pt;" + ("font-weight:bold;" if bold else "")
        if colour:
            style += f"color:{colour};"
        w.setStyleSheet(style)
        return w

    head = _label("", 14, True)
    sub = _label("", 9, colour="#aaaaaa", wrap=True)
    if segment:
        how = _label("The coloured blobs are what the model does <b>today</b>. Click where it "
                     "gets it <b>wrong</b> — cells it missed, two cells merged into one blob, "
                     "debris it outlined.<br><br>"
                     "Take one or two spots where it is <b>right</b> too, so it does not forget "
                     "what a correct answer looks like.<br>"
                     "Nothing interesting on this field? Press \u201cShow me another field\u201d.",
                     10, wrap=True)
        how.setTextFormat(Qt.RichText)
    else:
        how = _label("Click on a patch of cells you want to annotate.\n"
                     "The yellow square shows exactly what you will get.\n\n"
                     "Pick somewhere with plenty of cells and no big lumps of debris — this "
                     "square is what the model learns from.\n"
                     "Empty, blurry or dirty everywhere? Press \u201cShow me another field\u201d.",
                     10, wrap=True)
    count = _label("", 12, True, "#00cc77")
    lay.addWidget(head)
    lay.addWidget(sub)
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color:#444;")
    lay.addWidget(line)
    lay.addWidget(how)
    lay.addWidget(count)

    def _button(txt, tip, colour=None):
        b = QPushButton(txt)
        b.setToolTip(tip)
        b.setMinimumHeight(30)
        if colour:
            b.setStyleSheet(f"font-weight:bold; background-color:{colour}; color:white;")
        lay.addWidget(b)
        return b

    btn_field = _button("↻  Show me another field", "Same group, next image — use this if "
                                                   "this field is empty, blurry or all debris")
    btn_next = _button("Next group  ▶", "Move on to the next group")
    btn_stay = _button("⏸  Stay on this field",
                       "Stop jumping to the next group after each square, so you can take "
                       "several from one image. Press “Next group” when you are done here.")
    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    btn_prev = QPushButton("◀  Back")
    btn_undo = QPushButton("Undo last square")
    for b in (btn_prev, btn_undo):
        b.setMinimumHeight(28)
        rl.addWidget(b)
    lay.addWidget(row)
    btn_done = _button("✓  DONE — I have picked my tiles", "Close the picker and pre-segment "
                                                           "the tiles you chose", "#0a7d43")
    lay.addStretch(1)
    lay.addWidget(_label("Scroll = zoom · drag = pan · the square is placed where you click.",
                         8, colour="#888888", wrap=True))
    viewer.window.add_dock_widget(panel, area="right", name="Pick tiles")

    # ---- state -> screen -----------------------------------------------------
    def rect(y0, x0):
        return np.array([[y0, x0], [y0, x0 + tile], [y0 + tile, x0 + tile], [y0 + tile, x0]])

    def refresh_boxes():
        here = [p for p in st["picks"] if p["path"] == st["path"]]
        placed.data = [rect(p["y0"], p["x0"]) for p in here]
        n, target = len(st["picks"]), n_tiles
        mine = len([p for p in st["picks"] if p["group"] == keys[st["gi"]]])
        extra = ""
        if seg_layer is not None:
            extra = ("   ·   segmenting this field ..." if st["seg"] is None
                     else f"   ·   model finds {st['n_seg']} objects here")
        count.setText(f"{n} of {target} tiles picked   ·   this group: {mine}{extra}")
        enough = n >= max(4, target)
        btn_done.setText("✓  DONE — I have picked my tiles" if enough
                         else f"✓  DONE (pick {max(4, target) - n} more for a good model)")

    def load_field():
        """Show this group's current field, skipping past any file that will not open.

        A file that fails to read must not leave the PREVIOUS field on screen: the header
        would say the new group while a click recorded the old group's file. Skip forward
        instead, and if the whole group is unreadable, blank the state so clicks do nothing."""
        key = keys[st["gi"]]
        files = groups[key]
        img = path = None
        for _ in range(len(files)):
            path = files[st["fi"][key] % len(files)]
            try:
                img = read_image(path)
                break
            except Exception as exc:
                print(f"  ! skipping {os.path.basename(path)}: {exc}")
                st["fi"][key] += 1
                img = None
        if img is None:
            st["img"], st["path"] = None, None
            head.setText(f"{key}      (group {st['gi'] + 1} of {len(keys)})")
            sub.setText("none of this group's images could be opened — press “Next group ▶”")
            placed.data = []
            return
        idx = st["fi"][key] % len(files)
        st["img"], st["path"] = img, path
        ghost.data = []                                   # no stale box from the last field
        show_field(img)
        viewer.reset_view()
        head.setText(f"{key}      (group {st['gi'] + 1} of {len(keys)})")
        sub.setText(f"{os.path.basename(path)}\nfield {idx + 1} of {len(files)} in this group "
                    f"·  {img.shape[1]} × {img.shape[0]} px")
        show_segmentation(path, img)
        refresh_boxes()

    def show_segmentation(path, img):
        """Put the model's current answer on the field, computing it off the Qt thread.

        Segmenting a 2048 px field takes seconds; doing it inline would freeze the window on
        every click of "another field". So the result is fetched in a worker and picked up by
        the timer below, and the panel says so meanwhile."""
        if seg_layer is None:
            return
        if preseg_cache.get(path) is not None:
            st["seg"] = preseg_cache[path]
            st["n_seg"] = int(st["seg"].max())
            seg_layer.data = st["seg"]
            return
        st["seg"], st["n_seg"] = None, 0
        seg_layer.data = np.zeros(as_gray(img).shape, np.uint32)
        if path not in pending:
            pending[path] = pool.submit(segment, img)

    # ---- interaction ---------------------------------------------------------
    @viewer.mouse_move_callbacks.append
    def _ghost(_v, event):
        if st["img"] is None:
            return
        y, x = event.position[:2]
        y0, x0 = clamp_tile(y, x, tile, st["img"].shape)
        ghost.data = [rect(y0, x0)]

    @viewer.mouse_drag_callbacks.append
    def _place(_v, event):
        """Place a tile on a CLICK. A drag is a pan, and must not drop a tile."""
        start = event.position
        moved = False
        yield
        while event.type == "mouse_move":
            moved = True
            yield
        if moved or st["img"] is None:
            return
        y0, x0 = clamp_tile(start[0], start[1], tile, st["img"].shape)
        cand = {"path": st["path"], "y0": y0, "x0": x0, "group": keys[st["gi"]]}
        if overlaps(cand, st["picks"], tile):
            sub.setText(sub.text().split("\n")[0] + "\n⚠ that overlaps a square you already "
                                                    "placed here — pick somewhere else")
            return
        st["picks"].append(cand)
        print(f"  + {cand['group']:<16} {os.path.basename(cand['path'])}  y={y0} x={x0}",
              flush=True)
        refresh_boxes()
        mine = len([p for p in st["picks"] if p["group"] == keys[st["gi"]]])
        if st["auto"] and mine >= per_group and st["gi"] < len(keys) - 1:
            # Quota reached: move on by itself, so covering ten wells is ten clicks. The
            # short delay is not cosmetic — jumping instantly makes the click feel like it
            # did not register, because the box the user just placed disappears with it.
            if ADVANCE_DELAY_MS > 0:
                QTimer.singleShot(ADVANCE_DELAY_MS, go_next)
            else:
                go_next()

    def go_next(*_):
        if st["gi"] < len(keys) - 1:
            st["gi"] += 1
            load_field()
        else:
            head.setText("All groups covered ✓")
            sub.setText("Click DONE, or go Back to add more squares.")

    def go_prev(*_):
        if st["gi"] > 0:
            st["gi"] -= 1
            load_field()

    def other_field(*_):
        st["fi"][keys[st["gi"]]] += 1
        load_field()

    def toggle_auto(*_):
        st["auto"] = not st["auto"]
        btn_stay.setText("⏸  Stay on this field" if st["auto"]
                         else "▶  Auto-advance is OFF — turn back on")
        btn_stay.setStyleSheet("" if st["auto"] else "font-weight:bold; color:#ffc400;")
        refresh_boxes()

    def undo(*_):
        """Remove the last square — the one on THIS field if there is one, otherwise the
        last one placed anywhere, jumping back to it so the user sees what disappeared.
        Silently deleting a square from a group that is no longer on screen is the one way
        this button can lie."""
        if not st["picks"]:
            return
        here = [i for i, p in enumerate(st["picks"]) if p["path"] == st["path"]]
        gone = st["picks"].pop(here[-1] if here else len(st["picks"]) - 1)
        print(f"  - undo {gone['group']} y={gone['y0']} x={gone['x0']}")
        if not here:                                       # it was on another group's field
            st["gi"] = keys.index(gone["group"])
            st["fi"][gone["group"]] = groups[gone["group"]].index(gone["path"])
            load_field()
        else:
            refresh_boxes()

    btn_next.clicked.connect(go_next)
    btn_prev.clicked.connect(go_prev)
    btn_field.clicked.connect(other_field)
    btn_stay.clicked.connect(toggle_auto)
    btn_undo.clicked.connect(undo)
    def finish(*_):
        """DONE, but not by accident. A real session ended with ONE tile because the button
        was pressed after the first click; stage 1 then produced a task nobody could train on."""
        need = max(4, min(n_tiles, len(keys)))
        if len(st["picks"]) < need:
            from qtpy.QtWidgets import QMessageBox
            ans = QMessageBox.question(
                panel, "Finish already?",
                f"You have picked {len(st['picks'])} square(s), out of {n_tiles}.\n\n"
                f"Training needs at least {need} — below that the model cannot be trained or "
                f"measured, and the annotation work is wasted.\n\nStop anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        viewer.close()

    btn_done.clicked.connect(finish)
    viewer.bind_key("n", lambda *_: go_next(), overwrite=True)
    viewer.bind_key("f", lambda *_: other_field(), overwrite=True)
    viewer.bind_key("u", lambda *_: undo(), overwrite=True)

    def heartbeat():
        """Say, on stdout, that this script is waiting for a person.

        The run watchdog kills a script that produces no output for 180 s, and an
        interactive picker is silent by nature — a real session was killed at 52 min with
        "no output for 3150s", losing every tile the user had placed. Printing progress is
        what makes the silence signal mean something, so it has to be explicit that the wait
        is intended and how far along the human is."""
        mins = (time.time() - st["t0"]) / 60.0
        print(f"[prepare] waiting for the user — {len(st['picks'])} of {n_tiles} squares "
              f"picked, group {st['gi'] + 1}/{len(keys)}, window open {mins:.0f} min. "
              f"This script is MEANT to sit here until they press DONE.", flush=True)

    def poll():
        """Collect finished segmentations and keep the counter line honest."""
        for path, fut in list(pending.items()):
            if fut.done():
                pending.pop(path)
                try:
                    preseg_cache[path] = fut.result()
                except Exception as exc:                  # one bad field must not kill the picker
                    print(f"  ! could not segment {os.path.basename(path)}: {exc}")
                    preseg_cache[path] = None
                if path == st["path"] and preseg_cache[path] is not None:
                    st["seg"] = preseg_cache[path]
                    st["n_seg"] = int(st["seg"].max())
                    seg_layer.data = st["seg"]
                    refresh_boxes()          # only when something actually arrived: this runs
                                             # 2.5x a second and rebuilds the box mesh

    timer = None
    if seg_layer is not None:
        timer = QTimer()
        timer.timeout.connect(poll)
        timer.start(400)
    beat = QTimer()
    beat.timeout.connect(heartbeat)
    beat.start(45_000)                                    # < the watchdog's 180 s silence limit

    load_field()
    heartbeat()
    napari.run()                                          # blocks until the window is closed
    beat.stop()
    if timer is not None:
        timer.stop()
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
    print(f"[prepare] picker closed — {len(st['picks'])} tile(s) chosen")
    return st["picks"]


# ==============================================================================
def pick_tiles_auto(groups, tile, n_tiles, shapes_out):
    """No window: rank grid positions by blob count and spread the tiles over the groups.

    Reviewed-by-nobody tiles. Only for unattended runs — see the warning it prints."""
    rng = np.random.default_rng(SEED)
    keys = list(groups)
    per_group = max(1, int(np.ceil(n_tiles / max(len(keys), 1))))

    scan = []
    for k in keys:                                        # round-robin so the cap cannot
        scan += groups[k][:max(1, MAX_IMAGES_SCANNED // max(len(keys), 1))]   # starve a group
    scan = scan[:MAX_IMAGES_SCANNED]

    by_group = {k: [] for k in keys}
    for p in scan:
        try:
            img = read_image(p)
        except Exception as exc:                          # one bad file must not kill the run
            print(f"  ! skipping {os.path.basename(p)}: {exc}")
            continue
        shapes_out[p] = as_gray(img).shape
        key = next(k for k in keys if p in groups[k])
        for c in rank_tiles(img, tile):
            c.update(path=p, group=key)
            by_group[key].append(c)
        del img                                           # free it: these are multi-megapixel
    if not shapes_out:
        raise RuntimeError("No readable images.")

    for k in keys:
        rng.shuffle(by_group[k])                          # break score ties without position bias
        by_group[k].sort(key=lambda c: -c["score"])

    selected, per_image = [], MAX_TILES_PER_IMAGE or max(1, int(np.ceil(n_tiles / max(len(scan), 1))))
    for quota in (per_group, n_tiles):                    # widen only if a group ran dry
        for k in keys:
            taken = len([s for s in selected if s["group"] == k])
            for c in by_group[k]:
                if len(selected) >= n_tiles or taken >= quota:
                    break
                if overlaps(c, selected, tile):
                    continue
                if len([s for s in selected if s["path"] == c["path"]]) >= per_image:
                    continue
                selected.append(c)
                taken += 1
        if len(selected) >= n_tiles:
            break
    if not selected:                                      # flat / very low-contrast data
        print("[prepare] content ranking found nothing; falling back to centre crops")
        for p, (h, w) in list(shapes_out.items())[:n_tiles]:
            selected.append({"path": p, "y0": (h - tile) // 2, "x0": (w - tile) // 2,
                             "score": 0, "frac": 0.0,
                             "group": next(k for k in keys if p in groups[k])})
    print("[prepare] " + "!" * 70)
    print("[prepare] AUTO mode: these tiles were chosen by a blob count, which cannot tell a "
          "dust\n[prepare] speck from a cell. LOOK AT previews/ BEFORE anyone annotates them.")
    print("[prepare] " + "!" * 70)
    return selected


def main():
    import torch          # local: keeps this module importable (and its helpers
                          # unit-testable) without the GPU stack loaded

    dirs = {k: os.path.join(TASK_DIR, k)
            for k in ("tiles", "presegmentation", "annotations", "previews", "embeddings")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    ensure_model_cache(os.path.join(TASK_DIR, ".micro_sam_cache"))

    # --- 1. find the images and split them into groups --------------------------------
    recursive = RECURSIVE
    paths = list_images(INPUT_DIR, EXTS, recursive)
    if not paths and not recursive:
        paths = list_images(INPUT_DIR, EXTS, recursive=True)
        recursive = bool(paths)
        if paths:
            print(f"[prepare] nothing in {INPUT_DIR} itself; found {len(paths)} image(s) in "
                  f"sub-folders — searching recursively")
    if not paths:
        raise FileNotFoundError(
            f"No images with extension {sorted(EXTS)} (any case) in {INPUT_DIR}"
            + ("" if recursive else " or its sub-folders"))
    groups = group_images(paths, INPUT_DIR, GROUP_REGEX)
    n_tiles = N_TILES or max(6, len(groups))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_type = MODEL_TYPE or ("vit_b_lm" if device == "cuda" else "vit_t_lm")
    base_ckpt = find_base_checkpoint(TASK_DIR, model_type, BASE_CHECKPOINT)
    print(f"[prepare] {len(paths)} image(s) in {len(groups)} group(s); {model_type} on {device}"
          + ("  [continuing from a fine-tuned checkpoint]" if base_ckpt else ""))

    # --- 2. probe the data, then settle on a tile size ---------------------------------
    shapes, probes = {}, {}
    for p in [g[0] for g in groups.values()]:              # one probe per group is enough
        try:
            probes[p] = read_image(p)
            shapes[p] = as_gray(probes[p]).shape
        except Exception as exc:
            print(f"  ! skipping {os.path.basename(p)}: {exc}")
    if not shapes:
        raise RuntimeError("No readable images.")
    min_dim = min(min(s) for s in shapes.values())

    show_preseg = (device == "cuda") if SHOW_PRESEG == "auto" else bool(SHOW_PRESEG)
    if SHOW_PRESEG == "auto" and not show_preseg:
        print("[prepare] no GPU: the picker will show the images without the model's current "
              "segmentation (it would take minutes per field on CPU).")

    backend = None
    tile_why = f"TILE_SIZE={TILE_SIZE} from the config"
    if TILE_SIZE is None or show_preseg:
        # The model is needed for the probe segmentation, and the probe answers two questions
        # at once: how big a tile should be, and what the picker shows the user.
        print(f"[prepare] building "
              f"{SEGMENT_BACKEND + ' (' + CP_MODEL + ')' if SEGMENT_BACKEND == 'cellpose' else SEGMENT_BACKEND}"
              f"{' + fine-tuned weights' if base_ckpt else ''} on {device} ...")
        # is_tiled MUST agree with segment_field()'s own tiling test (`max(h, w) >
        # tile_shape`) — micro_sam only accepts tiled embeddings in the Tiled* segmenter
        # class, and get_predictor_and_segmenter picks the class from this flag alone.
        # Deciding it on the MIN dimension while segment_field decides on the MAX one made
        # the two disagree for any image with min(dim) <= 512 < max(dim) (e.g. 507x676),
        # and micro_sam reports that mismatch as `initialize() got an unexpected keyword
        # argument 'batch_size'`, or — once that is worked around — as `'Group' object has
        # no attribute 'ndim'`. Neither message names tiling, so derive both from one value.
        probe_tile = int(min(512, min_dim))
        tiled = max(max(s) for s in shapes.values()) > probe_tile
        probe_arg = probe_tile if tiled else None   # the ONLY tiling switch, used everywhere
        backend = build_backend(
            SEGMENT_BACKEND, model_type, base_ckpt, device,
            is_tiled=tiled, work_dir=TASK_DIR,
            cp_model=CP_MODEL,
        )
        print(f"[prepare] segmenting one field per group to measure the data "
              f"({len(probes)} field(s)) ...")
        probe_segs, preseg_cache = [], {}
        for p, img in probes.items():
            lab = backend.segment(img, probe_arg)
            preseg_cache[p] = lab
            probe_segs.append((lab, int(np.prod(as_gray(img).shape))))
            print(f"  {os.path.basename(p)[:44]:<46} {int(lab.max()):>4} objects")
    else:
        probe_segs, preseg_cache = [], {}

    if TILE_SIZE is None:
        tile, tile_why = measure_tile_size(probe_segs, min_dim)
        print(f"[prepare] tile size {tile} px — {tile_why}")
    else:
        tile = int(min(TILE_SIZE, min_dim))
        if tile < TILE_SIZE:
            tile_why = f"reduced {TILE_SIZE} -> {tile} px (smallest image dimension)"
            print(f"[prepare] tile size {tile_why}")
    if tile < 128:
        raise ValueError(f"Images are too small for tiled annotation (smallest dimension {min_dim} px).")

    # --- 3. choose the tiles ------------------------------------------------------------
    if PICK_MODE == "interactive":
        selected = pick_tiles_interactive(
            groups, tile, n_tiles,
            segment=((lambda img: backend.segment(img, probe_arg))
                     if show_preseg and backend is not None else None),
            preseg_cache=preseg_cache,
        )
        if not selected:
            raise RuntimeError(
                "No tiles were picked — the window was closed without a single click. "
                "Re-run this script and click on the fields you want to annotate.")
        if len(selected) < 4:
            print(f"[prepare] WARNING: only {len(selected)} tile(s). Stage 3 needs at least 3 "
                  f"for training plus 1 to validate on; 6-10 is the sweet spot.")
        for c in selected:                                 # only now, and only what is needed
            shapes.setdefault(c["path"], as_gray(read_image(c["path"])).shape)
    elif PICK_MODE == "auto":
        selected = pick_tiles_auto(groups, tile, n_tiles, shapes)
    else:
        raise ValueError(f"PICK_MODE must be 'interactive' or 'auto', not {PICK_MODE!r}")

    used = {}
    for c in selected:
        used[c["path"]] = used.get(c["path"], 0) + 1
    covered = sorted({c["group"] for c in selected}, key=natural_key)
    print(f"[prepare] {len(selected)} tiles of {tile}x{tile} px from {len(used)} image(s), "
          f"covering {len(covered)}/{len(groups)} group(s): {', '.join(map(str, covered))}")
    missed = [k for k in groups if k not in covered]
    if missed:
        print(f"[prepare] NOTE: no tile from {', '.join(map(str, missed))}.")

    # Re-read only the images a tile was actually cut from (cached: several tiles can share one).
    images = {p: read_image(p) for p in used}

    # One colour mode for the whole task. A folder can hold both grayscale and RGB files, and
    # the annotator shows the series in ONE napari image layer: the moment a (512,512,3) tile
    # follows a (512,512) one, napari reads the colour axis as a 512-slice stack and renders a
    # one-pixel-wide sliver — a black canvas with the masks floating on it, and no error. It
    # also gives torch_em two different input shapes to train on. If anything is colour,
    # everything becomes colour (never the reverse: dropping the channels can drop the stain).
    tile_mode = "rgb" if any(im.ndim == 3 for im in images.values()) else "gray"
    if tile_mode == "rgb" and any(im.ndim == 2 for im in images.values()):
        print(f"[prepare] mixed grayscale/RGB sources -> writing every tile as RGB")

    # One SCALE for the whole task. A fixed tile size cut from images of different sizes samples
    # different magnifications: a 512 px tile of a 512 px field and a 512 px tile of a 2048 px
    # field show the same object 4x apart, and SAM resizes both to 1024 regardless. The stock
    # generalist copes; a model fine-tuned on the mixture does not. Measured: 8 tiles from
    # 512/1024/2048 px sources made the model WORSE even with perfect labels (0.556 -> 0.515),
    # while the same tiles restricted to one source size behaved normally.
    src_dims = {p: max(shapes[p]) for p in used}
    spread = max(src_dims.values()) / max(min(src_dims.values()), 1)
    if spread >= 2:
        by_size = {}
        for p, d in src_dims.items():
            by_size.setdefault(d, []).append(os.path.basename(p))
        print(f"[prepare] " + "!" * 70)
        print(f"[prepare] WARNING: the tiles come from images {spread:.0f}x apart in size, so they "
              f"sample\n[prepare] {spread:.0f}x different magnifications. Fine-tuning on a mixture "
              f"of scales makes the model\n[prepare] WORSE, not better — even with perfect "
              f"annotations.")
        for d in sorted(by_size, reverse=True):
            print(f"[prepare]   {d:>5} px sources: {len(by_size[d])} tile(s)  "
                  f"({', '.join(n[:28] for n in by_size[d][:3])}{' ...' if len(by_size[d]) > 3 else ''})")
        print(f"[prepare] Point INPUT_DIR at one size class (or use GROUP_REGEX to separate them) "
              f"and re-run\n[prepare] BEFORE anyone annotates.")
        print(f"[prepare] " + "!" * 70)

    def as_mode(crop):
        if tile_mode == "rgb" and crop.ndim == 2:
            return np.repeat(crop[..., None], 3, axis=-1)
        return crop

    # --- 4. pre-segment each tile with the stock model ----------------------------------
    print(f"[prepare] pre-segmenting {len(selected)} tile(s) with "
          f"{'the ROUND-1 fine-tuned ' if base_ckpt else ''}"
          f"{SEGMENT_BACKEND} on {device} ...")
    # A FRESH, UNTILED backend: these are single tiles, already at the scale the model will be
    # trained and applied at, so tiling them again would only add seams.
    if backend is not None:
        backend.close()
    backend = build_backend(SEGMENT_BACKEND, model_type, base_ckpt, device,
                            is_tiled=False, work_dir=TASK_DIR, cp_model=CP_MODEL)

    entries = []
    for i, c in enumerate(selected):
        crop = as_mode(images[c["path"]][c["y0"]:c["y0"] + tile, c["x0"]:c["x0"] + tile])
        preseg = np.asarray(backend.segment(crop)).astype(np.uint32)

        stem = TILE_STEM.format(i)
        tile_path = os.path.join(dirs["tiles"], stem + ".tif")
        preseg_path = os.path.join(dirs["presegmentation"], stem + ".tif")
        tifffile.imwrite(tile_path, crop)
        tifffile.imwrite(preseg_path, preseg)
        overlay_png(crop, preseg, os.path.join(dirs["previews"], stem + ".png"))

        n = int(len(np.unique(preseg)) - 1)
        entries.append({
            "name": stem, "source": os.path.basename(c["path"]), "source_path": c["path"],
            "group": c.get("group"),
            "y0": int(c["y0"]), "x0": int(c["x0"]), "height": tile, "width": tile,
            "tile_path": tile_path, "preseg_path": preseg_path,
            # The annotator derives this name from the tile filename, so it is knowable now.
            # Stages 2/3 both rely on it; do not rename tiles after this point.
            "annotation_path": os.path.join(dirs["annotations"], stem + ".tif"),
            "preview_path": os.path.join(dirs["previews"], stem + ".png"),
            "n_preseg_objects": n,
        })
        print(f"  {stem}  [{c.get('group')}]  {os.path.basename(c['path'])}  "
              f"y={c['y0']} x={c['x0']}  preseg={n} objects")

    empty = [e["name"] for e in entries if e["n_preseg_objects"] == 0]
    if empty:
        print(f"[prepare] NOTE: {len(empty)} tile(s) pre-segmented to 0 objects ({', '.join(empty)}). "
              f"The human starts those from a blank canvas — normal when the stock model is a poor "
              f"fit, which is exactly when fine-tuning is worth doing.")

    counts = sorted(e["n_preseg_objects"] for e in entries)
    median = counts[len(counts) // 2]
    total = sum(counts)
    if median > 60:
        print(f"[prepare] WARNING: ~{median} objects per tile. Correcting that many by hand is "
              f"20+ min PER TILE, and people give up. Re-run with TILE_SIZE={max(tile // 2, 128)} "
              f"(and N_TILES={len(entries)}) — total annotated area drops 4x but the object count "
              f"per tile lands in the 10-40 range people actually finish.")
    elif median < 5:
        # The opposite failure, and the more insidious one: the tiles look fine, the human
        # annotates them, and stage 3 then has almost nothing to learn from — it drops every
        # tile with fewer than 2 objects outright. The two causes need different fixes, and
        # only the previews tell them apart.
        print(f"[prepare] WARNING: only ~{median} objects per tile ({total} in total). That is "
              f"thin training data — stage 3 discards any tile with fewer than 2 objects.")
        print(f"[prepare]   Open previews/*.png and see which of these it is:")
        print(f"[prepare]   - the tiles really are that empty -> re-run stage 1 and click on "
              f"DENSER patches (or raise TILE_SIZE to {min(tile * 2, 1024)}).")
        print(f"[prepare]   - the tiles are full of objects the outlines missed -> the stock "
              f"model is a poor fit, which is exactly the case fine-tuning fixes. Go ahead, but "
              f"expect the human to ADD most objects rather than correct them.")

    # Are the source images bigger than the tile? SAM resizes whatever it is given to 1024 px,
    # so a model trained on TILE-sized crops has learned objects at the apparent size they have
    # AFTER that resize. Feeding it a 4x larger image at inference shrinks every object 4x and
    # the fine-tuning gain evaporates. Stages 3/4 therefore run TILED inference at exactly this
    # tile size whenever the target images are larger — this flag is how they know.
    max_dim = max(max(s) for s in shapes.values())
    tiled_inference = bool(max_dim > tile)
    if tiled_inference:
        print(f"[prepare] source images up to {max_dim} px > tile {tile} px -> stages 3/4 will run "
              f"TILED inference at {tile} px so train and inference see objects at the same scale.")

    manifest = {
        "version": 2,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "input_dir": INPUT_DIR, "task_dir": TASK_DIR, "dirs": dirs,
        "model_type": model_type, "device_used": device,
        # WHICH model the user was shown and corrected. Stage 3 reads it and says so if it is
        # asked to train a different one — annotations are portable, but "the user fixed THIS
        # model's mistakes" is the claim that makes an active-learning round worth doing.
        "segment_backend": SEGMENT_BACKEND,
        # Which cellpose model the user was actually shown. Stage 3 reads this as its default
        # CP_MODEL so "corrected model" and "fine-tuned model" are the same one by construction.
        "cp_model": CP_MODEL if SEGMENT_BACKEND == "cellpose" else None,
        # None on round 1. On later rounds this is the model the user was shown and corrected,
        # and stage 3 both continues from it and measures against it.
        "base_checkpoint": base_ckpt,
        "tile_size": tile, "channel": CHANNEL, "seed": SEED,
        "pick_mode": PICK_MODE, "group_regex": GROUP_REGEX, "tile_mode": tile_mode,
        "source_size_spread": round(float(spread), 2),
        "tile_size_chosen_by": tile_why, "preseg_shown_in_picker": bool(show_preseg),
        "target_objects_per_tile": TARGET_OBJECTS_PER_TILE,
        "groups_total": len(groups), "groups_covered": len(covered),
        "tiled_inference": tiled_inference, "max_source_dim": int(max_dim),
        "n_tiles": len(entries), "n_source_images": len(used),
        "total_preseg_objects": total, "median_preseg_objects_per_tile": int(median),
        "tiles": entries,
    }
    if backend is not None:
        backend.close()          # a resident cellpose worker must not outlive this script

    with open(os.path.join(TASK_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(TASK_DIR, "ANNOTATION_INSTRUCTIONS.md"), "w") as f:
        f.write(build_instructions(manifest))

    print(f"\n[prepare] manifest      : {os.path.join(TASK_DIR, 'manifest.json')}")
    print(f"[prepare] instructions  : {os.path.join(TASK_DIR, 'ANNOTATION_INSTRUCTIONS.md')}")
    print(f"[prepare] tiles         : {len(entries)}  ({tile}x{tile} px)")
    print(f"[prepare] first guess   : {total} objects total, ~{total / max(len(entries), 1):.0f} per tile")
    print(f"[prepare] est. human time: {2 * len(entries)}-{4 * len(entries)} min")
    print("[prepare] NEXT -> WORKFLOW_FINETUNE_2_ANNOTATE.py with TASK_DIR = " + TASK_DIR)


def build_instructions(m):
    """The human-facing script. Generated (not static) so it carries this task's real numbers."""
    n, tile = m["n_tiles"], m["tile_size"]
    per = m["total_preseg_objects"] / max(n, 1)
    return f"""# Annotating {n} tiles for model fine-tuning

You are teaching the computer what a correct segmentation looks like. It has made a first
guess; your job is to fix it on **{n} small squares** ({tile} x {tile} pixels each,
about {per:.0f} objects per square). Roughly {2 * n}-{4 * n} minutes in total.

You do **not** annotate whole images and you do **not** annotate every cell in your dataset —
only everything inside these {n} small squares.

## The one rule

Inside the square, **every object must be outlined, and nothing else may be**.
Miss one and the computer learns "that is background". If an object is cut off by the edge of
the square, still include it.

**Leave the outlines that already look right alone.** You are checking the computer's work, not
redrawing it — an outline that follows the object is a correct answer even if you would have
drawn it a pixel or two differently. Only touch an outline that is clearly wrong: it covers two
objects, it covers half of one, or it is on something that is not an object at all.

## The window

A napari window opens with two layers listed on the left:

| layer | what it is |
|---|---|
| `image` | the tile |
| `committed_objects` | the computer's guess — one colour per object. **This is your answer sheet.** |

The **ImagentJ — Annotation Helper** panel on the right has everything you need: a tile
counter and four buttons. Use the buttons — they put napari into the right mode for you,
which is the one thing that is easy to get wrong.

## Three things to do

### ➕ ADD a missing object
1. Click **➕ ADD objects** in the helper panel (it turns green).
2. Left-click once **in the middle** of the object.
3. Press **S** → the outline appears (in `current_object`).
   - grabbed the neighbour too, or too much background? Press **T**, click on the part it
     should *not* include, press **S** again, then press **T** to go back.
   - still wrong? **Delete that one outline** (DELETE objects mode, or the **D** key with
     the mouse over it) and add it again. Do NOT reach for Shift+C / *Clear Annotations* —
     see the note under the key table.
4. Press **C** → the object turns into a new colour and joins `committed_objects`. Done.

> **Pressed C and nothing happened?** The thing you clicked is already outlined. The tool
> refuses to draw on top of an existing object — delete that outline first, then add it again.

### ✏ DRAW round objects
Use this when **ADD will not cooperate** — an outline the computer gets wrong however you
click it, or an object it keeps missing. Telling it *where* the object is often works where
telling it *what to click* does not.

1. Click **✏ DRAW round objects** in the helper panel (it turns purple).
2. **Click round the object**, then **double-click** to close the shape. Draw as many as you
   like before going on.
   - loose is fine. The computer uses the **box around** your shape, so tracing carefully
     buys nothing — aim, don't trace.
3. Press **S** → each shape is outlined.
4. Press **C** to keep them.

Same **S** and **C** as ADD — the only difference is what you gave the computer to work from.
You can mix the two: a shape round the object and a click inside it are both prompts.

> **Points not sticking as you click?** Press **✏ DRAW round objects** again. It switches to
> drag-a-rectangle, which always works and gives exactly the same result.

> If a neighbour creeps into the shape, press **ADD**, then **T** (the next click now means
> *exclude*), and click the neighbour. Then **S** again.

### ⌫ CLEAR my clicks & boxes
Removes the green/red dots and the shapes you drew. **Your outlines are not touched** — use
DELETE for those. Worth pressing whenever the picture gets cluttered: a leftover click from
an earlier object quietly joins the next **S**.

### ✖ DELETE a wrong object
1. Click **✖ DELETE objects** in the helper panel (it turns red).
2. Click on the wrong object → it disappears.

(Or just hover the mouse over it and press **D**.)

Delete anything that is not a real object (debris, dirt, a shadow), and anything the computer
got badly wrong. **To fix a bad outline, delete it and add it again** — that is faster and
safer than trying to repair it:

| problem | fix |
|---|---|
| object missing | ADD it |
| debris / background outlined | DELETE it |
| one outline covers two objects | DELETE it, then ADD each object separately |
| one object split into two outlines | DELETE both, then ADD it with one click |
| outline is badly off | DELETE it, then ADD it again |
| ADD keeps getting the same object wrong | DELETE it, then **DRAW** round it |
| objects packed tightly together | DELETE the clump, then **DRAW** round each one and exclude with **T** |

> **Tight clumps are the hard case.** One click inside a clump gives you the whole clump, and
> once that is committed every further click inside it is ignored — clicking more will not
> help. DELETE the clump first, then box one object at a time, adding an *exclude* click
> (**T**) on the neighbour that keeps coming along. If a clump is so dense that you cannot
> tell where one object ends and the next begins, leave it out and say so to whoever asked:
> a guess there is worse for training than nothing, because the computer learns the guess.

## Finishing a tile

Click **✓ TILE DONE → NEXT TILE** (or press **N**).

> ⚠ **Press N on every tile, including the LAST one.** N is what saves your work. Closing the
> window without pressing N loses that tile. After the last one, napari asks
> "Do you wish to close napari?" — click **Yes**.

If a square genuinely has nothing in it, N asks *"Nothing is segmented yet. Do you wish to
continue to the next image?"* — click **OK**. That is the tool checking you did not forget the
tile, not an error.

## Going back

Pressed N too early, or spotted a mistake on the tile before? Click **◀ BACK to previous tile**
(or press **B**). It reopens the previous square with your corrections on it, exactly as you
left them — it is not a fresh start. The square you are leaving is saved first, so you never
lose work by going back. Press **N** when you are done there and it jumps straight back to the
first square you have not finished yet.

Everything is saved tile by tile, so you can stop any time and pick up where you left off:
already-finished tiles are skipped when the annotator is restarted.

## Keys

| key | action |
|---|---|
| **S** | segment from your click |
| **T** | switch the click between *include* (positive) and *exclude* (negative) |
| **C** | commit the object you just made |
| **B** | go back to the previous tile |
| **N** | save this tile and go to the next one |
| **D** | delete the object under the mouse pointer |
| scroll / drag | zoom / pan |

> **Got an outline you don't want?** Delete it (**D**, or DELETE objects mode) and make it
> again. There is no undo here — deleting and redoing is the one move that works in every
> state, so it is the only one the panel offers.

> **Do not use Shift+C / *Clear Annotations*.** It is listed in micro_sam's own menus, but in
> this version it can fail instead of clearing. To start an object over, delete that one
> outline (**D**, or DELETE objects mode) and add it again — that works in every state.
"""


if __name__ == "__main__":
    main()
