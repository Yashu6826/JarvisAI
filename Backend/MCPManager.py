from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import hashlib
import importlib.metadata
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from Backend.LLMProvider import get_config
from Backend.GoogleOAuth import (
    current_session_id,
    google_connection_signature,
    google_mcp_connected,
    google_mcp_header,
)
from Backend.Paths import DATA_DIR


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / ".mcp.json"
PENDING_ACTIONS_PATH = DATA_DIR / "PendingMCPActions.json"
_APPROVAL_BYPASS = contextvars.ContextVar("mcp_approval_bypass", default=False)
_TOOL_CACHE: dict[str, list[Any]] = {}
_PENDING_LOCK = threading.RLock()
_LAST_MCP_ERROR = ""
_MCP_SERVER_ERRORS: dict[str, str] = {}
_PENDING_ACTION_TTL = timedelta(minutes=20)
logger = logging.getLogger("nexa.workflow.mcp")

_GENERIC_SENSITIVE_KEYWORDS = (
    "send",
    "create",
    "update",
    "delete",
    "remove",
    "move",
    "archive",
    "reply",
    "compose",
    "post",
    "write",
    "upload",
)


class MCPConfigurationError(RuntimeError):
    pass


class MCPExecutionError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_status(message: str, stage: str, detail: str) -> None:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return
    writer({
        "type": "status",
        "message": message,
        "stage": stage,
        "detail": detail,
    })


def _emit_custom_event(payload: dict[str, object]) -> None:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return
    writer(payload)


