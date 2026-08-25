"""Local-first chat export parsing and scoped persona signal extraction."""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from statistics import median
from typing import Any


MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_ZIP_TEXT_BYTES = 25 * 1024 * 1024
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'_-]{2,}")
WA_LINE = re.compile(r"^(?:\[)?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4})(?:,?\s+|\s+)(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APMapm]{2})?)(?:\]|\s+-\s+)?\s*(?P<author>[^:]+):\s(?P<text>.*)$")

STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "will", "your", "you", "are", "for", "but",
    "not", "was", "were", "what", "when", "where", "how", "can", "just", "like", "its", "our", "they",
    "i", "a", "an", "to", "of", "in", "on", "is", "it", "be", "we", "my", "me", "or", "so", "do", "if",
}
POSITIVE_WORDS = {"good", "great", "nice", "love", "happy", "thanks", "thank", "perfect", "awesome", "yes", "glad", "excited", "helpful", "better"}
NEGATIVE_WORDS = {"bad", "sad", "angry", "sorry", "hate", "problem", "wrong", "worried", "stress", "stressed", "difficult", "annoying", "upset"}
PLANNING_WORDS = {"plan", "next", "step", "todo", "priority", "deadline", "finish", "build", "ship", "schedule", "goal"}
REASONING_WORDS = {"because", "however", "therefore", "option", "reason", "tradeoff", "trade-off", "compare", "decide", "decision"}
SUPPORT_WORDS = {"thanks", "thank", "sorry", "great", "love", "appreciate", "help", "support", "care"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _words(text: str) -> list[str]:
    return [item.casefold() for item in WORD_RE.findall(text or "")]


def _parse_date(date_text: str, time_text: str) -> datetime:
    date_text = date_text.replace(".", "/").replace("-", "/")
    parts = [int(item) for item in date_text.split("/")]
    if parts[0] > 31:
        year, month, day = parts
    elif parts[2] > 31:
        day, month, year = parts
    else:
        month, day, year = parts
    if year < 100:
        year += 2000
    clean_time = re.sub(r"\s+", " ", time_text.strip()).upper()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            parsed = datetime.strptime(f"{day:02d}/{month:02d}/{year:04d} {clean_time}", f"%d/%m/%Y {fmt}")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _now()


def _parse_whatsapp(text: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff")
        match = WA_LINE.match(line)
        if match:
            current = {
                "id": str(uuid.uuid4()),
                "author": match.group("author").strip(),
                "text": match.group("text").strip(),
                "created_at": _parse_date(match.group("date"), match.group("time")),
            }
            messages.append(current)
        elif current and line:
            current["text"] = f"{current['text']} {line}".strip()
    return [item for item in messages if item["text"] and not item["text"].startswith("<Media omitted")]


def _parse_telegram(value: Any) -> list[dict[str, Any]]:
    raw_messages = value.get("messages", []) if isinstance(value, dict) else value
    result: list[dict[str, Any]] = []
    for item in raw_messages if isinstance(raw_messages, list) else []:
        if not isinstance(item, dict) or item.get("type") not in (None, "message"):
            continue
        text = item.get("text", "")
        if isinstance(text, list):
            text = "".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in text)
        text = str(text).strip()
        if not text:
            continue
        created = str(item.get("date") or "")
        try:
            timestamp = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            timestamp = _now()
        result.append({
            "id": str(uuid.uuid4()),
            "author": str(item.get("from") or "Unknown").strip(),
            "text": text,
            "created_at": timestamp,
        })
    return result


def _dimension(messages: list[dict[str, Any]], words: list[str]) -> list[dict[str, Any]]:
    text = " ".join(str(item["text"]) for item in messages).casefold()
    count = max(len(messages), 1)
    question_rate = text.count("?") / count
    avg_words = len(words) / count
    directness = min(1, max(-1, (text.count("!") / count) * .25 + (avg_words - 10) / 40))
    analytical = min(1, max(-1, (sum(text.count(term) for term in ("because", "however", "plan", "why", "option")) / count) * .12))
    supportive = min(1, max(-1, (sum(text.count(term) for term in ("thanks", "thank", "sorry", "great", "love")) / count) * .15))
    structured = min(1, max(-1, (sum(text.count(term) for term in ("first", "then", "step", "todo", "next")) / count) * .14))
    values = {"directness": directness, "detail": (avg_words - 10) / 25, "analysis": analytical, "creativity": text.count("idea") / count * .15, "risk_tolerance": question_rate * .08, "supportiveness": supportive, "structure": structured}
    labels = {
        "directness": ("Communication", "Reflective", "Direct"), "detail": ("Response depth", "Concise", "Detailed"),
        "analysis": ("Thinking style", "Intuitive", "Analytical"), "creativity": ("Idea style", "Practical", "Imaginative"),
        "risk_tolerance": ("Decision posture", "Cautious", "Bold"), "supportiveness": ("Interaction energy", "Challenging", "Supportive"),
        "structure": ("Work style", "Exploratory", "Structured"),
    }
    return [{"key": key, "label": meta[0], "score": round((max(-1, min(1, values[key])) + 1) * 50), "confidence": min(90, 30 + len(messages) // 5), "low_label": meta[1], "high_label": meta[2]} for key, meta in labels.items()]


def _extract_statements(messages: list[dict[str, Any]], pattern: str, limit: int = 8) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    matcher = re.compile(pattern, re.I)
    for item in messages:
        text = " ".join(str(item.get("text") or "").split())
        if matcher.search(text) and 4 <= len(_words(text)) <= 35:
            result.append({"author": str(item.get("author") or "Unknown")[:60], "text": text[:240]})
        if len(result) >= limit:
            break
    return result


def _topic_graph(messages: list[dict[str, Any]], top_words: list[tuple[str, int]]) -> dict[str, Any]:
    names = [word for word, _ in top_words[:8]]
    node_counts = dict(top_words[:8])
    edge_counts: Counter[tuple[str, str]] = Counter()
    for item in messages:
        present = sorted({word for word in _words(item["text"]) if word in node_counts})
        for index, left in enumerate(present):
            for right in present[index + 1:]:
                edge_counts[(left, right)] += 1
    maximum = max(node_counts.values(), default=1)
    return {
        "nodes": [{"id": name, "label": name, "weight": round(node_counts[name] / maximum * 100)} for name in names],
        "edges": [{"source": left, "target": right, "weight": count} for (left, right), count in edge_counts.most_common(12)],
    }


def _behavior_metrics(messages: list[dict[str, Any]], words: list[str]) -> dict[str, Any]:
    ordered = sorted(messages, key=lambda item: item["created_at"])
    message_count = max(1, len(ordered))
    word_lists = [_words(item["text"]) for item in ordered]
    reply_minutes = []
    initiations: Counter[str] = Counter()
    previous = None
    for item in ordered:
        if previous is None or (item["created_at"] - previous["created_at"]).total_seconds() >= 6 * 3600:
            initiations[item["author"]] += 1
        if previous and item["author"] != previous["author"]:
            delay = (item["created_at"] - previous["created_at"]).total_seconds() / 60
            if 0 <= delay <= 24 * 60:
                reply_minutes.append(delay)
        previous = item
    heatmap = [[0 for _ in range(24)] for _ in range(7)]
    month_counts: Counter[str] = Counter()
    for item in ordered:
        heatmap[item["created_at"].weekday()][item["created_at"].hour] += 1
        month_counts[item["created_at"].strftime("%Y-%m")] += 1
    text_words = [word.casefold() for word in words]
    positive_hits = sum(1 for word in text_words if word in POSITIVE_WORDS)
    negative_hits = sum(1 for word in text_words if word in NEGATIVE_WORDS)
    question_messages = sum(1 for item in ordered if "?" in item["text"])
    long_messages = sum(1 for item_words in word_lists if len(item_words) >= 30)
    quick_messages = sum(1 for item_words in word_lists if len(item_words) <= 5)
    reasoning_hits = sum(1 for word in text_words if word in REASONING_WORDS)
    planning_hits = sum(1 for word in text_words if word in PLANNING_WORDS)
    support_hits = sum(1 for word in text_words if word in SUPPORT_WORDS)
    lexical_total = max(1, positive_hits + negative_hits)
    data_score = round(reasoning_hits / max(1, reasoning_hits + question_messages) * 100)
    return {
        "median_reply_minutes": round(median(reply_minutes), 1) if reply_minutes else None,
        "reply_samples": len(reply_minutes),
        "initiations": [{"author": author, "count": count} for author, count in initiations.most_common(6)],
        "heatmap": [{"day": DAYS[index], "hours": hours} for index, hours in enumerate(heatmap)],
        "monthly_activity": [{"month": month, "count": count} for month, count in sorted(month_counts.items())[-12:]],
        "tone": {
            "positive": round(positive_hits / lexical_total * 100),
            "negative": round(negative_hits / lexical_total * 100),
            "curiosity": round(question_messages / message_count * 100),
            "supportive_language": min(100, round(support_hits / message_count * 300)),
        },
        "attention": {
            "deep_messages": round(long_messages / message_count * 100),
            "quick_messages": round(quick_messages / message_count * 100),
            "question_led": round(question_messages / message_count * 100),
        },
        "decision_style": {"evidence_led": data_score, "exploratory": 100 - data_score, "reasoning_markers": reasoning_hits, "planning_markers": planning_hits},
    }


def analyze_messages(messages: list[dict[str, Any]], filename: str, format_name: str) -> dict[str, Any]:
    words = [word for item in messages for word in _words(item["text"])]
    top_words = Counter(word for word in words if word not in STOPWORDS).most_common(12)
    total_words = len(words)
    avg_words = round(total_words / max(len(messages), 1), 1)
    author_counts = Counter(item["author"] for item in messages)
    text = " ".join(item["text"] for item in messages).casefold()
    dimensions = _dimension(messages, words)
    behavior = _behavior_metrics(messages, words)
    observations = []
    if avg_words >= 18:
        observations.append({"category": "communication", "title": "Detailed exchange", "description": "Messages in this conversation often carry context and explanation.", "confidence": min(92, 45 + len(messages) // 4)})
    if text.count("?") / max(len(messages), 1) >= .25:
        observations.append({"category": "curiosity", "title": "Question-led interaction", "description": "Questions frequently explore, clarify, or keep the conversation moving.", "confidence": min(90, 45 + len(messages) // 4)})
    if sum(text.count(term) for term in ("plan", "next", "step", "todo")) >= max(3, len(messages) // 15):
        observations.append({"category": "structure", "title": "Action-oriented style", "description": "Planning and next steps appear regularly in this conversation.", "confidence": min(90, 45 + len(messages) // 4)})
    strongest = sorted(dimensions, key=lambda item: abs(item["score"] - 50), reverse=True)[:3]
    profile = {
        "title": "Conversation behavior profile",
        "summary": f"A rule-based snapshot of {len(messages):,} messages across {len(author_counts)} participants. Strongest measured signals are {', '.join(item['label'].lower() for item in strongest) or 'still emerging'}.",
        "traits": [{"name": item["label"], "score": item["score"]} for item in strongest],
        "method": "Deterministic analysis from message structure, timing, and vocabulary. No LLM used.",
    }
    return {
        "name": filename.rsplit(".", 1)[0][:80] or "Imported conversation",
        "format": format_name,
        "message_count": len(messages), "word_count": total_words, "average_message_words": avg_words,
        "participant_count": len(author_counts),
        "participants": [{"name": author, "messages": count, "share": round(count / max(1, len(messages)) * 100)} for author, count in author_counts.most_common(8)],
        "top_words": [{"word": word, "count": count} for word, count in top_words],
        "active_hours": [{"hour": hour, "count": count} for hour, count in Counter(item["created_at"].hour for item in messages).most_common(5)],
        "dimensions": dimensions, "observations": observations,
        "topics": [{"name": word, "score": round(count / max(top_words[0][1], 1) * 100)} for word, count in top_words[:8]],
        "topic_graph": _topic_graph(messages, top_words),
        "behavior": behavior,
        "preference_statements": _extract_statements(messages, r"\b(i|we)\s+(prefer|like|love|need|want|usually|don't|do not)\b"),
        "goal_statements": _extract_statements(messages, r"\b(i|we)\s+(want to|need to|plan to|will|should)\b|\b(goal|deadline|finish|build|ship)\b"),
        "profile": profile,
        "source_summary": {"format": format_name, "message_count": len(messages), "word_count": total_words, "participant_count": len(author_counts)},
    }


def analyze_upload(filename: str, content: bytes) -> dict[str, Any]:
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("This export is larger than 25 MB. Please export a smaller date range.")
    lower = filename.casefold()
    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                candidates = [
                    item for item in archive.infolist()
                    if not item.is_dir() and item.filename.casefold().endswith(".txt")
                ]
                if not candidates:
                    raise ValueError("That WhatsApp ZIP does not contain a chat .txt file.")
                preferred = [item for item in candidates if item.filename.casefold().endswith("_chat.txt")]
                entry = preferred[0] if preferred else candidates[0]
                if entry.file_size > MAX_ZIP_TEXT_BYTES:
                    raise ValueError("The chat text inside this ZIP is larger than 25 MB.")
                if entry.filename.startswith(("/", "\\")) or ".." in entry.filename.replace("\\", "/").split("/"):
                    raise ValueError("That ZIP contains an unsafe file path.")
                raw_text = archive.read(entry)
                source_name = entry.filename.rsplit("/", 1)[-1]
        except zipfile.BadZipFile as exc:
            raise ValueError("That ZIP export could not be read.") from exc
        try:
            decoded = raw_text.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("The WhatsApp chat text must be UTF-8 encoded.") from exc
        messages, format_name = _parse_whatsapp(decoded), "WhatsApp ZIP"
        filename = source_name
    else:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 chat exports are supported.") from exc
    if lower.endswith(".json"):
        try:
            messages = _parse_telegram(json.loads(decoded))
        except json.JSONDecodeError as exc:
            raise ValueError("That Telegram JSON export could not be read.") from exc
        format_name = "Telegram JSON"
    elif lower.endswith(".txt"):
        messages, format_name = _parse_whatsapp(decoded), "WhatsApp TXT"
    elif not lower.endswith(".zip"):
        raise ValueError("Upload a WhatsApp .zip/.txt export or Telegram .json export.")
    if len(messages) < 5:
        raise ValueError("At least 5 readable messages are needed for a chat profile.")
    return analyze_messages(messages, filename, format_name)
