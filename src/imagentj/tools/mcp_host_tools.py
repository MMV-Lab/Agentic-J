"""Generic MCP host adapter for Agent J.

This module lets Agent J consume MCP servers the same way coding agents do:
load an ``mcpServers`` config, call ``tools/list``, convert each returned
``inputSchema`` into a LangChain tool schema, and forward calls via
``tools/call``. It is intentionally not tied to napari.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import StructuredTool, tool
from pydantic import ConfigDict, Field, create_model


_DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 5
_DEFAULT_TOOL_TIMEOUT_SECONDS = 30
_PATH_ARGUMENT_KEYS = {"path", "save_path", "save_dir"}

_ASYNC_LOOP_LOCK = threading.Lock()
_ASYNC_LOOP: asyncio.AbstractEventLoop | None = None
_ASYNC_THREAD: threading.Thread | None = None
_CLIENT_LOCK = threading.Lock()
_CLIENTS: dict[str, Any] = {}
_CONFIG_CACHE_KEY: str | None = None
_CONFIG_CACHE: dict[str, dict[str, Any]] | None = None


def _timeout_seconds(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        timeout = int(raw)
    except Exception:
        timeout = default
    return max(1, min(timeout, 600))


def _discovery_timeout_seconds() -> int:
    return _timeout_seconds(
        "IMAGENTJ_MCP_DISCOVERY_TIMEOUT_SECONDS",
        _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    )


def _tool_timeout_seconds() -> int:
    return _timeout_seconds(
        "IMAGENTJ_MCP_TOOL_TIMEOUT_SECONDS",
        _DEFAULT_TOOL_TIMEOUT_SECONDS,
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _ensure_async_loop() -> asyncio.AbstractEventLoop:
    global _ASYNC_LOOP, _ASYNC_THREAD

    with _ASYNC_LOOP_LOCK:
        if _ASYNC_LOOP is not None and _ASYNC_LOOP.is_running():
            return _ASYNC_LOOP

        ready = threading.Event()

        def runner() -> None:
            global _ASYNC_LOOP
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _ASYNC_LOOP = loop
            ready.set()
            loop.run_forever()

        _ASYNC_THREAD = threading.Thread(
            target=runner,
            name="imagentj-mcp-host-loop",
            daemon=True,
        )
        _ASYNC_THREAD.start()
        ready.wait()
        assert _ASYNC_LOOP is not None
        return _ASYNC_LOOP


def _run_async(coro: Any) -> Any:
    loop = _ensure_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


async def _with_timeout(coro: Any, timeout_seconds: int) -> Any:
    return await asyncio.wait_for(coro, timeout=timeout_seconds)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
        import tomli as tomllib  # type: ignore[no-redef]

    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".toml":
        return _read_toml(path)
    return json.loads(path.read_text())


def _normalise_config(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return canonical server mapping from Claude/Codex-style config."""
    if "mcpServers" in raw and isinstance(raw["mcpServers"], dict):
        servers = raw["mcpServers"]
    elif "mcp_servers" in raw and isinstance(raw["mcp_servers"], dict):
        servers = raw["mcp_servers"]
    else:
        servers = {
            name: value
            for name, value in raw.items()
            if isinstance(value, dict) and ("command" in value or "url" in value)
        }

    normalised: dict[str, dict[str, Any]] = {}
    for name, server in servers.items():
        if isinstance(server, dict) and not server.get("disabled", False):
            normalised[str(name)] = dict(server)
    return normalised


def _default_config_paths() -> list[Path]:
    cwd = Path.cwd()
    return [
        cwd / "mcp.json",
        cwd / ".imagentj" / "mcp.json",
        cwd / ".mcp.json",
        Path.home() / ".imagentj" / "mcp.json",
    ]


def _config_cache_key() -> str:
    parts = [
        os.getenv("IMAGENTJ_MCP_CONFIG_JSON", ""),
        os.getenv("IMAGENTJ_MCP_CONFIG", ""),
    ]
    if not os.getenv("IMAGENTJ_MCP_CONFIG_JSON"):
        configured_path = os.getenv("IMAGENTJ_MCP_CONFIG")
        paths = (
            [Path(configured_path).expanduser()]
            if configured_path
            else _default_config_paths()
        )
        for path in paths:
            try:
                stat = path.stat()
            except OSError as exc:
                parts.append(f"{path}:{exc.__class__.__name__}")
            else:
                parts.append(f"{path}:{stat.st_mtime_ns}")
    return "\n".join(parts)


