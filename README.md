# 🎙️ SpeakLoop

![License](https://img.shields.io/badge/License-All%20Rights%20Reserved-red?style=flat-square) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white) ![Runs%20offline](https://img.shields.io/badge/Runs-100%25%20offline-teal?style=flat-square)

A **local, free, speaking** mock-interview coach. It asks questions **out loud**,
listens to your spoken answers, and coaches you — everything runs on your Mac
(Ollama + faster-whisper + macOS voices), so practice costs ₹0 and works offline.

## What it does

| Mode | What Loop does |
|---|---|
| **Interview — AI Engineer** | 19 technical questions (RAG, evals, agents, cost, LoRA…), pushes for metrics, one follow-up when your answer is vague |
| **Behavioral (STAR)** | 12 behavioral questions, coaches you toward Situation-Task-Action-Result |
| **Daily English chat** | Free-flowing conversation for daily spoken-English practice |

Every reply is **spoken in a natural macOS voice** (server-side `say` → WAV, with
the browser voice as fallback; Premium voices supported). Live **filler-word
counter** (um/uh/basically/like…). Click **End & feedback** for a coach report:
score /10, strengths, improvements, best & weakest answer, one concrete next
focus. Transcripts save to `transcripts/`.

**Switching modes is instant** — change the dropdown and a fresh session starts
in that mode right away (the old one is dropped). No page refresh, ever.

## How to run

Prerequisites: [Ollama](https://ollama.com) with `qwen3:14b` pulled,
Python 3.11+, Chrome (for microphone access).

```bash
git clone https://github.com/iamrishavraj1/speakloop.git
cd speakloop
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
open http://localhost:8001
```

First click of **Start session** warms the models (~10 s the very first time;
whisper stays loaded after). Allow the **microphone** when Chrome asks. Then:
mic → answer out loud → mic again → Loop speaks back.

## Architecture

```
Chrome (localhost:8001)                    FastAPI (server.py)
┌──────────────────────────┐   webm/opus   ┌───────────────────────────┐
│ MediaRecorder (mic) ─────┼──────────────►│ stt.py  faster-whisper    │
│ speechSynthesis ◄────────┼─── text ──────│         (int8, 52x RT)    │
│ chat UI / filler stats   │               │            │              │
└──────────────────────────┘               │            ▼              │
                                           │ llm.py  Ollama /v1        │
                                           │         qwen3:14b         │
                                           │            │              │
                                           │ session.py (history, bank │
                                           │  progression, fillers)    │
                                           └───────────────────────────┘
```

## Design notes

- **Deterministic control, natural conversation** — the server decides which
  question is active and when to move on; the LLM only polishes language, gives
  quick feedback, and may ask ONE follow-up. Sessions stay on rails while
  feeling free-form.
- **Latency** — qwen3's hidden "thinking" tokens are disabled via Ollama's
  native API (`think: false`): 53 s → 1.7 s per reply. Whisper pre-warms at
  startup; steady-state turns take ~2–4 s.
- **Structured output** — replies follow a JSON contract (feedback + optional
  follow-up), with double-encoded-JSON unwrapping and empty-reply retries.

## Repo tour

| File | Read it to learn |
|---|---|
| `docs/01-concepts.md` | **Every concept**: STT, quantization, LLM serving, prompt design, session state, MediaRecorder, TTS, FastAPI |
| `docs/02-build-guide.md` | **Build it yourself** — 7 steps with acceptance checks, if you want to rebuild from scratch to learn |
| `server.py` | API surface, control-note pattern, graceful degradation |
| `session.py` | State, question progression, filler analytics, transcript saving |
| `prompts.py` | Interviewer persona, spoken-style constraints, JSON contract |
| `stt.py` / `llm.py` | whisper wrapper / Ollama client with think-stripping |
| `static/app.js` | MediaRecorder, speechSynthesis, UI state machine |

## Troubleshooting

- **Mic blocked** → Chrome settings → Privacy → Microphone → allow
  `localhost:8001`.
- **"I didn't catch that"** every time → speak closer to the mic; check
  the input device in macOS Sound settings.
- **First answer slow (~15 s)** → whisper warms up in the background at
  startup; after that turns take ~2-4 s. qwen's hidden "thinking" tokens
  are disabled via Ollama's `think: false` (53 s → 1.7 s per reply).
- **Connection refused** → `python server.py` not running, or Ollama app
  closed. Check `/api/health`.
- **Different voice** → see `.env.example`:
  - `TTS_VOICE=Aman` or `TTS_VOICE=Tara` for Indian-English accents
  - **Best quality (recommended):** install Premium voices once — System
    Settings → Accessibility → Spoken Content → System Voice → Manage
    Voices → download **Ava (Premium)** / **Zoe (Premium)** — then set
    `TTS_VOICE="Ava (Premium)"`. Genuinely human-sounding, still offline.
  - The app auto-picks the best installed voice when `TTS_VOICE=auto`.

## License

![License](https://img.shields.io/badge/License-All%20Rights%20Reserved-red?style=flat-square)

© 2026 Rishav Raj. Source is public for **learning and evaluation** — copying,
redistributing, or using it in your own projects or client work is **not
permitted** without written permission. See [LICENSE](LICENSE).

Commercial licensing / collaboration → [iamrishavraj1@gmail.com](mailto:iamrishavraj1@gmail.com)

---

*Contact: [iamrishavraj1@gmail.com](mailto:iamrishavraj1@gmail.com) · [iamrishavraj1.com](https://iamrishavraj1.com)*
