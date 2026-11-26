"""Build-time check: baked micro_sam checkpoints match micro_sam's own registry.

micro_sam fetches checkpoints through pooch, which hashes any file already in
$MICROSAM_CACHEDIR/models against micro_sam's xxh128 registry. A file whose hash
does not match is treated as stale and silently re-downloaded at first use —
inside napari's Qt thread, which freezes the viewer. So a bundled checkpoint that
has drifted from the installed micro_sam version must fail the image build here.

Usage: python verify_micro_sam_models.py vit_t_lm vit_b_lm ...
Each model is checked together with its `<model>_decoder` (AIS decoder).
"""
import os
import sys

import xxhash
from micro_sam.util import models

registry = models().registry
model_dir = os.path.join(os.environ["MICROSAM_CACHEDIR"], "models")

bad = []
for model in sys.argv[1:]:
    for name in (model, f"{model}_decoder"):
        path = os.path.join(model_dir, name)
        if not os.path.isfile(path):
            print(f"[micro_sam] {name}: MISSING ({path})")
            bad.append(name)
            continue
        h = xxhash.xxh128()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        ok = registry.get(name) == f"xxh128:{h.hexdigest()}"
        print(f"[micro_sam] {name}: {'OK' if ok else 'HASH MISMATCH'}")
        if not ok:
            bad.append(name)

if bad:
    sys.exit(f"[micro_sam] checkpoints do not match micro_sam's registry: {bad}")
