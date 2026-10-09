"""
Local voice I/O.

  transcribe(wav_bytes) -> text     via faster-whisper (speech-in)
  synthesize(text)      -> wav bytes via Piper       (speech-out)

Both libraries are imported lazily so the rest of the app runs even if voice
deps aren't installed. Models download on first use, then cache.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import wave
from functools import lru_cache

# Quieten the noisy Windows symlink / HF-token warnings before those libs import.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from core import config

# ---- speech-in: faster-whisper ------------------------------------------- #
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel  # lazy import

        _whisper_model = WhisperModel(
            config.VOICE.whisper_model,
            device="cpu",
            compute_type=config.VOICE.whisper_compute,
        )
    return _whisper_model


def transcribe(audio_bytes: bytes) -> str:
    """
    Transcribe audio (any ffmpeg-decodable container/bytes) to text.
    faster-whisper reads from a file path, so we spool to a temp file.
    """
    if not config.VOICE.enabled:
        return ""
    model = _get_whisper()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = model.transcribe(tmp_path, beam_size=1)
        return "".join(seg.text for seg in segments).strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---- speech-out: Piper ---------------------------------------------------- #
@lru_cache(maxsize=1)
def _piper_available() -> bool:
    # Either the `piper` CLI on PATH, or the `piper` python package.
    if shutil.which("piper"):
        return True
    try:
        import piper  # noqa: F401

        return True
    except ImportError:
        return False


def synthesize(text: str) -> bytes:
    """
    Turn text into 16-bit PCM WAV bytes with Piper. Returns b"" if unavailable
    or text is empty (the UI then just skips playback).
    """
    text = (text or "").strip()
    if not text or not config.VOICE.enabled or not _piper_available():
        return b""

    # Prefer the CLI (simplest, streams a wav to stdout).
    if shutil.which("piper"):
        try:
            proc = subprocess.run(
                ["piper", "--model", config.VOICE.piper_voice, "--output_file", "-"],
                input=text.encode("utf-8"),
                capture_output=True,
                check=True,
            )
            return proc.stdout
        except (subprocess.CalledProcessError, OSError):
            return b""

    # Fall back to the python package.
    try:
        from piper import PiperVoice

        voice = PiperVoice.load(config.VOICE.piper_voice)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize(text, wav)
        return buf.getvalue()
    except Exception:
        return b""
