# 01 — Concepts: how Interview Buddy works

Every concept in the app, in pipeline order. Each section ends with the
interview-angle — what this teaches you that also shows up in AI-engineer
interviews.

```
mic → [MediaRecorder] → webm/opus → [faster-whisper STT] → text
     → [session state] → [Ollama LLM + prompts] → JSON reply
     → [chat UI] → [speechSynthesis TTS] → sound out loud
```

## 2. Capturing audio in the browser (MediaRecorder)

`navigator.mediaDevices.getUserMedia({audio:true})` asks macOS for mic
access (the permission prompt you clicked) and returns a MediaStream.
`MediaRecorder` wraps that stream: `.start()`, then chunks arrive in
`ondataavailable`; `.stop()` fires `onstop`, where we join chunks into one
Blob. Default format is **webm/opus** — a tiny, compressed speech codec.

Server-side, we never parse audio ourselves: **PyAV** (bundled with
faster-whisper, no ffmpeg install needed) decodes any container — webm,
wav, aiff, mp3 — into the PCM whisper wants.

*Interview angle:* "I've built the capture→transcode→inference path and
know where latency lives" is systems maturity most AI candidates lack.

## 3. Speech-to-text: Whisper, faster-whisper, int8

**Whisper** (OpenAI) is an encoder-decoder transformer trained on 680k
hours: the encoder turns 30-second log-mel spectrogram windows into
representations, the decoder emits text tokens autoregressively. It's
weakly supervised on massive noisy data → robust to accents, mics, noise.

**faster-whisper** re-implements it on **CTranslate2**, an inference engine
with **int8 quantization**: weights stored as 8-bit integers instead of
32-bit floats → ~4× less memory, several× faster, tiny accuracy loss for
speech. On this Mac (M5 Pro, CPU-only — CT has no Metal support): *25 s of
audio transcribed in 0.5 s = 52× real-time with `base`*.

Knobs we set and why:
- `compute_type="int8"`, `cpu_threads=8` — CPU inference tuning.
- `beam_size=1` (greedy) — beam 5 buys ~1% accuracy for 4× time; pointless
  for interactive use.
- `language="en"` — skips language detection and stops Hindi/Urdu drift.
- `vad_filter=True` — voice-activity detection trims silence; silences are
  where whisper hallucinates ghost words.
- `initial_prompt="RAG, recall, LoRA, …"` — the decoder conditions on this
  text, biasing it toward our vocabulary. "RAG" survives; "rag" (blanket)
  does not. This is **prompting applied to an encoder-decoder**, same
  principle as giving an LLM domain context.
- **Lazy singleton** — the model (145 MB) loads once on first use, shared
  across requests; a lock guards concurrent first-loads.

*Interview angle:* explain quantization (int8 vs fp32) and the
real-time-factor benchmark you ran yourself.

## 4. Serving an LLM locally: Ollama's OpenAI-compatible API

Ollama runs GGUF-quantized models and exposes `http://localhost:11434/v1`
— the **same chat-completions API shape as OpenAI**. So `llm.py` uses the
standard `openai` SDK with a different `base_url` (and a dummy key):
provider becomes configuration, not code. Swap one env var → the same app
runs against gpt-4o-mini, or later against your own fine-tuned model in
vLLM. This exact abstraction is why phase 5 of fin-research-agent is cheap.

**qwen3 specifics:** it's a *thinking* model — it may spend output tokens
in `<think>…</think>` before the visible answer. We handle it twice:
`/no_think` appended to the system prompt (a trained soft switch) keeps
replies snappy, and a regex strips any think-block that still appears.
Cost tracking would count those tokens — latency you pay for nothing.

## 5. Prompt design: the parts that make it feel like an interviewer

Four techniques, all in `prompts.py`:

1. **Persona + constraints.** Role ("warm but rigorous interviewer"),
   candidate context (SDE-2 → AI engineer), and *spoken-style rules*: no
   markdown, no lists, ≤90 words — because the text becomes **speech**.
   Prompting for the output medium, not just the content.
2. **A strict JSON contract** in the prompt: `{"spoken", "quick_feedback",
   "followed_up"}` — the structured reply is what lets code act on it.
3. **The control-note pattern (the key idea).** The LLM is stateless and
   would happily skip questions or ramble. So the *server* owns the
   question bank and appends a note to the final user message:
   "current question = X, next = Y; follow up once if the answer lacks
   specifics, else move on (followed_up true/false)." Deterministic
   progression (code), natural language (model). The model proposes, the
   server decides.
4. **Robust parsing, never trust.** `extract_json()` slices the first `{`
   to the last `}` (models add preambles/fences) and callers fall back to
   treating raw text as spoken if parsing fails — a broken JSON never
   crashes a session.

*Interview angle:* "server-driven control flow with LLM-generated content"
is exactly how production agent systems stay debuggable.

## 6. Session state: memory is replay, not magic

The model remembers nothing. "Memory" = we keep `history` (role/content
pairs) in a Python object and replay the last N turns into every request
(`MAX_HISTORY_TURNS=10` — context trimming keeps requests fast and focused;
there's a real cost/quality trade-off in choosing N).

The **question bank** lives in `questions.py` (in code — versioned,
inspectable) and the server tracks `q_index`. Filler words ("um", "like",
"basically"…) are counted **locally with regexes** — cheap, explainable,
deterministic — while the LLM judges *quality*. Right tool for each job.
Known limitation: "like"/"right" overcount legitimate uses; documented and
interpreted by the feedback stage.

Sessions live in an in-memory dict — honest for a single-user local app.
Making them durable (SQLite) is exercise 1 in the build guide.

## 7. Speaking replies: browser TTS

`speechSynthesis` is built into every browser: create an
`SpeechSynthesisUtterance`, pick an English voice from `getVoices()`
(loaded async — we warm the list at startup), set `rate`, `speak()`.
We `cancel()` before each new reply so the buddy never talks over you, and
before recording starts so it never talks into its own transcript.

Zero backend cost, zero latency, works offline — vs cloud TTS (better
voices, ₹ per character). v1 picks the free one; switching is one function.

## 8. FastAPI shape (and why sync, not async)

`server.py` endpoints are plain `def` — FastAPI runs sync handlers in a
**threadpool**, which is the right call here: whisper + Ollama calls block
for seconds, single user, no need for async complexity. The moment you have
many concurrent streaming clients (fin-research-agent phase 4), that's
when `async def` + `asyncpg` + streaming earns its complexity.

Other pieces: `UploadFile` + `python-multipart` for the audio POST; a
tempfile round-trip (decode path needs a real file); `StaticFiles(html=True)`
mounted at `/` serves the frontend from the same process — one `python
server.py` runs everything on port 8001.

## 9. Honest limits + what you'd build next

In-memory sessions die on restart · STT is English-only here · replies
aren't streamed (whole sentence arrives, then is spoken) · no wake-word /
auto-stop on silence (click-to-send) · filler regexes are crude.

Natural next steps — each is a good self-exercise: SQLite sessions,
partial/streaming transcription (chunk while talking), words-per-minute +
answer-length metrics, a pause-detector that auto-sends, Hindi/Hinglish
mode (`language=None` in whisper), swapping in gemma4:26b via env var, and
running the whole thing against a cloud LLM to compare quality.
