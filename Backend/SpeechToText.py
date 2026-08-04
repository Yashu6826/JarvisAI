import json
import logging
import queue
import time
import audioop
from pathlib import Path

from Backend.LLMProvider import get_config

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel
except ImportError:
    sd = None
    KaldiRecognizer = None
    Model = None
    SetLogLevel = None

INPUT_LANGUAGE = get_config("INPUT_LANGUAGE", "en")
VOSK_MODEL_PATH = Path(get_config("VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15"))
VOSK_SAMPLE_RATE = int(get_config("VOSK_SAMPLE_RATE", "16000"))
VOSK_LISTEN_SECONDS = float(get_config("VOSK_LISTEN_SECONDS", "12"))
VOSK_INPUT_DEVICE = get_config("VOSK_INPUT_DEVICE", "").strip()
VOSK_PAUSE_SECONDS = float(get_config("VOSK_PAUSE_SECONDS", "1.0"))
_model = None


def SetAssistantStatus(status: str) -> None:
    status_path = Path("Frontend/Graphics/Status.data")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(status, encoding="utf-8")


def QueryModifier(query: str) -> str:
    normalized = " ".join(query.lower().strip().split())
    if not normalized:
        return ""
    question_starters = (
        "how",
        "what",
        "who",
        "where",
        "when",
        "why",
        "which",
        "whose",
        "whom",
        "can you",
    )
    normalized = normalized.rstrip(".?!")
    punctuation = "?" if normalized.startswith(question_starters) else "."
    return normalized[:1].upper() + normalized[1:] + punctuation


def _load_model():
    global _model
    if Model is None or sd is None:
        raise RuntimeError("Install the local speech packages from Requirements.txt.")
    if not VOSK_MODEL_PATH.is_dir():
        raise RuntimeError(
            f"Offline Vosk model not found at '{VOSK_MODEL_PATH}'. "
            "Download the small model listed in LOCAL_SETUP.md."
        )
    if _model is None:
        SetLogLevel(-1)
        _model = Model(str(VOSK_MODEL_PATH))
    return _model


def _input_device():
    if not VOSK_INPUT_DEVICE:
        return None
    try:
        return int(VOSK_INPUT_DEVICE)
    except ValueError:
        return VOSK_INPUT_DEVICE


def SpeechRecognition() -> str:
    try:
        model = _load_model()
    except RuntimeError as exc:
        logger.error("%s", exc)
        SetAssistantStatus("Offline speech setup required")
        return ""


def TranscribePCM(audio: bytes, sample_rate: int) -> str:
    """Transcribe 16-bit, mono PCM received from the browser microphone."""
    if not audio:
        return ""
    try:
        model = _load_model()
    except RuntimeError:
        raise
    if sample_rate < 8_000 or sample_rate > 96_000:
        raise RuntimeError("Unsupported microphone sample rate.")

    try:
        if sample_rate != VOSK_SAMPLE_RATE:
            audio, _ = audioop.ratecv(
                audio,
                2,
                1,
                sample_rate,
                VOSK_SAMPLE_RATE,
                None,
            )
        recognizer = KaldiRecognizer(model, VOSK_SAMPLE_RATE)
        chunk_size = 8_000
        for offset in range(0, len(audio), chunk_size):
            recognizer.AcceptWaveform(audio[offset:offset + chunk_size])
        text = json.loads(recognizer.FinalResult()).get("text", "")
        return QueryModifier(text)
    except Exception as exc:
        logger.exception("Browser audio transcription failed")
        raise RuntimeError("NEXA could not process the captured audio.") from exc

    audio_queue: queue.Queue[bytes] = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            logger.warning("Audio input status: %s", status)
        audio_queue.put(bytes(indata))

    recognizer = KaldiRecognizer(model, VOSK_SAMPLE_RATE)
    deadline = time.monotonic() + VOSK_LISTEN_SECONDS
    partial_text = ""
    last_partial_change = time.monotonic()
    SetAssistantStatus("Listening...")
    logger.info(
        "Listening with Vosk input device %s at %s Hz.",
        _input_device() if _input_device() is not None else "default",
        VOSK_SAMPLE_RATE,
    )

    try:
        with sd.RawInputStream(
            device=_input_device(),
            samplerate=VOSK_SAMPLE_RATE,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while time.monotonic() < deadline:
                try:
                    audio = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(audio):
                    text = json.loads(recognizer.Result()).get("text", "")
                    if text:
                        return QueryModifier(text)
                else:
                    current_partial = json.loads(recognizer.PartialResult()).get("partial", "")
                    if current_partial != partial_text:
                        partial_text = current_partial
                        last_partial_change = time.monotonic()
                    elif (
                        partial_text
                        and time.monotonic() - last_partial_change >= VOSK_PAUSE_SECONDS
                    ):
                        return QueryModifier(partial_text)
            text = json.loads(recognizer.FinalResult()).get("text", "")
            return QueryModifier(text)
    except Exception as exc:
        logger.error("Offline speech recognition failed: %s", exc)
        SetAssistantStatus("Microphone unavailable")
        return ""


if __name__ == "__main__":
    while True:
        print(SpeechRecognition())
