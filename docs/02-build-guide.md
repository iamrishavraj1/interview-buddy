# 02 — Build it yourself (7 steps)

You already have the finished app as reference — this guide is the path to
rebuild it from an empty folder so every line is *yours*. Read
`docs/01-concepts.md` §-references along the way. Each step has an
acceptance check: don't move on until it passes.

**Setup:** empty folder `~/Documents/buddy-own/`, `python3 -m venv .venv`,
`pip install faster-whisper fastapi uvicorn[standard] python-multipart openai`,
Ollama running, and copy `questions.py` from this repo (content, not skill).

---

## Step 1 — Talk to whisper (stt.py)

Goal: a script `python stt.py file.aiff` that prints a transcript.

- Make test audio without a mic: `say -o test.aiff "Tell me about RAG."`
- `WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=8)`
  — load it lazily (a module-level `None` + function that creates on first
  call). Measure load time and transcription time; print both.
- Add `language="en"`, `beam_size=1`, `initial_prompt` with tech terms,
  `vad_filter=True` — then try removing each and diff the output on the
  same file. (§3)

**Acceptance:** transcript matches; you can say out loud what int8, beam
size, and initial_prompt each do.

## Step 2 — Talk to Ollama (llm.py)

Goal: `python llm.py` sends one message and prints the reply.

- `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")`.
- Ask: `Reply with JSON {"ok": true}` at temperature 0. Then at 0.7.
- Write `extract_json()` (first `{` → last `}`) and prove it survives a
  reply like "Sure! Here you go: ```json {...}```".
- Ask qwen3 something longer and look for `<think>` — then add the strip
  regex, then try `/no_think` in the system message and compare latency. (§4)

**Acceptance:** JSON extraction never raises on 5 different phrasings; you
can explain why we don't use `eval`-style parsing anywhere.

## Step 3 — State machine (session.py)

Goal: a `Session` class that tracks a bank of questions without any LLM.

- `pairs`, `history`, `q_index`, `current_question`, `advance()`.
- Filler counting: regexes with word boundaries + phrase substrings; unit
  test with a string like "Um basically, like, we did the thing, right?"
- `llm_messages()`: older turns trimmed to last 10 + final combined message.

**Acceptance:** a 15-line test script drives two fake turns and prints the
right "current question" after a followed-up=false reply. (§6)

## Step 4 — API (server.py)

Goal: three endpoints, curl-testable, no frontend yet.

- `POST /api/start` → create Session, return opening line + first question.
- `POST /api/answer` → accept `UploadFile` + form field; save to a tempfile
  (suffix from filename!), transcribe, build the control note, call the
  LLM, parse, update session, return JSON. Handle: unknown session (404),
  empty transcript (friendly re-ask, don't burn an LLM call), broken JSON
  (fallback to raw text). (§5, §8)
- `POST /api/feedback` → digest + stats into the coach prompt, save
  `transcripts/<ts>-<mode>.md`.

**Acceptance:** drive a whole session with curl — `say` a fresh answer
file, POST it — and get sensible JSON every step. This is exactly how I
tested the built version before any browser existed.

## Step 5 — Speak it (static/, first version)

Goal: a page that records, sends, shows, speaks.

- One `index.html` + one `app.js`. `getUserMedia` → `MediaRecorder`;
  start/stop on the same button; onstop → Blob → FormData → `/api/answer`.
- Render bubbles; `speechSynthesis` for buddy replies (cancel first!).
- Show errors in-page: mic permission denied, fetch failed. (§2, §7)

**Acceptance:** you can hold a 3-turn conversation without touching the
keyboard, and killing the server mid-way shows a readable error, not a
silent hang.

## Step 6 — Control + polish

- Server-side progression: the control-note pattern, `followed_up` flag,
  "bank finished → wrap up" state. Watch your LLM try to skip questions
  before you add it — then confirm it can't after.
- Live filler counter, question x/y in the sidebar, voice on/off toggle,
  End & feedback button rendering the report.

**Acceptance:** a full mock interview end-to-end + saved transcript file.

## Step 7 — Make it yours (pick 2)

- SQLite sessions (survive restarts).
- Auto-send on 2 s of silence (AnalyserNode RMS threshold).
- Words-per-minute + answer-length metrics per question.
- Hindi/Hinglish mode (`language=None` in whisper, prompt tweak).
- Swap the LLM via env: gpt-4o-mini vs qwen3 vs gemma4 — write down the
  difference in coaching quality. (That comparison habit is the whole
  fin-research-agent methodology in miniature.)