def load_mcp_server_configs() -> dict[str, dict[str, Any]]:
    """Load MCP server configs from env/file using standard mcpServers shape."""
    global _CONFIG_CACHE, _CONFIG_CACHE_KEY

    cache_key = _config_cache_key()
    if _CONFIG_CACHE is not None and _CONFIG_CACHE_KEY == cache_key:
        return _CONFIG_CACHE

    raw_json = os.getenv("IMAGENTJ_MCP_CONFIG_JSON")
    if raw_json:
        configs = _normalise_config(json.loads(raw_json))
    else:
        configured_path = os.getenv("IMAGENTJ_MCP_CONFIG")
        paths = (
            [Path(configured_path).expanduser()]
            if configured_path
            else _default_config_paths()
        )
        configs = {}
        for path in paths:
            if path.exists():
                configs = _normalise_config(_load_config_file(path))
                break

    _CONFIG_CACHE = configs
    _CONFIG_CACHE_KEY = cache_key
    return configs


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return repr(value)


def _parse_text_payload(content: Any) -> Any:
    if not isinstance(content, list) or len(content) != 1:
        return None
    item = content[0]
    if not isinstance(item, dict) or item.get("type") != "text":
        return None
    text = item.get("text")
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _serialise_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "content") or hasattr(result, "structured_content"):
        payload: dict[str, Any] = {
            "content": _jsonable(getattr(result, "content", None)),
            "is_error": bool(
                getattr(result, "is_error", getattr(result, "isError", False))
            ),
        }
        structured = getattr(result, "structured_content", None)
        if structured is None:
            structured = getattr(result, "structuredContent", None)
        if structured is not None:
            payload["structured_content"] = _jsonable(structured)
            payload["parsed_content"] = _jsonable(structured)
        data_attr = getattr(result, "data", None)
        if data_attr is not None:
            payload["data"] = _jsonable(data_attr)
            if "parsed_content" not in payload:
                payload["parsed_content"] = _jsonable(data_attr)
        if "parsed_content" not in payload:
            parsed = _parse_text_payload(payload["content"])
            if parsed is not None:
                payload["parsed_content"] = parsed
        return payload

    data = _jsonable(result)
    if isinstance(data, dict):
        parsed = _parse_text_payload(data.get("content"))
        if parsed is not None:
            data["parsed_content"] = parsed
        return data
    return {"content": data}


def _tool_to_dict(mcp_tool: Any) -> dict[str, Any]:
    data = _jsonable(mcp_tool)
    if isinstance(data, dict):
        return {
            "name": data.get("name"),
            "description": data.get("description", ""),
            "input_schema": data.get("inputSchema")
            or data.get("input_schema")
            or data.get("parameters"),
        }
    return {"name": repr(mcp_tool), "description": "", "input_schema": None}


def _client_key(server_name: str, server_config: dict[str, Any]) -> str:
    return json.dumps([server_name, server_config], sort_keys=True, default=str)


