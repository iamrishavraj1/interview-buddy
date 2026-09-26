"""Server-side TTS via macOS `say` — replaces the browser's robotic voice.

Why: Chrome's default speechSynthesis voice sounds flat. macOS ships much
better voices (Samantha, Aman, Daniel) and you can download Premium ones
(System Settings -> Accessibility -> Spoken Content -> System Voice ->
Manage Voices — "Ava (Premium)", "Zoe (Premium)" sound genuinely human).
Still 100% local and free; synthesis takes ~0.2 s for a sentence.

Flow: synth(text) -> WAV file in tts_cache/ -> served at /tts/<name> ->
frontend plays it with `new Audio(url)`. If say fails for any reason we
return None and the frontend falls back to speechSynthesis.
"""
import re
import subprocess
import time
import uuid
from pathlib import Path

from config import TTS_VOICE

CACHE = Path(__file__).parent / "tts_cache"
CACHE.mkdir(exist_ok=True)

# First installed wins. Premium/enhanced first (if user installs them),
# then the good built-ins. Aman/Tara = Indian English.
PREFERRED = ["Ava (Premium)", "Zoe (Premium)", "Allison (Premium)",
             "Samantha", "Aman", "Tara", "Daniel"]

_VOICE_LINE = re.compile(r"^(.+?)\s{2,}(en_[A-Z]{2})\s{2,}")  # name  lang  # sample


def installed_voices() -> list[str]:
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True,
                             text=True, timeout=5, check=True).stdout
    except Exception:
        return []
    return [m.group(1).strip() for m in
            (_VOICE_LINE.match(line) for line in out.splitlines()) if m]


def pick_voice() -> str | None:
    if TTS_VOICE != "auto":            # explicit env override wins as-is
        return TTS_VOICE
    installed = set(installed_voices())
    return next((v for v in PREFERRED if v in installed), None)


def synth(text: str) -> str | None:
    """text -> URL of a WAV file (or None on any failure)."""
    voice = pick_voice()
    if not voice:
        return None
    _cleanup()
    out = CACHE / f"{uuid.uuid4().hex}.wav"
    try:
        subprocess.run(
            ["say", "-v", voice, "--data-format=LEI16@22050", "-o", str(out), text],
            timeout=30, check=True, capture_output=True)
    except Exception:
        return None
    return f"/tts/{out.name}"


def _cleanup(max_age_s: int = 3600) -> None:
    """Old spoken replies are useless — keep the cache small."""
    now = time.time()
    for f in CACHE.glob("*.wav"):
        try:
            if now - f.stat().st_mtime > max_age_s:
                f.unlink()
        except OSError:
            pass
