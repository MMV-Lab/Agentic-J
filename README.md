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
git clone https://github.com/LJMedPhys/Imagent_J.git
cd Imagent_J

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

## Documentation

The full user guide lives in [`user_guide/`](user_guide/):

| Guide | Contents |
|-------|----------|
| [01 Getting Started](user_guide/01_getting_started.md) | Prerequisites, `.env` setup, API keys, starting the container |
| [02 Interface & Agents](user_guide/02_interface_and_agents.md) | noVNC interface, agent architecture, supported plugins |
| [03 Prompting](user_guide/03_prompting.md) | How to write effective prompts |
| [04 Data, History & Reports](user_guide/04_data_history_and_reports.md) | File layout, chat history, issue reports |
| [05 Security](user_guide/05_security.md) | Security model, network exposure, key handling |

For Docker-specific operations (logs, volumes, troubleshooting) see [DOCKER_MANUAL.md](DOCKER_MANUAL.md).

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
