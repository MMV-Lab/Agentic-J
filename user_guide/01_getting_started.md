# Getting Started

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose on Linux)
- At least 8 GB RAM and 30 GB free disk space
- An API key — either OpenAI or OpenRouter (see below)

---

## 1. Create a `.env` file

Copy `.env.template` and paste the file into the project root (i.e. the cloned repo), rename this as `.env`. This files helps pass credentials into the container. The `GMAIL_APP_PASSWORD` (not an actual password, trust us) is for sending the error report directly to the developers. A minimal example of the `.env` file content:

```env
# Required: pick one 
OPENAI_API_KEY=your-openai-api-key-here
OPEN_ROUTER_API_KEY=your-openrouter-api-key-here

# For reporting issues directly
GMAIL_APP_PASSWORD=sntt iusy rddg mtoi

```

---

## 2. API key options

| Provider | Variable | Notes |
|----------|----------|-------|
| **OpenAI** | `OPENAI_API_KEY` | Direct access to GPT models. OpenAI-only setups use `gpt-5.6-luna` through the Responses API with high reasoning for the VLM Judge. |
| **OpenRouter** | `OPEN_ROUTER_API_KEY` | Proxy that routes to many providers. The VLM Judge uses `google/gemini-3.5-flash`; this route takes priority when both keys are present. |

If neither key is set in the `.env` when the container starts, a **setup wizard** will appear in the browser before Fiji launches. You can insert the key there.

<!-- SCREENSHOT: setupwizard-->


---

## 3. Place your images

Put your image files in the `data/` folder at the project root (i.e. the cloned repo). Inside the container this folder is mounted at `/app/data`. The agent can read from and write to this path.

```
project-root/
├── data/           ← your images go here
│   └── my_image.tif
├── .env
└── docker-compose.yml
```

---

## 4. Start the container
Open the Terminal, and find your project folder. Inside the project folder, run the following command:

```bash
docker compose up
```

During the first run, Docker will pull/build the image (this takes several minutes). On subsequent starts it reuses the cached image. In the terminal, a long log will be printed out, but do not fret, most of it is just informative. 

Open your browser and go to:

```
http://localhost:6080/vnc.html
```

Click on "Connect", Fiji and the Agentic-J chat panel should appear in the browser window. Sometimes the SL4FJ warning pops up in the Console window, but this is not severe, and the window can be closed. 

To stop:

```bash
docker compose down
```

> Your data, scripts, models, plugins, and chat history are persisted in Docker named volumes and the `data/` folder — they survive container restarts and image rebuilds.

---

## 5. Updating

When a new image version is available:

```bash
docker compose pull   # or rebuild: docker compose build
docker compose up
```

Named volumes (Fiji plugins, chat history, saved scripts) are preserved across updates.
