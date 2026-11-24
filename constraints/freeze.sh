#!/bin/bash
# Regenerate the version pins in this folder from a built image that passed its tests:
#   constraints/freeze.sh agenticj:cpu-local [agenticj:gpu-local]
# To upgrade packages: empty the pin files (keep them), build, test, re-run this.
# <env>.txt       pip constraints (PIP_CONSTRAINT) — every Python package in the env
# <env>.conda.yml conda pins (CONDARC, pinned_packages) — every conda package in the env (the two conda-built envs)
# napari-mcp-gpu.txt  pins for the one GPU-only step (CUDA torch reinstall), from the GPU image if given
# Both only constrain what gets installed anyway, so entries unused on another platform are harmless.
set -eu
cd "$(dirname "$0")"
docker run --rm -i --network none -u "$(id -u)" -v "$PWD":/out --entrypoint /opt/conda/bin/python "$1" - <<'PY'
import json, re, subprocess
# git installs are pinned by commit, torch/torchvision by the Dockerfile (CPU and GPU builds differ)
skip = {"pip", "setuptools", "wheel", "cp_measure", "cp-measure", "mobile_sam", "mobile-sam", "torch", "torchvision"}
# the cellpose env overrides tifffile in a second pip call, against aicsimageio's own upper bound
skip_in = {"cellpose": {"tifffile"}}
ok = re.compile(r"^\d+(\.\d+)*((a|b|rc|\.post|\.dev)\d+)*$")
for env in ("local_imagent_J", "napari-mcp", "cellpose", "cellpose4", "stardist", "brainglobe"):
    pkgs = json.loads(subprocess.check_output(["/opt/conda/bin/conda", "list", "-n", env, "--json"]))
    pips = json.loads(subprocess.check_output([f"/opt/conda/envs/{env}/bin/python", "-m", "pip", "list", "--format=json"]))
    pins = {}
    for p in pips:
        version = p["version"].split("+")[0]            # drop +cpu / +cu126
        if p["name"].lower() not in skip | skip_in.get(env, set()) and ok.match(version):
            pins[p["name"].lower()] = f"{p['name']}=={version}"
    open(f"/out/{env}.txt", "w").write("\n".join(pins[k] for k in sorted(pins)) + "\n")
    if env not in ("local_imagent_J", "napari-mcp"):    # the other envs take only python from conda
        continue
    conda = sorted(f"  - {p['name']}=={p['version']}" for p in pkgs if p["channel"] != "pypi")
    open(f"/out/{env}.conda.yml", "w").write("pinned_packages:\n" + "\n".join(conda) + "\n")
    print(env, len(pins), "pip pins,", len(conda), "conda pins")
PY
[ -n "${2:-}" ] || exit 0
docker run --rm -i --network none -u "$(id -u)" -v "$PWD":/out --entrypoint /opt/conda/envs/napari-mcp/bin/python "$2" - <<'PY'
# everything torch and torchvision pull in, at the versions the torch index served
import importlib.metadata as md, re
from packaging.requirements import Requirement
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
seen, todo = {}, ["torch", "torchvision"]
while todo:
    name = norm(todo.pop())
    if name in seen:
        continue
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        continue
    seen[name] = dist.version.split("+")[0]
    for r in map(Requirement, dist.requires or []):
        if r.marker is None or r.marker.evaluate({"extra": ""}):
            todo.append(r.name)
pins = [f"{n}=={v}" for n, v in sorted(seen.items()) if n not in ("torch", "torchvision")]
open("/out/napari-mcp-gpu.txt", "w").write("\n".join(pins) + "\n")
print("napari-mcp GPU step", len(pins), "pip pins")
PY
