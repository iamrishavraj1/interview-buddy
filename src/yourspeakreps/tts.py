"""Server-side TTS — cross-platform, 100% local (no cloud, no API keys).

Engines by OS (auto-detected):
- macOS   -> built-in `say` (best quality: Aman/Tara/Samantha + Premium voices)
- Windows -> built-in SAPI voices via PowerShell System.Speech
            (Zira/David/Heera Desktop — shipped with Windows)
- Linux   -> espeak-ng (`sudo apt install espeak-ng`; pip fallbacks later)

Flow stays identical on every OS: synth(text, voice) -> WAV in tts_cache/
-> served at /tts/<name> -> frontend plays it with `new Audio(url)`. If the
engine fails for any reason we return None and the frontend falls back to
browser speechSynthesis.

macOS gotcha kept from the first build: `say -v '?'` returns LONG names
("Aman (English (India))") with a SINGLE space before the locale when called
from a subprocess — parse with `\\s+`, not column widths. Long and short
names both work for synthesis; we try long first, short as fallback.
"""
import base64
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from yourspeakreps.config import PROJECT_ROOT, TTS_VOICE

CACHE = PROJECT_ROOT / "tts_cache"
CACHE.mkdir(exist_ok=True)

if sys.platform == "darwin":
    PLATFORM = "darwin"
elif sys.platform.startswith("win"):
    PLATFORM = "win32"
else:
    PLATFORM = "linux"

# ---------------------------------------------------------------- macOS ----
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


def _macos_voice_pairs() -> list[tuple[str, str]]:
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


def _macos_english_voices() -> list[dict]:
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

    pairs = sorted((p for p in _macos_voice_pairs() if rank(p)[0] < 9), key=rank)
    return [{"name": n,
             "label": _LOCALE_LABEL.get(loc, loc.replace("en_", "")),
             "base": _base(n)}
            for n, loc in pairs]


def _say(voice: str, out_path: Path, text: str) -> bool:
    try:
        subprocess.run(
            ["say", "-v", voice, "--data-format=LEI16@22050",
             "-o", str(out_path), text],
            timeout=30, check=True, capture_output=True)
        return True
    except Exception:
        return False


# -------------------------------------------------------------- Windows ----
def _ps_encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _sapi_voices() -> list[tuple[str, str]]:
    """Installed SAPI voices as (name, culture) — e.g. ('Microsoft Heera
    Desktop', 'en-IN'). No quoting issues: the script goes over as an
    -EncodedCommand (base64 UTF-16LE)."""
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.GetInstalledVoices() | ForEach-Object { "
        "\"$($_.VoiceInfo.Name)|$($_.VoiceInfo.Culture.Name)\" }\n"
        "$s.Dispose()"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", _ps_encode(script)],
            capture_output=True, text=True, timeout=25, check=True).stdout
    except Exception:
        return []
    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        if "|" in line:
            name, culture = line.rsplit("|", 1)
            pairs.append((name.strip(), culture.strip()))
    return pairs


def _sapi_synth(voice: str | None, out_path: Path, text: str) -> bool:
    text = (text or "").replace('"@', '"@ ')[:2000]  # here-string guard
    voice_line = f"$s.SelectVoice('{voice}')\n" if voice else ""
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        f"$s.SetOutputToWaveFile('{out_path.as_posix()}')\n"
        + voice_line +
        "$s.Rate = 0\n"
        "$s.Speak(@\"\n" + text + "\n\"@)\n"
        "$s.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", _ps_encode(script)],
            timeout=60, check=True, capture_output=True)
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception:
        return False


# ---------------------------------------------------------------- Linux ----
def _espeak_synth(voice: str | None, out_path: Path, text: str) -> bool:
    # espeak-ng voice ids look like "en-us"; accept any "en*" the user sets
    v = (voice or "en-us") if (voice or "").startswith("en") else "en-us"
    try:
        subprocess.run(["espeak-ng", "-v", v, "-w", str(out_path), text],
                       timeout=60, check=True, capture_output=True)
        return True
    except Exception:
        return False


# --------------------------------------------------------------- public ----
def english_voices() -> list[dict]:
    """Picker-friendly list, same shape on every OS:
    [{name, label, base}] — `name` is what synth() accepts."""
    if PLATFORM == "darwin":
        return _macos_english_voices()
    if PLATFORM == "win32":
        return [{"name": n,
                 "label": c.replace("en-", "").upper() or "WIN",
                 "base": n}
                for n, c in _sapi_voices() if c.lower().startswith("en")]
    return [{"name": "en-us", "label": "espeak-ng", "base": "en-us"}]


def pick_voice() -> str | None:
    """Auto = platform default (Indian voice on macOS, en-IN SAPI on
    Windows, espeak-ng on Linux). Explicit TTS_VOICE env wins as-is."""
    if TTS_VOICE != "auto":
        return TTS_VOICE
    if PLATFORM == "linux":
        return "en-us"
    vs = english_voices()
    return vs[0]["name"] if vs else None


def synth(text: str, voice: str | None = None) -> str | None:
    """text -> URL of a WAV file (or None on any failure -> browser TTS)."""
    v = (voice or "").strip()[:80] or pick_voice()
    if not v:
        return None
    _cleanup()
    out = CACHE / f"{uuid.uuid4().hex}.wav"

    if PLATFORM == "darwin":
        ok = _say(v, out, text)
        if not ok:
            base = _base(v)
            ok = base != v and _say(base, out, text)
    elif PLATFORM == "win32":
        ok = _sapi_synth(v, out, text)
    else:
        ok = _espeak_synth(v, out, text)

    if ok:
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
