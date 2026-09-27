"""Server-side TTS via macOS `say` — replaces the browser's robotic voice.

Why: Chrome's default speechSynthesis voice sounds flat. macOS ships much
better voices (Aman/Tara = Indian English, Samantha, Daniel) and you can
download Premium ones (System Settings -> Accessibility -> Spoken Content
-> System Voice -> Manage Voices). Still 100% local and free; synthesis
takes ~0.2 s for a sentence.

Gotcha learned here: `say -v '?'` returns LONG names ("Aman (English
(India))") with a SINGLE space before the locale when called from a
subprocess — parse with `\s+`, not column widths. Both the long and the
short name ("Aman") work for synthesis; we try long first, short as
fallback (see synth()).

Flow: synth(text, voice) -> WAV file in tts_cache/ -> served at
/tts/<name> -> frontend plays it with `new Audio(url)`. If say fails for
any reason we return None and the frontend falls back to speechSynthesis.
"""
import re
import subprocess
import time
import uuid
from pathlib import Path

from config import TTS_VOICE

CACHE = Path(__file__).parent / "tts_cache"
CACHE.mkdir(exist_ok=True)

# Novelty/robotic voices that would make the picker silly.
NOVELTY = {"Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos",
           "Wobble", "Good News", "Jester", "Organ", "Ralph", "Superstar",
           "Trinoids", "Whisper", "Zarvox", "Junior", "Rocko", "Shelley",
           "Sandy", "Grandma", "Grandpa", "Fred", "Albert", "Eddy", "Flo",
           "Grandma (English (UK))", "Grandma (English (US))",
           "Grandpa (English (UK))", "Grandpa (English (US))"}

_LOCALE_LABEL = {"en_IN": "Indian", "en_US": "US", "en_GB": "UK",
                 "en_AU": "AU", "en_IE": "IE", "en_ZA": "SA", "en_IN_": "Indian"}

# name (short or long form)  locale   # sample text
_VOICE_LINE = re.compile(r"^(.+?)\s+(en_[A-Z]{2}(?:_[A-Z]+)?)\s+#")


def _base(name: str) -> str:
    """'Aman (English (India))' -> 'Aman' (display name)."""
    return re.sub(r"\s*\(English.*?\)\s*$", "", name).strip()


def _voice_pairs() -> list[tuple[str, str]]:
    """(listed_name, locale) for every installed voice, deduped."""
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True,
                             text=True, timeout=5, check=True).stdout
    except Exception:
        return []
    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        m = _VOICE_LINE.match(line)
        if m and (m.group(1).strip(), m.group(2)) not in pairs:
            pairs.append((m.group(1).strip(), m.group(2)))
    return pairs


def english_voices() -> list[dict]:
    """Picker-friendly list: Indian voices first, then Premium, rest after.
    `name` is what you pass to `say -v`; `label` is for display."""
    def rank(item):
        name, locale = item
        base = _base(name)
        if base in NOVELTY:
            return (9, name)
        if locale.startswith("en_IN"):
            return (0, name)
        if "Premium" in name or "Enhanced" in name:
            return (1, name)
        return (2, name)

    pairs = sorted((p for p in _voice_pairs() if rank(p)[0] < 9), key=rank)
    return [{"name": n,
             "label": _LOCALE_LABEL.get(loc, loc.replace("en_", "")),
             "base": _base(n)}
            for n, loc in pairs]


def pick_voice() -> str | None:
    """Auto = first of english_voices() -> Indian voice if installed."""
    if TTS_VOICE != "auto":            # explicit env override wins as-is
        return TTS_VOICE
    vs = english_voices()
    return vs[0]["name"] if vs else None


def _say(voice: str, out_path: Path, text: str) -> bool:
    try:
        subprocess.run(
            ["say", "-v", voice, "--data-format=LEI16@22050",
             "-o", str(out_path), text],
            timeout=30, check=True, capture_output=True)
        return True
    except Exception:
        return False


def synth(text: str, voice: str | None = None) -> str | None:
    """text -> URL of a WAV file (or None on any failure).

    `voice` is the user's picker choice (a full listed name); falls back
    to pick_voice(). If the full name fails to synthesize, retries once
    with its short base name, then gives up (browser TTS takes over).
    """
    v = (voice or "").strip()[:64] or pick_voice()
    if not v:
        return None
    _cleanup()
    out = CACHE / f"{uuid.uuid4().hex}.wav"
    if _say(v, out, text):
        return f"/tts/{out.name}"
    base = _base(v)
    if base != v and _say(base, out, text):
        return f"/tts/{out.name}"
    out.unlink(missing_ok=True)
    return None


def _cleanup(max_age_s: int = 3600) -> None:
    """Old spoken replies are useless — keep the cache small."""
    now = time.time()
    for f in CACHE.glob("*.wav"):
        try:
            if now - f.stat().st_mtime > max_age_s:
                f.unlink()
        except OSError:
            pass
