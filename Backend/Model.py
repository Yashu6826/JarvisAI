import re

from Backend.LLMProvider import LMSTUDIO_MODEL, LocalLLMUnavailable, generate_text

funcs = [
    "exit",
    "general",
    "realtime",
    "open",
    "close",
    "generate image",
    "system",
    "content",
]

preamble = """
You are a local command router for a desktop assistant. Classify the user request.
Return only one or more comma-separated commands. Do not explain.

Allowed commands:
- general <query>: normal conversation or questions answerable from offline model knowledge.
- realtime <query>: facts that require live web information, including prices,
  weather, news, sports, current people/roles, or an explicit web/Google search.
- open <website or local application name>: open a website or installed application.
- close <local application name>: close an installed local application.
- generate image <prompt>: create an image with the local Stable Diffusion server.
- system <mute|unmute|volume up|volume down>: change the computer volume.
- content <topic>: write a document locally and open it in Notepad.
- exit: close the assistant.

Use realtime whenever the answer may have changed since the model was trained.
Opening a website is an open command, not a realtime command.
"""


def _valid_decisions(response: str, prompt: str) -> list[str]:
    decisions = [item.strip() for item in response.replace("\n", " ").split(",")]
    valid = []
    for task in decisions:
        normalized = task.lower()
        if normalized == "exit":
            valid.append("exit")
            continue
        if any(normalized.startswith(f"{func} ") for func in funcs if func != "exit"):
            valid.append(task)
    return valid or [f"general {prompt}"]


def _deterministic_command(prompt: str) -> list[str] | None:
    normalized = " ".join(prompt.lower().strip().split())
    if normalized in {"bye", "goodbye", "exit", "quit", "close jarvis"}:
        return ["exit"]

    for command in ("open", "close"):
        match = re.search(rf"\b{command}\s+(.+)", normalized)
        if match:
            return [f"{command} {match.group(1).strip()}"]

    realtime_markers = (
        "price of ",
        "stock price",
        "share price",
        "latest ",
        "current ",
        "today",
        "news",
        "weather",
        "google search",
        "search google",
        "search the web",
        "look up",
    )
    if any(marker in normalized for marker in realtime_markers):
        return [f"realtime {prompt.strip()}"]

    image_match = re.search(r"\b(?:generate|create|make)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+)", normalized)
    if image_match:
        return [f"generate image {image_match.group(1).strip()}"]

    if normalized in {"mute", "unmute", "volume up", "volume down"}:
        return [f"system {normalized}"]

    if normalized.startswith("content "):
        return [f"content {normalized.removeprefix('content ').strip()}"]
    if normalized.startswith(("write ", "draft ", "compose ")):
        return [f"content {prompt.strip()}"]
    return None


def FirstLayerDMM(prompt: str = "test") -> list[str]:
    direct_command = _deterministic_command(prompt)
    if direct_command:
        return direct_command

    try:
        response = generate_text(
            prompt=prompt,
            system=preamble,
            model=LMSTUDIO_MODEL,
            temperature=0.1,
        )
    except LocalLLMUnavailable:
        return [f"general {prompt}"]
    except Exception:
        return [f"general {prompt}"]
    return _valid_decisions(response, prompt)


if __name__ == "__main__":
    while True:
        print(FirstLayerDMM(input(">>> ")))