def _config_path() -> Path:
    configured = get_config("NEXA_MCP_CONFIG_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_CONFIG_PATH


def _read_json_file(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_config_document() -> dict[str, Any]:
    data = _read_json_file(_config_path(), {})
    return data if isinstance(data, dict) else {}


def _normalized_transport(server: dict[str, Any]) -> str:
    value = str(server.get("transport") or "").strip().lower()
    if value in {"http", "streamable_http", "streamable-http", "sse"}:
        return "http"
    if value:
        return value
    if server.get("url"):
        return "http"
    return "stdio"


def _resolve_env_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    resolved: dict[str, str] = {}
    for key, value in raw.items():
        if not key:
            continue
        if isinstance(value, str) and value.startswith("$"):
            resolved[str(key)] = os.getenv(value[1:], "")
        else:
            resolved[str(key)] = str(value)
    return resolved


def _normalize_server(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("x-nexa") if isinstance(raw.get("x-nexa"), dict) else {}
    transport = _normalized_transport(raw)
    return {
        "name": name,
        "label": str(meta.get("label") or name.replace("_", " ").title()),
        "description": str(meta.get("description") or ""),
        "category": str(meta.get("category") or "general"),
        "enabled": bool(raw.get("enabled", True)),
        "transport": transport,
        "url": str(raw.get("url") or "").strip(),
        "command": str(raw.get("command") or "").strip(),
        "args": [str(item) for item in raw.get("args", [])] if isinstance(raw.get("args"), list) else [],
        "env": _resolve_env_map(raw.get("env")),
        "headers": _resolve_env_map(raw.get("headers")),
        "read_only": bool(meta.get("read_only", False)),
        "requires_confirmation": bool(meta.get("requires_confirmation", False)),
        "sensitive_tools": [
            str(item).strip().lower()
            for item in meta.get("sensitive_tools", [])
            if str(item).strip()
        ] if isinstance(meta.get("sensitive_tools"), list) else [],
        "oauth_service": str(meta.get("oauth_service") or "").strip(),
        "tool_allowlist": [
            str(item).strip()
            for item in meta.get("tool_allowlist", [])
            if str(item).strip()
        ] if isinstance(meta.get("tool_allowlist"), list) else [],
    }


def list_mcp_servers() -> list[dict[str, Any]]:
    doc = _load_config_document()
    servers = doc.get("mcpServers")
    if not isinstance(servers, dict):
        return []

    items: list[dict[str, Any]] = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            continue
        server = _normalize_server(str(name), raw)
        configured = bool(server["url"] or server["command"])
        oauth_connected = (
            google_mcp_connected(server["oauth_service"])
            if server["oauth_service"] else True
        )
        items.append({
            **server,
            "configured": configured,
            "oauth_connected": oauth_connected,
            "active": bool(server["enabled"] and configured and oauth_connected),
        })
    return items


def mcp_server_summary() -> str:
    ready = [
        server
        for server in mcp_status_snapshot().get("servers", [])
        if server.get("ready")
    ]
    if not ready:
        return ""
    parts = []
    for server in ready:
        mode = "read-only" if server.get("read_only") else "interactive"
        parts.append(f"{server['label']} ({mode})")
    return ", ".join(parts)


def mcp_runtime_diagnostics() -> dict[str, Any]:
    """Return import/runtime readiness without exposing configuration secrets."""
    global _LAST_MCP_ERROR
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: F401

        adapter_version = importlib.metadata.version("langchain-mcp-adapters")
        mcp_version = importlib.metadata.version("mcp")
    except Exception as exc:
        raw_message = f"{type(exc).__name__}: {exc}"
        if "RequestContext" in raw_message or "mcp.shared.context" in raw_message:
            message = (
                "MCP dependency mismatch. Run NEXA with .venv\\Scripts\\python.exe "
                "or reinstall requirements.txt in the active environment."
            )
        else:
            message = raw_message
        _LAST_MCP_ERROR = message
        return {
            "available": False,
            "adapter_version": "",
            "mcp_version": "",
            "error": message,
        }
    return {
        "available": True,
        "adapter_version": adapter_version,
        "mcp_version": mcp_version,
        "error": _LAST_MCP_ERROR,
    }


def _public_server(server: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    runtime_error = str(
        _MCP_SERVER_ERRORS.get(server["name"])
        or runtime.get("error")
        or ""
    )
    return {
        "name": server["name"],
        "label": server["label"],
        "description": server["description"],
        "category": server["category"],
        "enabled": server["enabled"],
        "configured": server["configured"],
        "oauth_service": server["oauth_service"],
        "oauth_connected": server["oauth_connected"],
        "active": server["active"],
        "ready": bool(server["active"] and runtime.get("available") and not runtime_error),
        "read_only": server["read_only"],
        "requires_confirmation": server["requires_confirmation"],
        "tool_allowlist": list(server.get("tool_allowlist", [])),
        "runtime_error": runtime_error if server["active"] else "",
    }


def mcp_status_snapshot() -> dict[str, Any]:
    servers = list_mcp_servers()
    active = [server for server in servers if server.get("active")]
    runtime = mcp_runtime_diagnostics()
    public_servers = [_public_server(server, runtime) for server in servers]
    ready = [server for server in public_servers if server.get("ready")]
    return {
        "configured_count": len(servers),
        "active_count": len(active),
        "ready_count": len(ready),
        "servers": public_servers,
        "runtime": runtime,
    }


def _connection_config(server: dict[str, Any]) -> dict[str, Any]:
    if server["transport"] == "http":
        if not server["url"]:
            raise MCPConfigurationError(f"MCP server '{server['name']}' is missing its url.")
        payload: dict[str, Any] = {
            "transport": "http",
            "url": server["url"],
        }
        if server["headers"]:
            payload["headers"] = server["headers"]
        if server.get("oauth_service"):
            authorization = google_mcp_header(server["oauth_service"])
            if authorization:
                payload.setdefault("headers", {})["Authorization"] = authorization
        return payload

    if not server["command"]:
        raise MCPConfigurationError(f"MCP server '{server['name']}' is missing its command.")
    payload = {
        "transport": "stdio",
        "command": server["command"],
    }
    if server["args"]:
        payload["args"] = server["args"]
    if server["env"]:
        payload["env"] = server["env"]
    return payload


def _config_signature() -> str:
    path = _config_path()
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    identity = google_connection_signature()
    return hashlib.sha1(f"{content}\n{identity}".encode("utf-8")).hexdigest()


def _load_pending_actions() -> list[dict[str, Any]]:
    with _PENDING_LOCK:
        data = _read_json_file(PENDING_ACTIONS_PATH, [])
        items = data if isinstance(data, list) else []
        changed = False
        cutoff = datetime.now(timezone.utc) - _PENDING_ACTION_TTL
        for item in items:
            if not isinstance(item, dict) or item.get("status") != "pending_confirmation":
                continue
            try:
                created_at = datetime.fromisoformat(str(item.get("created_at") or ""))
                if not created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if created_at < cutoff:
                item["status"] = "expired"
                item["expired_at"] = _utc_now()
                changed = True
        if changed:
            _write_json_file(PENDING_ACTIONS_PATH, items[-200:])
        return items


def _save_pending_actions(items: list[dict[str, Any]]) -> None:
    with _PENDING_LOCK:
        _write_json_file(PENDING_ACTIONS_PATH, items[-200:])


def _pending_action_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "server_name": item.get("server_name", ""),
        "server_label": item.get("server_label", item.get("server_name", "")),
        "tool_name": item.get("tool_name", ""),
        "display_name": item.get("display_name", item.get("tool_name", "")),
        "arguments": item.get("arguments", {}),
        "status": item.get("status", ""),
        "created_at": item.get("created_at", ""),
        "request_text": item.get("request_text", ""),
        "reason": item.get("reason", ""),
    }


def _latest_pending_action_record() -> dict[str, Any] | None:
    session_id = current_session_id()
    for item in reversed(_load_pending_actions()):
        if (
            isinstance(item, dict)
            and item.get("status") == "pending_confirmation"
            and str(item.get("session_id") or "") == session_id
        ):
            return item
    return None


def get_latest_pending_action() -> dict[str, Any] | None:
    item = _latest_pending_action_record()
    return _pending_action_payload(item) if item else None


def _find_server_by_name(name: str) -> dict[str, Any] | None:
    for server in list_mcp_servers():
        if server["name"] == name:
            return server
    return None


def _server_name_from_request(request: Any) -> str:
    for candidate in (
        getattr(request, "server_name", ""),
        getattr(getattr(request, "runtime", None), "server_name", ""),
        getattr(getattr(request, "context", None), "server_name", ""),
    ):
        if candidate:
            return str(candidate)
    return ""


def _request_text_from_runtime(runtime: Any) -> str:
    state = getattr(runtime, "state", {}) or {}
    messages = state.get("messages", [])
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return str(getattr(message, "content", ""))
    return ""


def _tool_is_sensitive(server: dict[str, Any], tool_name: str) -> bool:
    lowered = tool_name.strip().lower()
    if server.get("read_only"):
        return False
    if lowered in set(server.get("sensitive_tools", [])):
        return True
    return any(keyword in lowered for keyword in _GENERIC_SENSITIVE_KEYWORDS)


def _tool_is_allowed(server: dict[str, Any], tool_name: str) -> bool:
    """Enforce explicit tool boundaries before a tool reaches the model."""
    lowered = tool_name.strip().lower()
    allowlist = {
        str(item).strip().lower()
        for item in server.get("tool_allowlist", [])
        if str(item).strip()
    }
    if allowlist:
        return lowered in allowlist
    # A server advertised as read-only must provide an explicit allowlist. This
    # prevents a newly added remote write tool from silently becoming available.
    return not server.get("read_only")


def _display_name(server_label: str, tool_name: str) -> str:
    label = tool_name.replace("_", " ").replace("-", " ").strip().title()
    return f"{server_label}: {label}" if server_label else label


def _queue_pending_action(
    *,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    request_text: str,
    reason: str,
) -> dict[str, Any]:
    with _PENDING_LOCK:
        items = _load_pending_actions()
        for item in items:
            if (
                item.get("status") == "pending_confirmation"
                and str(item.get("session_id") or "") == current_session_id()
            ):
                item["status"] = "superseded"
                item["superseded_at"] = _utc_now()

        server = _find_server_by_name(server_name) or {
            "label": server_name or "Connected App"
        }
        action = {
            "id": uuid4().hex,
            "server_name": server_name,
            "server_label": server.get("label", server_name),
            "tool_name": tool_name,
            "display_name": _display_name(server.get("label", server_name), tool_name),
            "arguments": arguments,
            "status": "pending_confirmation",
            "created_at": _utc_now(),
            "expires_at": (
                datetime.now(timezone.utc) + _PENDING_ACTION_TTL
            ).isoformat(),
            "request_text": request_text.strip(),
            "reason": reason,
            "session_id": current_session_id(),
        }
        items.append(action)
        _save_pending_actions(items)
        return action


def cancel_pending_action(action_id: str) -> dict[str, Any]:
    with _PENDING_LOCK:
        items = _load_pending_actions()
        for item in items:
            if item.get("id") != action_id:
                continue
            if str(item.get("session_id") or "") != current_session_id():
                raise MCPExecutionError(
                    "This connected action belongs to a different browser session."
                )
            if item.get("status") != "pending_confirmation":
                raise MCPExecutionError(
                    "That MCP action is no longer waiting for confirmation."
                )
            item["status"] = "cancelled"
            item["cancelled_at"] = _utc_now()
            _save_pending_actions(items)
            return _pending_action_payload(item)
    raise MCPExecutionError("Pending MCP action not found.")


def _exception_summary(exc: BaseException) -> str:
    """Flatten ExceptionGroup wrappers into a useful bounded diagnostic."""
    children = getattr(exc, "exceptions", None)
    if children:
        details = "; ".join(_exception_summary(item) for item in children[:3])
        return details or type(exc).__name__
    return f"{type(exc).__name__}: {exc}"[:1000]


async def _load_mcp_tools_async() -> list[Any]:
    global _LAST_MCP_ERROR
    runtime = mcp_runtime_diagnostics()
    if not runtime.get("available"):
        _LAST_MCP_ERROR = str(runtime.get("error") or "MCP runtime is unavailable.")
        return []
    signature = _config_signature()
    if signature and signature in _TOOL_CACHE:
        return list(_TOOL_CACHE[signature])

    active_servers = [server for server in list_mcp_servers() if server.get("active")]
    if not active_servers:
        _MCP_SERVER_ERRORS.clear()
        if signature:
            _TOOL_CACHE[signature] = []
        _LAST_MCP_ERROR = ""
        return []

    from langchain_mcp_adapters.callbacks import Callbacks
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_core.messages import ToolMessage

    async def approval_interceptor(request: Any, handler: Any) -> Any:
        server_name = _server_name_from_request(request)
        server = _find_server_by_name(server_name) or {}
        tool_name = str(getattr(request, "name", ""))
        if not server:
            return ToolMessage(
                content="The connected tool was blocked because its server policy was unavailable.",
                tool_call_id=getattr(
                    getattr(request, "runtime", None),
                    "tool_call_id",
                    "",
                ),
                name=tool_name,
                status="error",
            )

        if not _tool_is_allowed(server, tool_name):
            return ToolMessage(
                content=(
                    f"{_display_name(server.get('label', server_name), tool_name)} "
                    "is outside Nexa's allowed operations for this service."
                ),
                tool_call_id=getattr(
                    getattr(request, "runtime", None),
                    "tool_call_id",
                    "",
                ),
                name=tool_name,
                status="error",
            )

        # An approval bypass skips only the second confirmation prompt. The
        # server identity and current allowlist are still enforced in case the
        # policy changed while the action was waiting in the UI.
        if _APPROVAL_BYPASS.get():
            return await handler(request)

        if server.get("requires_confirmation") and _tool_is_sensitive(server, tool_name):
            pending = _queue_pending_action(
                server_name=server_name,
                tool_name=tool_name,
                arguments=dict(getattr(request, "args", {}) or {}),
                request_text=_request_text_from_runtime(getattr(request, "runtime", None)),
                reason="This connected-app action can change external state and needs approval.",
            )
            _emit_custom_event({
                "type": "confirm_mcp_action",
                "action": _pending_action_payload(pending),
            })
            return ToolMessage(
                content=(
                    f"{pending['display_name']} requires approval in the UI before it can run."
                ),
                tool_call_id=getattr(getattr(request, "runtime", None), "tool_call_id", ""),
                name=tool_name,
            )

        return await handler(request)

    async def on_progress(
        progress: float,
        total: float | None,
        message: str | None,
        context: Any,
    ) -> None:
        tool_part = f" / {context.tool_name}" if getattr(context, "tool_name", "") else ""
        percent = f"{(progress / total) * 100:.0f}%" if total else f"{progress}"
        _emit_status(
            "Connected app is working",
            "MCP",
            f"{context.server_name}{tool_part}: {percent}{f' - {message}' if message else ''}",
        )

    filtered_tools: list[Any] = []
    _MCP_SERVER_ERRORS.clear()
    for server in active_servers:
        try:
            client = MultiServerMCPClient(
                {server["name"]: _connection_config(server)},
                tool_interceptors=[approval_interceptor],
                callbacks=Callbacks(on_progress=on_progress),
                tool_name_prefix=True,
            )
            discovered_tools = await client.get_tools()
        except Exception as exc:
            error = _exception_summary(exc)
            if type(exc).__name__ == "ConnectError" or "ConnectError" in error:
                error = (
                    f"{error} (could not establish TLS connection to "
                    f"{server.get('url') or 'the configured MCP endpoint'}; "
                    "check outbound HTTPS/proxy/firewall access)"
                )
            _MCP_SERVER_ERRORS[server["name"]] = error[:1000]
            logger.warning(
                "MCP server %s could not be loaded: %s",
                server["name"],
                _MCP_SERVER_ERRORS[server["name"]],
            )
            continue

        for tool in discovered_tools:
            exposed_name = str(getattr(tool, "name", ""))
            prefix = f"{server['name']}_"
            if not exposed_name.startswith(prefix):
                continue
            original_name = exposed_name.removeprefix(prefix)
            if _tool_is_allowed(server, original_name):
                filtered_tools.append(tool)

    _LAST_MCP_ERROR = ""
    if signature and not _MCP_SERVER_ERRORS:
        _TOOL_CACHE[signature] = list(filtered_tools)
        while len(_TOOL_CACHE) > 12:
            _TOOL_CACHE.pop(next(iter(_TOOL_CACHE)))
    return list(filtered_tools)


def load_mcp_tools() -> list[Any]:
    global _LAST_MCP_ERROR
    try:
        return _run_async(_load_mcp_tools_async)
    except Exception as exc:
        _LAST_MCP_ERROR = f"{type(exc).__name__}: {exc}"
        logger.error("MCP tools could not be loaded: %s", _LAST_MCP_ERROR)
        return []


def _run_async(factory: Any) -> Any:
    """Run an async factory safely from sync code with or without a live loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(factory())).result()


async def _execute_tool_async(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    tools = await _load_mcp_tools_async()
    exposed_name = f"{server_name}_{tool_name}"
    for tool in tools:
        if getattr(tool, "name", "") != exposed_name:
            continue
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(arguments)
        return tool.invoke(arguments)
    raise MCPExecutionError(
        f"The connected tool '{exposed_name}' is not available."
    )


def confirm_pending_action(action_id: str) -> dict[str, Any]:
    with _PENDING_LOCK:
        items = _load_pending_actions()
        target = next(
            (item for item in items if item.get("id") == action_id),
            None,
        )
        if not target:
            raise MCPExecutionError("Pending MCP action not found.")
        if str(target.get("session_id") or "") != current_session_id():
            raise MCPExecutionError(
                "This connected action belongs to a different browser session."
            )
        if target.get("status") != "pending_confirmation":
            raise MCPExecutionError(
                "That connected action is no longer waiting for confirmation."
            )
        target["status"] = "executing"
        target["execution_started_at"] = _utc_now()
        _save_pending_actions(items)

    token = _APPROVAL_BYPASS.set(True)
    try:
        result = _run_async(
            lambda: _execute_tool_async(
                str(target.get("server_name", "")),
                str(target.get("tool_name", "")),
                dict(target.get("arguments", {}) or {}),
            )
        )
    except Exception as exc:
        with _PENDING_LOCK:
            items = _load_pending_actions()
            failed = next(
                (item for item in items if item.get("id") == action_id),
                None,
            )
            if failed:
                failed["status"] = "failed"
                failed["failed_at"] = _utc_now()
                failed["error"] = f"{type(exc).__name__}: {exc}"
                _save_pending_actions(items)
        raise MCPExecutionError(
            "The connected app could not complete the approved action. "
            "Review the connection and try the request again."
        ) from exc
    finally:
        _APPROVAL_BYPASS.reset(token)

    with _PENDING_LOCK:
        items = _load_pending_actions()
        completed = next(
            (item for item in items if item.get("id") == action_id),
            None,
        )
        if not completed:
            raise MCPExecutionError("The completed connected action could not be recorded.")
        completed["status"] = "completed"
        completed["confirmed_at"] = _utc_now()
        completed["result_preview"] = str(result)[:1000]
        _save_pending_actions(items)
        return {
            **_pending_action_payload(completed),
            "result_preview": str(result)[:1000],
        }
