"""Thin client for Gnani's Prisma (speech to text) and Timbre (text to speech) REST APIs."""
from __future__ import annotations

import hashlib

import requests

from . import config


class GnaniError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _headers() -> dict:
    return {"X-API-Key-ID": config.GNANI_API_KEY}


def _need_key() -> None:
    if not config.GNANI_API_KEY:
        raise GnaniError("no_api_key", status=503)


def _error_text(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return err.get("message") or resp.text[:200]
    except Exception:
        return resp.text[:200]


def transcribe(audio_bytes: bytes, filename: str = "audio.wav", language: str | None = None) -> str:
    """Prisma v2.5: audio file in, transcript out. Formats: wav/mp3/ogg/flac/aac/m4a, max 60 s."""
    _need_key()
    try:
        resp = requests.post(
            config.STT_URL,
            headers=_headers(),
            files={"audio_file": (filename, audio_bytes)},
            data={"language_code": language or config.STT_LANGUAGE},
            timeout=45,
        )
    except requests.RequestException as e:
        raise GnaniError(f"stt_network_error: {e}") from e
    if resp.status_code != 200:
        raise GnaniError(f"stt_failed: {_error_text(resp)}", status=resp.status_code)
    data = resp.json()
    if not data.get("success", True):
        raise GnaniError(f"stt_failed: {data}")
    return (data.get("transcript") or "").strip()


def synthesize(text: str) -> bytes:
    """Timbre: text in, WAV audio out. Cached on disk so repeated lines cost nothing."""
    _need_key()
    key = hashlib.sha256(
        f"{config.TTS_MODEL}|{config.TTS_VOICE}|{config.TTS_LANGUAGE}|{config.TTS_SPEED}|{text}".encode()
    ).hexdigest()
    cached = config.TTS_CACHE_DIR / f"{key}.wav"
    if cached.exists():
        return cached.read_bytes()

    body = {
        "text": text,
        "model": config.TTS_MODEL,
        "voice": config.TTS_VOICE,
        "language": config.TTS_LANGUAGE,
        "speed": config.TTS_SPEED,
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    try:
        resp = requests.post(
            config.TTS_URL,
            headers={**_headers(), "Content-Type": "application/json"},
            json=body,
            timeout=45,
        )
    except requests.RequestException as e:
        raise GnaniError(f"tts_network_error: {e}") from e
    if resp.status_code != 200:
        raise GnaniError(f"tts_failed: {_error_text(resp)}", status=resp.status_code)
    audio = resp.content
    cached.write_bytes(audio)
    return audio
