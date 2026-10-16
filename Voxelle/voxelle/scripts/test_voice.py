"""Day 1 check: does Prisma understand your family, and does Timbre sound warm enough?

Usage:
  python scripts/test_voice.py stt recording.wav            # speech -> text
  python scripts/test_voice.py stt recording.wav --lang en-IN
  python scripts/test_voice.py tts "Papa, subah ki dawai ka time ho gaya hai"
  python scripts/test_voice.py voices "Papa, BP ki goli lijiye"   # same line in several voices
  python scripts/test_voice.py batch recordings/                  # every audio file in a folder

Needs GNANI_API_KEY in .env. Recordings: WAV/MP3/OGG/FLAC/AAC/M4A, up to 60 seconds.
Try your parents' real voices: slow, soft, with medicine names. That is the biggest risk.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, gnani  # noqa: E402

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
OUT = Path(__file__).resolve().parent.parent / "data" / "voice_tests"
TRY_VOICES = ["Poorvi", "Nalini", "Kaveri", "Deepak"]


def stt(path: Path, lang: str | None) -> None:
    text = gnani.transcribe(path.read_bytes(), path.name, lang)
    print(f"{path.name}: {text!r}")


def tts(text: str, voice: str | None = None) -> Path:
    if voice:
        config.TTS_VOICE = voice
    audio = gnani.synthesize(text)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"tts_{config.TTS_VOICE}.wav"
    out.write_bytes(audio)
    print(f"saved {out}  ({len(audio) // 1024} KB, voice={config.TTS_VOICE}, model={config.TTS_MODEL})")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["stt", "tts", "voices", "batch"])
    p.add_argument("target")
    p.add_argument("--lang", default=None)
    a = p.parse_args()

    if not config.GNANI_API_KEY:
        sys.exit("Set GNANI_API_KEY in .env first (copy .env.example to .env).")

    try:
        if a.mode == "stt":
            stt(Path(a.target), a.lang)
        elif a.mode == "tts":
            tts(a.target)
        elif a.mode == "voices":
            for v in TRY_VOICES:
                try:
                    tts(a.target, v)
                except gnani.GnaniError as e:
                    print(f"{v}: {e}")
        else:
            files = sorted(f for f in Path(a.target).iterdir() if f.suffix.lower() in AUDIO_EXT)
            if not files:
                sys.exit(f"No audio files in {a.target}")
            for f in files:
                try:
                    stt(f, a.lang)
                except gnani.GnaniError as e:
                    print(f"{f.name}: ERROR {e}")
    except gnani.GnaniError as e:
        sys.exit(f"Gnani error: {e}")


if __name__ == "__main__":
    main()
