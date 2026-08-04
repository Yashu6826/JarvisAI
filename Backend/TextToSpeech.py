import logging
import random

from Backend.LLMProvider import get_config

logger = logging.getLogger(__name__)

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

TTS_RATE = int(get_config("LOCAL_TTS_RATE", "185"))
TTS_VOLUME = float(get_config("LOCAL_TTS_VOLUME", "1.0"))
FEMALE_VOICE_HINTS = [
    hint.strip().lower()
    for hint in get_config(
        "LOCAL_FEMALE_VOICE_HINTS", "zira,hazel,heera,female"
    ).split(",")
    if hint.strip()
]


def _set_preferred_voice(engine, voice_preference: str) -> None:
    if voice_preference != "female":
        return
    for voice in engine.getProperty("voices"):
        description = f"{voice.name} {voice.id}".lower()
        if any(hint in description for hint in FEMALE_VOICE_HINTS):
            engine.setProperty("voice", voice.id)
            return
    logger.warning("No preferred female Windows voice was found; using the default voice.")


def TTS(
    text: str,
    func=lambda value=None: True,
    voice_preference: str = "",
) -> bool:
    if pyttsx3 is None:
        logger.error("Local text-to-speech is unavailable. Install pyttsx3.")
        return False
    if func() is False:
        return False

    engine = None
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", TTS_RATE)
        engine.setProperty("volume", max(0.0, min(TTS_VOLUME, 1.0)))
        _set_preferred_voice(engine, voice_preference)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as exc:
        logger.error("Local text-to-speech failed: %s", exc)
        return False
    finally:
        if engine is not None:
            engine.stop()
        func(False)


def TextToSpeech(text: str, func=lambda value=None: True) -> bool:
    sentences = str(text).split(".")
    responses = [
        "The rest of the answer is on the chat screen.",
        "Please check the chat screen for the full answer.",
        "The complete response is visible in the chat screen.",
    ]
    if len(sentences) > 4 and len(text) >= 250:
        spoken_text = ". ".join(sentences[:2]).strip() + ". " + random.choice(responses)
        return TTS(spoken_text, func)
    return TTS(str(text), func)


def ThinkingToSpeech(summary: str, func=lambda value=None: True) -> bool:
    return TTS(summary, func, voice_preference="female")


if __name__ == "__main__":
    while True:
        TextToSpeech(input("Enter text: "))
