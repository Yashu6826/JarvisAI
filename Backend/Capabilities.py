"""Single source of truth for Nexa capability descriptions and policies."""

from __future__ import annotations

from typing import Any, Iterable

from Backend.GoogleOAuth import google_mcp_connected
from Backend.MapsConnector import geoapify_configured


LOCAL_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "general",
        "label": "General assistant",
        "description": "Answer normal questions and continue conversations.",
        "category": "knowledge",
        "tools": [],
        "side_effect": "none",
    },
    {
        "id": "web",
        "label": "Live web research",
        "description": "Search the public web, inspect sources, and cite URLs.",
        "category": "knowledge",
        "tools": ["search_web", "read_webpage", "open_website"],
        "side_effect": "open_website_only",
    },
    {
        "id": "maps",
        "label": "Places and directions",
        "description": "Find nearby places, resolve locations, and calculate driving, walking, or bicycle routes through Geoapify.",
        "category": "location",
        "tools": ["maps_search_places", "maps_geocode", "maps_get_directions"],
        "side_effect": "none",
    },
    {
        "id": "live_planning",
        "label": "Weather, holidays, and currency",
        "description": "Check live weather and air quality, evaluate public holidays for scheduling, and convert currencies using reference rates.",
        "category": "live_data",
        "tools": ["get_weather_and_air_quality", "check_holiday_schedule", "convert_currency"],
        "side_effect": "none",
    },
    {
        "id": "device",
        "label": "Windows device control",
        "description": "Open or close applications, control audio and brightness, and inspect this computer.",
        "category": "local_action",
        "tools": [
            "open_application",
            "close_application",
            "control_volume",
            "control_brightness",
            "get_system_specs",
            "get_power_and_wifi_status",
        ],
        "side_effect": "explicit_request",
    },
    {
        "id": "email",
        "label": "Email composition and sending",
        "description": "Draft locally and send from the connected Gmail account only after UI confirmation.",
        "category": "connected_action",
        "tools": ["draft_email", "send_email"],
        "side_effect": "confirmation_required_to_send",
    },
    {
        "id": "documents",
        "label": "Local documents",
        "description": "Write requested content to a local text document.",
        "category": "local_action",
        "tools": ["create_document"],
        "side_effect": "explicit_request",
    },
    {
        "id": "owner_profile",
        "label": "Owner resume knowledge",
        "description": "Answer supported owner-profile questions from the local resume index.",
        "category": "private_knowledge",
        "tools": ["answer_owner_profile"],
        "side_effect": "none",
    },
)


GOOGLE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "gmail": {
        "label": "Gmail",
        "description": "Search and read Gmail. Email sending uses this connected account and always requires UI confirmation.",
        "read_only_mcp": True,
        "features": [
            "search inbox threads",
            "read messages and threads",
            "list drafts and labels",
            "send after confirmation",
        ],
    },
    "google_drive": {
        "label": "Google Drive",
        "description": "Search, inspect, download, and read eligible Drive files without changing Drive.",
        "read_only_mcp": True,
        "features": [
            "search files",
            "list recent files",
            "read file content",
            "inspect metadata and permissions",
            "download file content",
        ],
    },
    "google_calendar": {
        "label": "Google Calendar",
        "description": "Read schedules and manage events. Every event mutation requires UI confirmation.",
        "read_only_mcp": False,
        "features": [
            "list and search events",
            "inspect calendars and events",
            "suggest meeting times",
            "create, update, delete, or respond after confirmation",
        ],
    },
}


def capability_snapshot(mcp_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build public, machine-readable live capability state."""
    mcp_snapshot = mcp_snapshot or {}
    server_by_name = {
        str(server.get("name")): server
        for server in mcp_snapshot.get("servers", [])
        if isinstance(server, dict)
    }
    google: list[dict[str, Any]] = []
    for service, definition in GOOGLE_CAPABILITIES.items():
        server = server_by_name.get(service, {})
        connector_connected = google_mcp_connected(service)
        google.append({
            "id": service,
            "label": definition["label"],
            "description": definition["description"],
            "features": list(definition["features"]),
            "connected": connector_connected,
            "available": connector_connected,
            "read_only": bool(definition["read_only_mcp"]),
            "error": str(server.get("runtime_error") or ""),
        })
    local = []
    for item in LOCAL_CAPABILITIES:
        available = geoapify_configured() if item["id"] == "maps" else True
        local.append(dict(item, available=available))
    return {
        "local": local,
        "google": google,
        "plugins": [
            {
                "id": str(server.get("name") or ""),
                "label": str(server.get("label") or server.get("name") or "Connected app"),
                "description": str(server.get("description") or ""),
                "connected": bool(server.get("oauth_connected", True)),
                "available": bool(server.get("ready")),
                "read_only": bool(server.get("read_only")),
            }
            for server in mcp_snapshot.get("servers", [])
            if isinstance(server, dict) and str(server.get("name") or "") not in GOOGLE_CAPABILITIES
        ],
        "mcp_runtime": dict(mcp_snapshot.get("runtime") or {}),
    }


def capability_prompt(
    mcp_snapshot: dict[str, Any] | None,
    exposed_tool_names: Iterable[str],
) -> str:
    """Generate concise capability context for the system prompt."""
    snapshot = capability_snapshot(mcp_snapshot)
    tool_names = sorted({name for name in exposed_tool_names if name})
    lines = [
        "Live capability state:",
        "- Normal conversation and live public-web research are available.",
        "- Local Windows actions, local documents, and owner-resume retrieval are available when relevant.",
    ]
    maps = next((item for item in snapshot["local"] if item["id"] == "maps"), None)
    if maps:
        state = "configured and ready" if maps["available"] else "not configured"
        lines.append(f"- Geoapify places and directions: {state}. {maps['description']}")
    lines.append("- Live planning data: weather and AQI through Open-Meteo, public-holiday scheduling through Nager, and reference currency conversion through Frankfurter.")
    for service in snapshot["google"]:
        if service["available"]:
            state = "connected and ready"
        elif service["connected"]:
            state = "connected but currently unavailable"
        else:
            state = "not connected"
        lines.append(f"- {service['label']}: {state}. {service['description']}")
    for plugin in snapshot["plugins"]:
        state = "connected and ready" if plugin["available"] else "not connected or unavailable"
        lines.append(
            f"- Connected plugin {plugin['label']}: {state}. {plugin['description']}"
        )
    if tool_names:
        lines.append(f"- Tools exposed for this request: {', '.join(tool_names)}.")
    lines.append(
        "- Never claim an unavailable or disconnected capability worked. Explain the prerequisite instead."
    )
    return "\n".join(lines)
