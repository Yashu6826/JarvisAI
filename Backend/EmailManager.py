"""Email drafting and confirmed Gmail delivery through the connected account."""

from __future__ import annotations

import base64
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from Backend.GoogleOAuth import (
    GoogleOAuthError,
    current_session_id,
    google_access_token,
    google_connected_email,
    google_mcp_connected,
)
from Backend.LLMProvider import LMSTUDIO_MODEL, LocalLLMUnavailable, generate_text


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "Data"
EMAIL_RECORDS_PATH = DATA_DIR / "PendingEmails.json"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
PENDING_TTL = timedelta(minutes=30)
DRAFT_TTL = timedelta(hours=24)
MAX_EMAIL_RECORDS = 200
_lock = threading.RLock()


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


class EmailDraftError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now() -> str:
    return _now().isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _session_id() -> str:
    session_id = current_session_id()
    if not session_id:
        raise EmailConfigurationError(
            "No browser session is available. Refresh Nexa and reconnect Gmail."
        )
    return session_id


def _extract_addresses(value: str) -> list[str]:
    seen: set[str] = set()
    addresses: list[str] = []
    for match in EMAIL_PATTERN.findall(value or ""):
        lowered = match.lower()
        if lowered not in seen:
            seen.add(lowered)
            addresses.append(match)
    return addresses


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise EmailDraftError("The email draft model did not return JSON.")
    try:
        payload = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise EmailDraftError("The email draft model returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise EmailDraftError("The email draft model returned an unexpected structure.")
    return payload


def _read_records_unlocked() -> list[dict[str, Any]]:
    try:
        data = json.loads(EMAIL_RECORDS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_records_unlocked(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = EMAIL_RECORDS_PATH.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(items[-MAX_EMAIL_RECORDS:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(EMAIL_RECORDS_PATH)


def _expire_records(items: list[dict[str, Any]]) -> bool:
    changed = False
    now = _now()
    for item in items:
        status = item.get("status")
        created_at = _parse_time(item.get("created_at"))
        if not created_at:
            continue
        if status == "pending_confirmation" and now - created_at > PENDING_TTL:
            item["status"] = "expired"
            item["expired_at"] = now.isoformat()
            changed = True
        elif status == "draft" and now - created_at > DRAFT_TTL:
            item["status"] = "expired"
            item["expired_at"] = now.isoformat()
            changed = True
    return changed


def _load_records() -> list[dict[str, Any]]:
    with _lock:
        items = _read_records_unlocked()
        if _expire_records(items):
            _write_records_unlocked(items)
        return items


def _save_records(items: list[dict[str, Any]]) -> None:
    with _lock:
        _write_records_unlocked(items)


def _pending_email_payload(item: dict[str, Any]) -> dict[str, object]:
    return {
        "id": item["id"],
        "sender": item.get("sender", ""),
        "to": list(item.get("to", [])),
        "cc": list(item.get("cc", [])),
        "bcc": list(item.get("bcc", [])),
        "bcc_count": len(item.get("bcc", [])),
        "subject": item["subject"],
        "body": item["body"],
        "status": item["status"],
        "created_at": item["created_at"],
        "expires_at": item.get("expires_at", ""),
        "request_text": str(item.get("request_text", "")),
    }


def _draft_payload(item: dict[str, Any]) -> dict[str, object]:
    return {
        "id": item["id"],
        "to": list(item.get("to", [])),
        "cc": list(item.get("cc", [])),
        "bcc_count": len(item.get("bcc", [])),
        "subject": item["subject"],
        "body": item["body"],
        "status": item["status"],
        "created_at": item["created_at"],
    }


def email_configuration_status() -> dict[str, object]:
    connected = google_mcp_connected("gmail")
    return {
        "configured": connected,
        "connected": connected,
        "sender": google_connected_email("gmail") if connected else "",
        "delivery": "gmail_oauth",
    }


def draft_email(request: str) -> dict[str, str]:
    prompt = request.strip()
    if not prompt:
        raise EmailDraftError("The email request was empty.")

    system = (
        "You write polished emails. Return strict JSON with exactly two keys: "
        "`subject` and `body`. The subject must be concise. The body must be "
        "plain text only, with normal paragraph breaks and no Markdown. Do not "
        "invent recipient addresses, facts, dates, or commitments."
    )

    try:
        response = generate_text(
            prompt=prompt,
            system=system,
            model=LMSTUDIO_MODEL,
            temperature=0.2,
            reasoning="off",
        )
    except LocalLLMUnavailable as exc:
        raise EmailDraftError(str(exc)) from exc
    except Exception as exc:
        raise EmailDraftError(
            f"Could not draft the email: {type(exc).__name__}: {exc}"
        ) from exc

    payload = _parse_json_object(response)
    subject = " ".join(str(payload.get("subject", "")).split()).strip()
    body = str(payload.get("body", "")).strip()
    if not subject or not body:
        raise EmailDraftError("The generated email draft was incomplete.")
    return {"subject": subject, "body": body}


def save_email_draft(
    *,
    recipient: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    request_text: str = "",
) -> dict[str, object]:
    """Store a short-lived local draft so a later send tool can reference it."""
    clean_subject = " ".join(subject.split()).strip()
    clean_body = body.strip()
    if not clean_subject or not clean_body:
        raise EmailDraftError("The generated email draft was incomplete.")
    item = {
        "id": uuid4().hex,
        "session_id": _session_id(),
        "sender": google_connected_email("gmail"),
        "to": _extract_addresses(recipient),
        "cc": _extract_addresses(cc),
        "bcc": _extract_addresses(bcc),
        "subject": clean_subject,
        "body": clean_body,
        "status": "draft",
        "created_at": _utc_now(),
        "request_text": request_text.strip(),
    }
    with _lock:
        items = _read_records_unlocked()
        _expire_records(items)
        items.append(item)
        _write_records_unlocked(items)
    return _draft_payload(item)


def get_email_draft(draft_id: str) -> dict[str, Any]:
    session_id = _session_id()
    for item in _load_records():
        if item.get("id") != draft_id:
            continue
        if item.get("session_id") != session_id:
            raise EmailDeliveryError("That email draft belongs to another browser session.")
        if item.get("status") != "draft":
            raise EmailDeliveryError("That email draft is no longer available.")
        return dict(item)
    raise EmailDeliveryError("Email draft not found.")


def create_pending_email(
    recipient: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    request_text: str = "",
    validate_config: bool = True,
    allow_empty_recipients: bool = False,
) -> dict[str, object]:
    session_id = _session_id()
    sender = google_connected_email("gmail")
    if validate_config and (not google_mcp_connected("gmail") or not sender):
        raise EmailConfigurationError(
            "Gmail is not connected in this browser. Connect Gmail in Nexa before sending."
        )

    to_addresses = _extract_addresses(recipient)
    cc_addresses = _extract_addresses(cc)
    bcc_addresses = _extract_addresses(bcc)
    if not allow_empty_recipients and not to_addresses:
        raise EmailDeliveryError("At least one valid recipient email address is required.")

    clean_subject = " ".join(subject.split()).strip()
    clean_body = body.strip()
    if not clean_subject:
        raise EmailDeliveryError("The email subject was empty.")
    if not clean_body:
        raise EmailDeliveryError("The email body was empty.")

    with _lock:
        items = _read_records_unlocked()
        _expire_records(items)
        for item in items:
            if (
                item.get("status") == "pending_confirmation"
                and item.get("session_id") == session_id
            ):
                item["status"] = "superseded"
                item["superseded_at"] = _utc_now()

        created_at = _now()
        pending_email = {
            "id": uuid4().hex,
            "session_id": session_id,
            "sender": sender,
            "to": to_addresses,
            "cc": cc_addresses,
            "bcc": bcc_addresses,
            "subject": clean_subject,
            "body": clean_body,
            "status": "pending_confirmation",
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + PENDING_TTL).isoformat(),
            "request_text": request_text.strip(),
        }
        items.append(pending_email)
        _write_records_unlocked(items)
    return _pending_email_payload(pending_email)


def get_latest_pending_email() -> dict[str, object] | None:
    try:
        session_id = _session_id()
    except EmailConfigurationError:
        return None
    pending_items = [
        item
        for item in _load_records()
        if isinstance(item, dict)
        and item.get("status") == "pending_confirmation"
        and item.get("session_id") == session_id
    ]
    return _pending_email_payload(pending_items[-1]) if pending_items else None


def confirm_pending_email(
    email_id: str,
    recipient: str = "",
    cc: str = "",
    bcc: str = "",
) -> dict[str, object]:
    session_id = _session_id()
    with _lock:
        items = _read_records_unlocked()
        _expire_records(items)
        for item in items:
            if item.get("id") != email_id:
                continue
            if item.get("session_id") != session_id:
                raise EmailDeliveryError(
                    "That email belongs to a different browser session."
                )
            if item.get("status") != "pending_confirmation":
                raise EmailDeliveryError(
                    "That email is no longer waiting for confirmation."
                )

            resolved_to = _extract_addresses(recipient) or list(item.get("to", []))
            resolved_cc = _extract_addresses(cc) or list(item.get("cc", []))
            resolved_bcc = _extract_addresses(bcc) or list(item.get("bcc", []))
            if not resolved_to:
                raise EmailDeliveryError(
                    "Enter at least one valid recipient email address before sending."
                )

            result = send_gmail_email(
                recipient=", ".join(resolved_to),
                subject=str(item.get("subject", "")),
                body=str(item.get("body", "")),
                cc=", ".join(resolved_cc),
                bcc=", ".join(resolved_bcc),
            )
            item["to"] = resolved_to
            item["cc"] = resolved_cc
            item["bcc"] = resolved_bcc
            item["sender"] = result["sender"]
            item["status"] = "sent"
            item["sent_at"] = _utc_now()
            item["gmail_message_id"] = result.get("message_id", "")
            item["gmail_thread_id"] = result.get("thread_id", "")
            _write_records_unlocked(items)
            return {
                **result,
                "id": item["id"],
                "request_text": str(item.get("request_text", "")),
                "body": str(item.get("body", "")),
            }
    raise EmailDeliveryError("Pending email not found.")


def cancel_pending_email(email_id: str) -> dict[str, object]:
    session_id = _session_id()
    with _lock:
        items = _read_records_unlocked()
        _expire_records(items)
        for item in items:
            if item.get("id") != email_id:
                continue
            if item.get("session_id") != session_id:
                raise EmailDeliveryError(
                    "That email belongs to a different browser session."
                )
            if item.get("status") != "pending_confirmation":
                raise EmailDeliveryError(
                    "That email is no longer waiting for confirmation."
                )
            item["status"] = "cancelled"
            item["cancelled_at"] = _utc_now()
            _write_records_unlocked(items)
            return {
                "id": item["id"],
                "to": list(item.get("to", [])),
                "subject": str(item.get("subject", "")),
                "request_text": str(item.get("request_text", "")),
            }
    raise EmailDeliveryError("Pending email not found.")


def send_gmail_email(
    recipient: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> dict[str, object]:
    """Send through Gmail API using the current browser's connected account."""
    sender = google_connected_email("gmail")
    if not sender or not google_mcp_connected("gmail"):
        raise EmailConfigurationError(
            "Gmail is not connected in this browser. Connect Gmail in Nexa before sending."
        )

    to_addresses = _extract_addresses(recipient)
    cc_addresses = _extract_addresses(cc)
    bcc_addresses = _extract_addresses(bcc)
    if not to_addresses:
        raise EmailDeliveryError("At least one valid recipient email address is required.")

    clean_subject = " ".join(subject.split()).strip()
    clean_body = body.strip()
    if not clean_subject:
        raise EmailDeliveryError("The email subject was empty.")
    if not clean_body:
        raise EmailDeliveryError("The email body was empty.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    if bcc_addresses:
        message["Bcc"] = ", ".join(bcc_addresses)
    message["Subject"] = clean_subject
    message.set_content(clean_body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    try:
        access_token = google_access_token("gmail")
        response = requests.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"raw": encoded},
            timeout=30,
        )
    except GoogleOAuthError as exc:
        raise EmailConfigurationError(str(exc)) from exc
    except requests.RequestException as exc:
        raise EmailDeliveryError(
            "Could not reach the Gmail API. Check the internet connection and try again."
        ) from exc

    if not response.ok:
        try:
            payload = response.json()
            detail = str((payload.get("error") or {}).get("message") or "")
        except (TypeError, ValueError):
            detail = ""
        if response.status_code in {401, 403}:
            raise EmailDeliveryError(
                "Gmail did not authorize sending. Reconnect Gmail in Nexa and try again."
            )
        raise EmailDeliveryError(
            f"Gmail rejected the message{f': {detail}' if detail else '.'}"
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise EmailDeliveryError("Gmail returned an unexpected response.") from exc
    return {
        "sender": sender,
        "to": to_addresses,
        "cc": cc_addresses,
        "bcc_count": len(bcc_addresses),
        "subject": clean_subject,
        "message_id": str(result.get("id") or ""),
        "thread_id": str(result.get("threadId") or ""),
    }
