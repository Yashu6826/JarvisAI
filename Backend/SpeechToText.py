"""Cloud speech-to-text compatibility helpers.

Local Vosk transcription has been removed from NEXA. Browser microphone audio is
handled by `Backend.WebApp` and sent to OpenRouter's transcription endpoint.
"""

from __future__ import annotations


def SpeechRecognition() -> str:
    raise RuntimeError("Local microphone speech recognition has been removed.")


def TranscribePCM(audio: bytes, sample_rate: int) -> str:
    from Backend.WebApp import _openrouter_transcription

    return _openrouter_transcription(audio, sample_rate)
