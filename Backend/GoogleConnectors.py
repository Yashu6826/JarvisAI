"""First-party Google API connectors for Nexa's connected Google account."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from Backend.GoogleOAuth import GoogleOAuthError, google_access_token, google_mcp_connected


class GoogleConnectorError(RuntimeError):
    pass


def _request(service: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    if not google_mcp_connected(service):
        raise GoogleConnectorError(f"Connect {service.replace('_', ' ')} in Nexa first.")
    try:
        token = google_access_token(service)
    except GoogleOAuthError as exc:
        raise GoogleConnectorError(str(exc)) from exc
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(kwargs.pop("headers", {}))
    try:
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    except requests.RequestException as exc:
        raise GoogleConnectorError("Google could not be reached. Check the internet connection.") from exc
    if response.status_code in {401, 403}:
        raise GoogleConnectorError("Google did not authorize this connected account. Disconnect and reconnect the service in Nexa.")
    if not response.ok:
        raise GoogleConnectorError(f"Google connector request failed ({response.status_code}).")
    try:
        payload = response.json()
    except ValueError as exc:
        raise GoogleConnectorError("Google returned an invalid response.") from exc
    return payload if isinstance(payload, dict) else {}


def _message_text(payload: dict[str, Any]) -> str:
    def decode(part: dict[str, Any]) -> str:
        data = str((part.get("body") or {}).get("data") or "")
        if data:
            try:
                return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            except (ValueError, UnicodeDecodeError):
                return ""
        for child in part.get("parts") or []:
            if isinstance(child, dict):
                text = decode(child)
                if text:
                    return text
        return ""

    return " ".join(decode(payload).split())


def _gmail_message(message_id: str) -> dict[str, Any]:
    payload = _request(
        "gmail",
        "GET",
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        params={"format": "full"},
    )
    headers = {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in (payload.get("payload") or {}).get("headers", [])
        if isinstance(item, dict)
    }
    return {
        "id": str(payload.get("id") or message_id),
        "thread_id": str(payload.get("threadId") or ""),
        "subject": headers.get("subject", "(no subject)"),
        "from": headers.get("from", "Unknown sender"),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": str(payload.get("snippet") or ""),
        "body": _message_text(payload.get("payload") or {})[:12_000],
    }


def gmail_search_messages(query: str = "", count: int = 5) -> dict[str, Any]:
    count = max(1, min(int(count), 10))
    listing = _request(
        "gmail",
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        params={"maxResults": count, **({"q": query} if query.strip() else {})},
    )
    messages = [
        _gmail_message(str(item.get("id")))
        for item in listing.get("messages") or []
        if isinstance(item, dict) and item.get("id")
    ]
    return {"ok": True, "messages": messages, "result_count": len(messages)}


def gmail_read_message(message_id: str) -> dict[str, Any]:
    if not message_id.strip():
        raise GoogleConnectorError("A Gmail message ID is required.")
    return {"ok": True, "message": _gmail_message(message_id.strip())}


def drive_search_files(query: str = "", count: int = 10) -> dict[str, Any]:
    count = max(1, min(int(count), 50))
    params = {
        "pageSize": count,
        "orderBy": "modifiedTime desc",
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,description,size)",
    }
    if query.strip():
        escaped = query.replace("'", "\\'")
        params["q"] = f"trashed = false and fullText contains '{escaped}'"
    payload = _request("google_drive", "GET", "https://www.googleapis.com/drive/v3/files", params=params)
    return {"ok": True, "files": payload.get("files") or []}


def calendar_list_events(start_iso: str = "", end_iso: str = "", count: int = 10) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    params = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": max(1, min(int(count), 50)),
        "timeMin": start_iso or now.isoformat().replace("+00:00", "Z"),
        "timeMax": end_iso or (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
    }
    payload = _request(
        "google_calendar",
        "GET",
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        params=params,
    )
    return {"ok": True, "events": payload.get("items") or []}


def calendar_list_calendars() -> dict[str, Any]:
    payload = _request(
        "google_calendar",
        "GET",
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        params={"fields": "items(id,summary,primary,accessRole,timeZone)"},
    )
    return {"ok": True, "calendars": payload.get("items") or []}