def _merged_env(server_config: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in (server_config.get("env") or {}).items():
        env[str(key)] = str(value)
    return env


def _client_for_server(server_name: str, server_config: dict[str, Any]) -> Any:
    key = _client_key(server_name, server_config)
    with _CLIENT_LOCK:
        if key in _CLIENTS:
            return _CLIENTS[key]

        try:
            from fastmcp import Client
        except Exception as exc:
            raise RuntimeError(f"fastmcp is required for MCP host support: {exc}") from exc

        if "command" in server_config:
            try:
                from fastmcp.client.transports import StdioTransport
            except Exception as exc:
                raise RuntimeError(f"fastmcp stdio transport is unavailable: {exc}") from exc

            transport = StdioTransport(
                command=str(server_config["command"]),
                args=[str(item) for item in server_config.get("args", [])],
                env=_merged_env(server_config),
                cwd=server_config.get("cwd"),
                keep_alive=_bool_env("IMAGENTJ_MCP_KEEP_ALIVE", True),
            )
            client = Client(transport, name=f"imagentj-{server_name}")
        elif "url" in server_config:
            client = Client(
                {"mcpServers": {server_name: server_config}},
                name=f"imagentj-{server_name}",
            )
        else:
            raise ValueError(
                f"MCP server '{server_name}' must define either command or url."
            )

        _CLIENTS[key] = client
        return client


def _evict_client(server_name: str, server_config: dict[str, Any]) -> None:
    """Remove a stale client from the cache so the next call spawns a fresh one."""
    key = _client_key(server_name, server_config)
    with _CLIENT_LOCK:
        _CLIENTS.pop(key, None)


async def _list_server_tools(server_name: str, server_config: dict[str, Any]) -> dict:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            client = _client_for_server(server_name, server_config)
            async with client:
                tools = await client.list_tools()
            return {
                "status": "ok",
                "server_name": server_name,
                "tools": [_tool_to_dict(item) for item in tools],
            }
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                # The server process likely died (e.g. napari window closed).
                # Evict the stale client so the next attempt spawns a fresh process.
                _evict_client(server_name, server_config)
    raise last_exc  # type: ignore[misc]


async def _call_server_tool(
    server_name: str,
    server_config: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict:
    call_arguments, path_translations = _translate_arguments(arguments)
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            client = _client_for_server(server_name, server_config)
            async with client:
                result = await client.call_tool(tool_name, call_arguments)
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                # Server process died (e.g. napari window closed); evict and retry.
                _evict_client(server_name, server_config)
            else:
                raise last_exc from exc  # type: ignore[misc]
    payload = {
        "status": "ok",
        "server_name": server_name,
        "tool_name": tool_name,
        "arguments": call_arguments,
        "result": _serialise_result(result),
    }
    if path_translations:
        payload["path_translations"] = path_translations
    serialised = payload["result"]
    if isinstance(serialised, dict) and serialised.get("is_error"):
        payload["status"] = "error"
    parsed = serialised.get("parsed_content") if isinstance(serialised, dict) else None
    if isinstance(parsed, dict) and parsed.get("status") in {"error", "failed"}:
        payload["status"] = "error"
        payload["message"] = str(parsed.get("message") or parsed)
    return payload


def _configured_path_mappings() -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    raw_map = os.getenv("IMAGENTJ_MCP_PATH_MAP", "")
    for item in raw_map.split(","):
        text = item.strip()
        if not text or "=" not in text:
            continue
        container_prefix, host_prefix = text.split("=", 1)
        container_prefix = container_prefix.strip().rstrip("/")
        host_prefix = host_prefix.strip().rstrip("/")
        if container_prefix and host_prefix:
            mappings.append((container_prefix, host_prefix))

    host_data_dir = os.getenv("IMAGENTJ_MCP_HOST_DATA_DIR")
    if host_data_dir:
        host_data_dir = host_data_dir.rstrip("/")
        mappings.extend([("/app/data", host_data_dir), ("/data", host_data_dir)])
    return mappings


def _translate_path(path: str) -> tuple[str, Optional[dict[str, str]]]:
    if not path.startswith("/"):
        return path, None
    for container_prefix, host_prefix in _configured_path_mappings():
        if path == container_prefix:
            return host_prefix, {"from": path, "to": host_prefix}
        prefix = container_prefix + "/"
        if path.startswith(prefix):
            relative = path[len(prefix) :]
            translated = str(Path(host_prefix) / relative)
            return translated, {"from": path, "to": translated}
    return path, None


def _translate_arguments(
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    path_translations: list[dict[str, str]] = []

    def translate(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                item_key: translate(item_value, item_key)
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [translate(item) for item in value]
        if key in _PATH_ARGUMENT_KEYS and isinstance(value, str) and value:
            new_value, change = _translate_path(value)
            if change:
                change["field"] = key
                path_translations.append(change)
            return new_value
        return value

    translated = translate(arguments)
    return translated, path_translations


def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", value).strip("_")
    if not safe:
        safe = "server"
    if safe[0].isdigit():
        safe = f"_{safe}"
    return safe


def _langchain_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{_safe_segment(server_name)}__{_safe_segment(tool_name)}"


def _schema_field_default(prop_schema: dict[str, Any], required: bool) -> Any:
    if "default" in prop_schema:
        return prop_schema["default"]
    return ... if required else None


def _schema_to_args_model(tool_name: str, input_schema: Any) -> type:
    if not isinstance(input_schema, dict):
        input_schema = {}
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    required = set(input_schema.get("required") or [])

    fields: dict[str, Any] = {}
    for field_name, raw_prop_schema in properties.items():
        prop_schema = raw_prop_schema if isinstance(raw_prop_schema, dict) else {}
        default = _schema_field_default(prop_schema, field_name in required)
        fields[str(field_name)] = (
            Any,
            Field(
                default,
                description=prop_schema.get("description"),
                json_schema_extra=prop_schema,
            ),
        )

    model_name = "".join(
        part.capitalize() for part in _safe_segment(tool_name).split("_")
    )
    return create_model(
        f"{model_name}Args",
        __config__=ConfigDict(extra="allow"),
        **fields,
    )


def _make_host_tool(
    server_name: str,
    server_config: dict[str, Any],
    mcp_tool: dict[str, Any],
) -> StructuredTool:
    upstream_name = str(mcp_tool["name"])
    public_name = _langchain_tool_name(server_name, upstream_name)
    description = (
        mcp_tool.get("description")
        or f"Call MCP tool `{upstream_name}` from server `{server_name}`."
    )
    args_schema = _schema_to_args_model(public_name, mcp_tool.get("input_schema"))

    def invoke_mcp_tool(**kwargs: Any) -> dict:
        return _run_async(
            _with_timeout(
                _call_server_tool(server_name, server_config, upstream_name, kwargs),
                _tool_timeout_seconds(),
            )
        )

    invoke_mcp_tool.__name__ = f"invoke_{public_name}"
    return StructuredTool.from_function(
        func=invoke_mcp_tool,
        name=public_name,
        description=description,
        args_schema=args_schema,
        infer_schema=False,
    )


def get_mcp_tools(include_raw_tools: bool = True) -> list:
    """
    Discover configured MCP servers and return LangChain tools for Agent J.

    Tool names use the namespace ``mcp__<server>__<tool>``. For example, a
    config entry named ``napari-mcp`` exposing ``add_layer`` becomes
    ``mcp__napari_mcp__add_layer``.
    """
    configs = load_mcp_server_configs()
    tools: list = []
    discovery_timeout = _discovery_timeout_seconds()
    registered_names: set[str] = set()

    for server_name, server_config in configs.items():
        try:
            listed = _run_async(
                _with_timeout(
                    _list_server_tools(server_name, server_config),
                    discovery_timeout,
                )
            )
        except Exception:
            continue
        if listed.get("status") != "ok":
            continue
        for mcp_tool in listed.get("tools", []):
            if not isinstance(mcp_tool, dict) or not mcp_tool.get("name"):
                continue
            public_name = _langchain_tool_name(server_name, str(mcp_tool["name"]))
            if public_name in registered_names:
                continue
            registered_names.add(public_name)
            tools.append(_make_host_tool(server_name, server_config, mcp_tool))

    if include_raw_tools:
        tools.extend([mcp_list_servers, mcp_list_tools, mcp_call_tool])
    return tools


@tool("mcp_list_servers")
def mcp_list_servers() -> dict:
    """List MCP servers configured for Agent J."""
    configs = load_mcp_server_configs()
    return {
        "status": "ok",
        "servers": [
            {
                "name": name,
                "transport": "http" if "url" in config else "stdio",
                "description": config.get("description"),
            }
            for name, config in configs.items()
        ],
    }


@tool("mcp_list_tools")
def mcp_list_tools(
    server_name: Optional[str] = None,
    timeout_seconds: int = _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
) -> dict:
    """List tools exposed by one or all configured MCP servers."""
    configs = load_mcp_server_configs()
    selected = (
        {server_name: configs[server_name]}
        if server_name and server_name in configs
        else configs
    )
    if server_name and server_name not in configs:
        return {"status": "error", "message": f"Unknown MCP server: {server_name}"}

    results = []
    for name, config in selected.items():
        try:
            result = _run_async(
                _with_timeout(_list_server_tools(name, config), timeout_seconds)
            )
        except Exception as exc:
            result = {"status": "error", "server_name": name, "message": str(exc)}
        results.append(result)
    return {"status": "ok", "servers": results}


@tool("mcp_call_tool")
def mcp_call_tool(
    server_name: str,
    tool_name: str,
    arguments: Optional[dict] = None,
    timeout_seconds: int = _DEFAULT_TOOL_TIMEOUT_SECONDS,
) -> dict:
    """Call one MCP tool by explicit server and upstream tool name."""
    configs = load_mcp_server_configs()
    if server_name not in configs:
        return {"status": "error", "message": f"Unknown MCP server: {server_name}"}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {"status": "error", "message": "arguments must be a JSON object"}
    try:
        return _run_async(
            _with_timeout(
                _call_server_tool(
                    server_name,
                    configs[server_name],
                    tool_name,
                    arguments,
                ),
                timeout_seconds,
            )
        )
    except Exception as exc:
        return {
            "status": "error",
            "server_name": server_name,
            "tool_name": tool_name,
            "message": str(exc),
        }
