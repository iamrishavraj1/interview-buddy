"""Central config — every knob in one place, env-overridable.

Defaults already work on this machine (Ollama local + whisper `base`,
both verified — see docs/01-concepts.md). No .env required to run.
"""
import os
from pathlib import Path

# LLM (Ollama's OpenAI-compatible endpoint)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")

# STT (faster-whisper)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")   # base=52x real-time here
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "8"))

# TTS voice. "auto" = picker default: Indian voices (Aman/Tara) first,
# then Premium if installed, then Samantha/Daniel. UI picker can override
# per session; this env var wins over "auto" entirely.
TTS_VOICE = os.getenv("TTS_VOICE", "auto")

# Conversation
MAX_HISTORY_TURNS = 10     # how many previous user/assistant turns the LLM sees
SPOKEN_WORD_LIMIT = 90     # interviewer replies stay short enough to be spoken
RETRY_LIMIT = 2            # coaching retries per question before Loop
                           # demonstrates the correct version and moves on
PORT = int(os.getenv("PORT", "8001"))

# Project root (repo root) — runtime artifacts (tts_cache/, transcripts/)
# live here, outside the package, and are gitignored.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
