# Security

## What the agent can do

The AI agent executes Groovy/Java code directly in Fiji, reads and writes files in mounted directories, and installs Fiji plugins. This is intentional — it is what makes the tool useful.

---

## Default security posture (local desktop use)

By default the container is configured for single-user local use:

| Feature | Status |
|---------|--------|
| Port binding | `localhost:6080` only — not reachable from other machines |
| Container user | Non-root (`imagentj`) |
| Linux capabilities | All dropped |
| Privilege escalation | Blocked (`no-new-privileges`) |
| Resource limits | 4 CPU cores, 8 GB RAM |

Your image data in `./data/` is readable and writable by the agent. This is the only folder, it can have access to. So all of your private files outside of this folder are never accessed. 
Your image data are not directly sent to the agent but the metadata of the images are and any information your provide via chatting. 

---

## API keys

- Store keys only in `.env` — never share  this file.
- The `.env` file is in `.dockerignore` and is not baked into the image.
- Keys are passed as environment variables. The agent itself does not have direct file-system access to `/home/imagentj/api_keys.env` (the persisted keys file).
