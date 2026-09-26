# 🎙️ Interview Buddy

A **local, free, speaking** interview-prep webapp. It asks you questions
**out loud**, listens to your spoken answers, and coaches you — everything
runs on your Mac (Ollama qwen3:14b + faster-whisper + browser speech), so
practice costs ₹0 and works offline.

Built for Rishav's AI-engineer transition (Sep 2026) — the question banks
mirror his `fin-research-agent` interview syllabus, so every practice
session doubles as project-revision.

## What it does

| Mode | What Buddy does |
|---|---|
| **Interview — AI Engineer** | 19 technical questions (RAG, evals, agents, cost, LoRA…), pushes for metrics, one follow-up when your answer is vague |
| **Behavioral (STAR)** | 12 behavioral questions, coaches you toward Situation-Task-Action-Result |
| **Daily English chat** | Free-flowing conversation for daily spoken-English practice |

Every reply is **spoken** (browser TTS). Live filler-word counter
(um/uh/basically/like…). Click **End & feedback** for a coach report:
score /10, strengths, improvements, best & weakest answer, one concrete
next focus. Transcripts save to `transcripts/`.

## Run it

Prereqs (already true on this machine): Ollama app running with
`qwen3:14b` pulled, Python 3.11+.

```bash
cd ~/Documents/interview-buddy
source .venv/bin/activate        # if you already created it, else:
# python3 -m venv .venv && source .venv/bin/activate
# pip install -r requirements.txt

python server.py
open http://localhost:8001
```

First click of **Start session** warms the models (~10 s the very first
time; whisper stays loaded after). Allow the **microphone** when Chrome
asks. Then: mic → answer out loud → mic again → Buddy speaks back.

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

The **server** decides which question is active and when to move on; the
LLM only polishes language, gives quick feedback, and may ask ONE
follow-up. Deterministic control, natural conversation.

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
- **First answer slow (~15 s)** → whisper model + Ollama warm-up; later
  turns are fast. qwen thinking is disabled via `/no_think`.
- **Connection refused** → `python server.py` not running, or Ollama app
  closed. Check `/api/health`.
- Want a different voice/model → see `.env.example` (gemma4:26b works too).
