# Contributing to YourSpeakReps

First — thank you. This project grows by people who want to **speak better**
and like the idea of a 100%-local, ₹0/free coach.

## Setup (2 minutes)

```bash
git clone https://github.com/iamrishavraj1/yourspeakreps.git
cd yourspeakreps
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m yourspeakreps.server     # http://localhost:8001
pytest                             # smoke tests should pass
```

Requirements: [Ollama](https://ollama.com) with `qwen3:14b`, Python 3.11+,
Chrome. Linux needs `espeak-ng` (`sudo apt install espeak-ng`).

## Project map

```
src/yourspeakreps/
├── config.py      # every knob, env-overridable
├── server.py      # FastAPI: /api/start, /api/answer, /api/feedback, /tts
├── session.py     # per-session state, question progression, filler analytics
├── questions.py   # the question banks ← most contributions land here
├── prompts.py     # interviewer persona + spoken-style constraints
├── stt.py         # faster-whisper wrapper (lazy singleton)
├── llm.py         # Ollama client (native API, think:false)
└── tts.py         # cross-platform TTS: macOS say / Windows SAPI / Linux espeak-ng
static/            # frontend (index.html, app.js)
```

## Good first contributions

### 1. Add a question bank or mode (easiest, highest impact)
`questions.py` is plain Python lists — no framework knowledge needed.
- Add questions to an existing bank (keep them spoken-style: short, natural,
  one idea per question).
- Or add a whole new mode: a bank + one entry in the mode map in
  `server.py` + one `<option>` in `static/index.html`.

### 2. Add a spoken language
English is the default today. A new language needs three touchpoints:
1. A question bank in that language (`questions.py`)
2. `initial_prompt` in `stt.py` biased to that language's vocabulary
3. Voice guidance in `README.md` (which TTS voices sound good)

Hindi/Hinglish is the top ask — `faster-whisper` already handles it, the work
is in the bank + prompts.

### 3. Improve a TTS engine
`tts.py` exposes one interface (`synth(text, voice) -> wav url`).
- Linux: wire up **piper** for better-than-espeak quality
- Windows: test more SAPI voices, add rate/pitch knobs
- Any OS: add edge-case handling you hit

### 4. Platform testing
We can't test every OS/voice combo — if something breaks on your setup,
an issue with your OS version + the console error is a valuable PR.

## Ground rules

- **The server controls the session** (control-note pattern) — the LLM only
  polishes language and gives feedback. Don't move session logic into prompts.
- **Sync handlers, lazy models** — FastAPI runs handlers in a threadpool;
  heavy models load lazily behind a lock (`stt.py` shows the pattern).
- **No cloud calls, ever.** Everything must run offline.
- `pytest` green before you open a PR.

## PR flow

1. Fork → branch (`feat/your-thing`)
2. Small, focused PRs — one feature per PR
3. Describe what you changed and how you tested it (which OS, which voice)
4. Open the PR against `main`
