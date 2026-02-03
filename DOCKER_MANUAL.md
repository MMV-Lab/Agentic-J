# ImagentJ Docker Manual

A containerized AI-powered ImageJ/Fiji assistant for image analysis tasks.

## Prerequisites

- Docker and Docker Compose installed
- OpenAI API key (for the AI agent)
- Web browser (Chrome, Firefox, Safari, or Edge)

## Quick Start

```bash
# 1. Create environment file
cp .env.template .env

# 2. Edit .env and add your API key
# OPENAI_API_KEY=your-key-here

# 3. Start the container
docker compose up -d

# 4. Open browser to access the GUI
# http://localhost:6080/vnc.html
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
OPENAI_API_KEY=your-openai-api-key

# Optional - LangSmith tracing
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=imagentj

# Optional - Custom image data directory
IMAGE_DATA_DIR=/path/to/your/images
```

### Image Data Access

Place your images in the `./data` directory (or set `IMAGE_DATA_DIR`). They'll be available inside the container at `/data`.

```bash
# Example: Copy images to the data directory
mkdir -p data
cp /path/to/your/images/*.tif data/
```

## Using the Application

### Accessing the GUI

1. Start the container: `docker compose up -d`
2. Open http://localhost:6080/vnc.html in your browser
3. You'll see a virtual desktop with:
   - **ImagentJ Chat Window** - AI assistant interface
   - **Fiji** - ImageJ/Fiji application (opens when needed)

### Interacting with the AI Agent

The chat interface accepts natural language requests for image analysis:

**Example requests:**
- "Open the image /data/sample.tif"
- "Apply a Gaussian blur with sigma 2"
- "Segment the nuclei in this image"
- "Measure the area of all particles"
- "Create a histogram of pixel intensities"

**Tips:**
- Be specific about file paths (use `/data/filename` for your images)
- The agent will ask clarifying questions if needed
- Results appear in the Fiji window

### Plugin Management

**Installing plugins:**
```
"Install the StarDist plugin"
"I need MorphoLibJ for morphological operations"
```

The agent will:
1. Check if the plugin is already installed
2. Search for it in the plugin database
3. Ask for confirmation before installing
4. Install and prompt you to restart

**After plugin installation:**
1. Quit Fiji (close the Fiji window or File > Quit)
2. The container will stop
3. Restart: `docker compose up -d`
4. Reconnect to http://localhost:6080/vnc.html
5. The plugin is now available

## Container Management

### Common Commands

```bash
# Start container (detached)
docker compose up -d

# View logs
docker compose logs -f

# Stop container
docker compose down

# Restart container
docker compose restart

# Open a shell in the container
docker compose exec imagentj bash
```

### Data Persistence

The following data persists across container restarts:

| Data | Location | Docker Volume |
|------|----------|---------------|
| Fiji plugins | `/opt/Fiji.app/plugins` | `fiji_plugins` |
| Fiji jars | `/opt/Fiji.app/jars` | `fiji_jars` |
| Saved scripts | `/app/scripts/saved_scripts` | `saved_scripts` |
| Plugin updates | `./fiji_update` | Bind mount |
| Qdrant database | `./qdrant_data` | Bind mount |
| Your images | `./data` | Bind mount |

### Cleaning Up

```bash
# Stop and remove container
docker compose down

# Remove all data (plugins, scripts, etc.)
docker compose down -v

# Remove the image
docker rmi imagent_j-imagentj:with-fastembed
```

## Troubleshooting

### Cannot connect to noVNC (http://localhost:6080)

**Container not running:**
```bash
docker compose ps
# If not running:
docker compose up -d
```

**Port conflict:**
```bash
# Check if port 6080 is in use
lsof -i :6080
# Edit docker-compose.yml to use a different port if needed
```

### Fiji window not appearing

The Fiji window opens automatically when the agent needs it. If it doesn't appear:
1. Check container logs: `docker compose logs -f`
2. Look for Java/ImageJ errors
3. Restart the container: `docker compose restart`

### Plugin not found after installation

1. Ensure you restarted the container after installation
2. Check if the plugin files exist:
   ```bash
   docker compose exec imagentj ls /opt/Fiji.app/plugins/ | grep -i pluginname
   ```
3. Check the update staging area:
   ```bash
   ls fiji_update/plugins/
   ```

### "Request interrupted by user" in chat

This happens when you interact with Fiji (e.g., quit/restart) while the agent is working. Simply:
1. Wait for the container to restart
2. Reconnect to http://localhost:6080
3. Retry your request

### Container crashes on restart

Check for stale X11 lock files (should be auto-cleaned):
```bash
docker compose logs | grep -i "X11\|display\|lock"
```

If issues persist:
```bash
docker compose down
docker compose up -d
```

### Agent says "OPENAI_API_KEY not set"

1. Verify your `.env` file exists and contains the key
2. Check the key is valid
3. Restart the container after editing `.env`

## Advanced Usage

### Development Mode

Source code is bind-mounted for live updates:
- Edit files in `./src/` - changes apply on container restart
- No rebuild needed for Python code changes

### Custom Fiji Installation

The container uses Fiji at `/opt/Fiji.app`. To use a different version:
1. Modify the `FIJI_PATH` environment variable in `docker-compose.yml`
2. Rebuild or mount your Fiji installation

### Accessing Container Shell

```bash
# As application user
docker compose exec imagentj bash

# As root (limited due to security settings)
docker compose exec -u root imagentj bash
```

### Running Without GUI

For headless/CLI operations:
```bash
docker compose run imagentj python -c "import imagej; ij = imagej.init('/opt/Fiji.app')"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser                          │
│                 http://localhost:6080                   │
└─────────────────────┬───────────────────────────────────┘
                      │ WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                 Docker Container                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   noVNC     │──│   x11vnc    │──│      Xvfb       │ │
│  │  (port 6080)│  │ (port 5900) │  │  (display :1)   │ │
│  └─────────────┘  └─────────────┘  └────────┬────────┘ │
│                                              │          │
│  ┌───────────────────────────────────────────▼────────┐ │
│  │                  gui_runner.py                     │ │
│  │  ┌─────────────────┐  ┌─────────────────────────┐  │ │
│  │  │  PySide6 Chat   │  │    Fiji/ImageJ (Java)   │  │ │
│  │  │    Interface    │  │      via PyImageJ       │  │ │
│  │  └─────────────────┘  └─────────────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Support

For issues and feature requests, please open an issue in the project repository.
