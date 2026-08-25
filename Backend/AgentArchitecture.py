"""Production primitives for Nexa's workflow-based agent runtime.

The semantic planner selects tools from a closed catalog. This module derives
workflow metadata from that validated selection and keeps context/audit state
deterministic; it does not classify natural-language requests with keywords.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field

from Backend.Chatbot import LoadHistory
from Backend.MongoStore import current_chat_session_id, current_chat_user_id
from Backend.Paths import DATA_DIR
from Backend.SessionContext import load_for_agent, prompt_block


class Workflow(str, Enum):
    DIRECT = "direct"
    RESEARCH = "research"
    PERSONAL_APP = "personal_app"
    ACTION = "action"
    KNOWLEDGE = "knowledge"
    LONG_RUNNING = "long_running"


class RouteDecision(BaseModel):
    """Validated boundary between intake and agent execution."""

    workflow: Workflow
    domains: list[str] = Field(default_factory=list)
    reason: str
    requires_confirmation: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class AgentContext(BaseModel):
    """Small, user-scoped context supplied to a workflow, never raw history."""

    conversation: str = ""
    session_context: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""
    user_id: str = ""


class AgentRun(BaseModel):
    id: str
    started_at: str
    completed_at: str = ""
    status: str = "running"
    workflow: str
    domains: list[str] = Field(default_factory=list)
    session_id: str = ""
    user_id: str = ""
    request_chars: int = 0
    selected_tools: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    error: str = ""


_WEB_TOOLS = {"research_web", "search_web", "read_webpage", "open_website"}
_DEVICE_TOOLS = {
    "open_application", "close_application", "control_volume",
    "control_brightness", "get_system_specs", "get_power_and_wifi_status",
    "create_document",
}
_LIVE_DATA_TOOLS = {
    "maps_search_places", "maps_geocode", "maps_get_directions",
    "get_weather_and_air_quality", "check_holiday_schedule", "convert_currency",
}
_ACTION_TOOLS = {
    "open_website", "open_application", "close_application", "control_volume",
    "control_brightness", "draft_email", "send_email", "create_document",
}
_CONFIRMATION_TOOLS = {"send_email"}
_MUTATION_TOKENS = {
    "send", "create", "update", "delete", "remove", "move", "archive",
    "reply", "respond", "post", "write", "upload", "share", "schedule",
}


def _tool_domain(name: str) -> str:
    if name.startswith("gmail_") or name in {"draft_email", "send_email"}:
        return "gmail"
    if name.startswith("google_drive_"):
        return "drive"
    if name.startswith("google_calendar_"):
        return "calendar"
    if name == "answer_owner_profile":
        return "owner_profile"
    if name in _WEB_TOOLS:
        return "web"
    if name in _DEVICE_TOOLS:
        return "device"
    if name in _LIVE_DATA_TOOLS:
        return "live_data"
    if name == "get_capabilities" or "_" not in name:
        return ""
    return name.split("_", 1)[0].strip().lower()


def _looks_mutating_tool(name: str) -> bool:
    if name in _ACTION_TOOLS:
        return True
    return bool(_MUTATION_TOKENS & set(name.lower().split("_")))


def route_from_plan(plan: dict[str, Any]) -> RouteDecision:
    """Derive audit/session metadata from a validated semantic tool plan.

    Natural-language intent has already been decided by the planner. This
    function examines only selected tool identities, never request wording.
    """
    selected = [str(item) for item in plan.get("tool_names") or [] if str(item)]
    domains: list[str] = []
    for name in selected:
        domain = _tool_domain(name)
        if domain and domain not in domains:
            domains.append(domain)

    has_action = any(_looks_mutating_tool(name) for name in selected)
    if has_action:
        workflow = Workflow.ACTION
    elif "answer_owner_profile" in selected and set(selected) <= {
        "answer_owner_profile", "get_capabilities"
    }:
        workflow = Workflow.KNOWLEDGE
    elif any(
        domain not in {"web", "device", "live_data", "owner_profile"}
        for domain in domains
    ):
        workflow = Workflow.PERSONAL_APP
    elif "web" in domains:
        workflow = Workflow.RESEARCH
    else:
        workflow = Workflow.DIRECT

    return RouteDecision(
        workflow=workflow,
        domains=domains,
        reason="Derived from the semantic planner's validated tool selection.",
        requires_confirmation=any(
            name in _CONFIRMATION_TOOLS
            or (_looks_mutating_tool(name) and name not in _ACTION_TOOLS)
            for name in selected
        ),
        confidence=0.9,
    )


def build_context(max_messages: int = 10, max_chars: int = 3_000) -> AgentContext:
    """Return a bounded history view from the current, already user-scoped chat."""
    session_context = load_for_agent()
    if session_context:
        conversation = prompt_block(session_context)
        if max_chars > 0:
            conversation = conversation[:max_chars]
        return AgentContext(
            conversation=conversation,
            session_context=session_context,
            session_id=current_chat_session_id(),
            user_id=current_chat_user_id(),
        )
    try:
        messages = LoadHistory(limit=max_messages)
    except Exception:
        messages = []
    snippets: list[str] = []
    used = 0
    for message in reversed(messages):
        role = str(message.get("role") or "user")
        if role not in {"user", "assistant"}:
            continue
        content = " ".join(str(message.get("content") or "").split())
        if not content:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        content = content[:remaining]
        snippets.append(f"{role.title()}: {content}")
        used += len(content)
    snippets.reverse()
    return AgentContext(
        conversation="\n".join(snippets),
        session_context={},
        session_id=current_chat_session_id(),
        user_id=current_chat_user_id(),
    )


class AgentRunStore:
    """Append-only, redacted runtime audit records for troubleshooting and evals."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "AgentRuns.json"
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, values: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(values[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def start(self, decision: RouteDecision, request: str, selected_tools: Iterable[str]) -> AgentRun:
        run = AgentRun(
            id=str(uuid4()),
            started_at=datetime.now(timezone.utc).isoformat(),
            workflow=decision.workflow.value,
            domains=decision.domains,
            session_id=current_chat_session_id(),
            user_id=current_chat_user_id(),
            request_chars=len(request),
            selected_tools=sorted(set(selected_tools)),
        )
        with self._lock:
            values = self._read()
            values.append(run.model_dump())
            self._write(values)
        return run

    def finish(self, run_id: str, *, tool_calls: Iterable[str] = (), error: str = "") -> None:
        with self._lock:
            values = self._read()
            for item in reversed(values):
                if item.get("id") == run_id:
                    item.update({
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "status": "failed" if error else "completed",
                        "tool_calls": list(tool_calls),
                        "error": error[:500],
                    })
                    break
            self._write(values)

    def set_selected_tools(self, run_id: str, selected_tools: Iterable[str]) -> None:
        """Record the validated plan only after it has passed policy checks."""
        with self._lock:
            values = self._read()
            for item in reversed(values):
                if item.get("id") == run_id:
                    item["selected_tools"] = sorted(set(selected_tools))
                    break
            self._write(values)

    def list_for_current_user(self, limit: int = 50) -> list[dict[str, Any]]:
        user_id = current_chat_user_id()
        with self._lock:
            records = self._read()
        if user_id:
            records = [item for item in records if item.get("user_id") == user_id]
        return list(reversed(records[-max(1, min(limit, 100)):]))


RUN_STORE = AgentRunStore()
