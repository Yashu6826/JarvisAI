"""Cloud text-to-speech compatibility helpers.

Local desktop speech playback has been removed from NEXA. The React app calls
`/api/speech` and plays the OpenRouter-generated audio in the browser.
"""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)


def _spoken_preview(text: str) -> str:
    sentences = str(text).split(".")
    responses = [
        "The rest of the answer is on the chat screen.",
        "Please check the chat screen for the full answer.",
        "The complete response is visible in the chat screen.",
    ]
    if len(sentences) > 4 and len(text) >= 250:
        return ". ".join(sentences[:2]).strip() + ". " + random.choice(responses)
    return str(text)


def TTS(text: str, func=lambda value=None: True, voice_preference: str = "") -> bool:
    if func() is False:
        return False
    try:
        from Backend.WebApp import _openrouter_speech

        _openrouter_speech(_spoken_preview(text))
        return True
    except Exception as exc:
        logger.error("Cloud text-to-speech failed: %s", exc)
        return False
    finally:
        func(False)


def TextToSpeech(text: str, func=lambda value=None: True) -> bool:
    return TTS(text, func)


def ThinkingToSpeech(summary: str, func=lambda value=None: True) -> bool:
    return TTS(summary, func)


if __name__ == "__main__":
    while True:
        TextToSpeech(input("Enter text: "))
