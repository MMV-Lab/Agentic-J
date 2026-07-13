# Agentic-J

An AI-powered agent for microscopy image analysis. Agentic-J runs ImageJ inside a container together with an LLM-driven chat panel that can plan analyses, write and execute Groovy macros, install plugins, and report results.

## Quick start (Docker)

Prerequisites:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose on Linux)
- [Git](https://git-scm.com/downloads) **and** [Git LFS](https://git-lfs.com/) — the RAG vector database (`qdrant_data/**/storage.sqlite`) is stored via Git LFS, so a plain clone without LFS will give you stub files that won't work.
- ~8 GB RAM and ~30 GB free disk
- An OpenAI **or** OpenRouter API key

Steps:

```bash
# 1. One-time: enable Git LFS for your user (skip if already done)
git lfs install

# 2. Clone the repository (LFS files download automatically)
git clone https://github.com/MMV-Lab/Agentic-J.git Agentic-J
cd Agentic-J

# If you cloned BEFORE running `git lfs install`, hydrate the LFS files now:
# git lfs pull

# 3. Configure credentials
cp .env.template .env
# edit .env and fill in OPENAI_API_KEY or OPEN_ROUTER_API_KEY

# 4. Start the container
docker compose up
```

Then open <http://localhost:6080/vnc.html> in your browser. Fiji and the Agentic-J chat panel run inside the virtual desktop.

If no API key is set in `.env`, a setup wizard appears in the browser before Fiji launches.

Place images you want to analyse in [`./data/`](data/) — the agent sees them at `/app/data` inside the container.

> **Verifying LFS worked:** after cloning, check that `qdrant_data/collection/BioimageAnalysisDocs/storage.sqlite` is several MB, not a ~130-byte text file starting with `version https://git-lfs.github.com/...`. If it's a stub, run `git lfs install && git lfs pull`.

## GPU support (optional)

By default the container runs on **CPU** (`docker compose up`). On an NVIDIA GPU host you can run the GPU build, which accelerates the deep-learning segmentation steps — **Cellpose** (v3 + Cellpose-SAM, PyTorch) and **StarDist** (TensorFlow).

Requirements:

- NVIDIA GPU + driver **560+** (for the default CUDA 12.6 build; `560+` for `cu126`, `570+` for `cu128`)
- [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- **CDI enabled** in Docker (Docker 25+). Verify:

  ```bash
  docker info | grep -iA2 'CDI spec'   # must list the CDI spec directories
  nvidia-ctk cdi list                   # must list nvidia.com/gpu=all, =0, ...
  ```

  If those are empty, enable CDI once (needs host admin):

  ```bash
  sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
  # add   "features": { "cdi": true }   to /etc/docker/daemon.json
  sudo systemctl restart docker
  ```

**1. Set the build parameters.** Two build args in the [`Dockerfile`](Dockerfile) control the image — both **default to a CPU build**:

- **`USE_GPU`** — `false` (default) installs CPU PyTorch/TensorFlow; `true` installs CUDA PyTorch + `tensorflow[and-cuda]`.
- **`CUDA_TAG`** — the PyTorch CUDA wheel index. `cu126` (default) targets driver **560+**; `cu128` targets driver **570+** (newest CUDA / RTX 50xx).

`docker-compose.gpu.yml` already sets `USE_GPU=true` (and `CUDA_TAG=cu126`) for you. To pick a different CUDA build, export `CUDA_TAG` before building:

```bash
export CUDA_TAG=cu128     # optional; default is cu126
```

> **Older drivers (< 560).** `torch==2.11.0` wheels are published **only** for `cu126` and `cu128`. To target a lower tag (`cu121`/`cu124`), setting `CUDA_TAG` is not enough — you must also lower the pinned `torch==2.11.0` and `torchvision==0.26.0` strings in the [`Dockerfile`](Dockerfile) to a release that exists for that tag (e.g. `torch==2.6.0` for `cu124`), or the build fails with `No matching distribution found for torch==2.11.0`.

**2. Build and start** with the `docker-compose.gpu.yml` override:

```bash
# First time: build the GPU image (~30–60 min; downloads CUDA torch + tensorflow[and-cuda])
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build

# Start
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

(To build the GPU image without the override, pass the args directly: `docker compose build --build-arg USE_GPU=true --build-arg CUDA_TAG=cu126`.)

**3. Verify** the GPU is active inside the container:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec imagentj \
  /opt/conda/envs/cellpose/bin/python -c "import torch; print(torch.cuda.is_available())"   # -> True
```

## Documentation

The full user guide lives in [`user_guide/`](user_guide/):

| Guide | Contents |
|-------|----------|
| [01 Getting Started](user_guide/01_getting_started.md) | Prerequisites, `.env` setup, API keys, starting the container |
| [02 Interface & Agents](user_guide/02_interface_and_agents.md) | noVNC interface, agent architecture, supported plugins |
| [03 Prompting](user_guide/03_prompting.md) | How to write effective prompts |
| [04 Data, History & Reports](user_guide/04_data_history_and_reports.md) | File layout, chat history, issue reports |
| [05 Security](user_guide/05_security.md) | Security model, network exposure, key handling |


## Project layout

- [`src/imagentj/`](src/imagentj/) — main Python package (agents, tools, RAG)
- [`skills/`](skills/) — per-plugin documentation packs the agent retrieves at runtime
- [`bundled_jars/`](bundled_jars/), [`bundled_cache/`](bundled_cache/) — JARs and a pre-warmed jgo/Maven cache used to build the image offline
- [`data/`](data/) — image data and per-run outputs (mounted into the container)
- [`models/`](models/) — Cellpose models (bind-mounted at runtime)

## Development (without Docker)

Running on the host is supported but not the recommended path. See [environment.yml](environment.yml) for the conda environment, set `FIJI_PATH` to your local Fiji install, and run `python gui_runner.py` (GUI) or `python run.py` (CLI).

## Reporting issues

Use the **Report Issue** button in the chat panel, or email `agentj.help@gmail.com`.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Copyright © 2026 ISAS e.V.
