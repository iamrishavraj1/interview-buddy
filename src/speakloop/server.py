"""SpeakLoop — FastAPI backend.

Run:  python server.py     →  http://localhost:8001

Endpoints:
  POST /api/start     {mode}                    → session + first question
  POST /api/answer    audio file + session_id   → transcript + spoken reply
  POST /api/feedback  session_id                → coach report (+ saved file)
  GET  /api/health                              → liveness + config
  /   static frontend (served from ./static)

All API endpoints are plain `def` (sync): FastAPI runs them in a threadpool,
which is exactly right for a single user with blocking STT + LLM calls.
(docs/01-concepts.md §8 explains when you'd go async instead.)
"""
import shutil
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from speakloop import config
from speakloop import stt
from speakloop import tts
from speakloop.llm import chat, extract_json
from speakloop.prompts import feedback_system, interviewer_system
from speakloop.questions import DAILY_STARTERS
from speakloop.session import SESSIONS, Session, get
from speakloop.stt import transcribe


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Pre-warm whisper in the background so the FIRST answer isn't slow
    # (model load ~10 s, transcription after that ~0.5 s — docs/01 §3).
    threading.Thread(target=stt.get_model, daemon=True).start()
    yield


app = FastAPI(title="SpeakLoop", version="1.0.0", lifespan=lifespan)

OPENINGS = {
    "interview": ("Hi! I'm Loop. We'll go through {n} questions, and you answer "
                  "like you're talking to a real interviewer. Ready? "
                  "First question: {q}"),
    "behavioral": ("Hi! I'm Loop. Today we practice behavioral answers — "
                   "use the STAR way: situation, task, action, result. "
                   "First question: {q}"),
    "daily": "Hi! Great to hear you. Let's just chat — " + DAILY_STARTERS[0],
}


class StartRequest(BaseModel):
    mode: str  # "interview" | "behavioral" | "daily"
    voice: str | None = None  # picker choice; None = auto (Indian first)


@app.get("/api/voices")
def voices() -> dict:
    """English voices for the UI picker + which one is the default."""
    return {"voices": tts.english_voices(), "default": tts.pick_voice()}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": config.OLLAMA_MODEL,
            "whisper": config.WHISPER_MODEL}


@app.post("/api/start")
def start(body: StartRequest) -> dict:
    if body.mode not in ("interview", "behavioral", "daily"):
        raise HTTPException(400, f"unknown mode: {body.mode}")

    s = Session(body.mode)
    s.id = uuid.uuid4().hex[:12]
    first_q = s.activate_next_question()

    if body.mode == "daily":
        spoken = OPENINGS["daily"]
    else:
        spoken = OPENINGS[body.mode].format(
            n=s.total_questions, q=first_q)
    s.add_assistant(spoken)
    SESSIONS[s.id] = s
    return {"session_id": s.id, "reply": spoken, "quick_feedback": "",
            "audio_url": tts.synth(spoken, body.voice),
            "question_number": 1 if first_q else 0,
            "total_questions": s.total_questions}


@app.post("/api/answer")
def answer(session_id: str = Form(...), audio: UploadFile = File(...),
           voice: str | None = Form(None)) -> JSONResponse:
    s = get(session_id)
    if s is None:
        raise HTTPException(404, "session not found — start a new session")

    # 1) STT — any container the browser recorded (webm/opus) or a test file.
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(audio.file, tmp)
        tmp.close()
        transcript = transcribe(tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    if not transcript:
        missed = "Sorry, I didn't catch that — say it again?"
        return JSONResponse({
            "transcript": "", "reply": missed, "quick_feedback": "",
            "audio_url": tts.synth(missed, voice), "followed_up": True,
            "question_number": min(s.q_index + 1, s.total_questions),
            "total_questions": s.total_questions, "fillers": s.fillers,
        })

    # 2) LLM turn — server keeps control of progression via the control note.
    max_attempts = config.RETRY_LIMIT + 1
    next_q = "the question bank is finished — wrap up warmly" if s.exhausted \
        else repr(s.bank[s.q_index] if s.bank else None)
    if s.attempts >= max_attempts:
        retry_policy = (f"This was attempt {s.attempts} of {max_attempts} — the "
                        f"retry limit is reached: retry MUST be false. Speak the "
                        f"corrected version yourself, briefly praise the effort, "
                        f"then move to the next question.")
    else:
        retry_policy = (
            f"This is attempt {s.attempts} of {max_attempts} for this question. "
            f"If the answer has a correctable language/structure mistake: set "
            f"retry=true, correct ONE thing in 'correction', and ask them to say "
            f"it again. If it is clean (or the retry improved it): retry=false.")
    note = (
        f"[SERVER NOTE — not to be read aloud]\n"
        f"Current question: {s.current_question or '(free conversation — keep it going)'}\n"
        f"Next bank question: {next_q}\n"
        f"{retry_policy}\n"
        f"If your 'spoken' ends with a question about this same answer, "
        f"followed_up MUST be true (unless retry=true)."
    )

    def llm_turn() -> str:
        return chat(interviewer_system(s.mode),
                    s.llm_messages(transcript, note), temperature=0.7)

    def parse(raw: str) -> tuple[str, str, bool, bool, str]:
        try:
            data = extract_json(raw)
            return (str(data.get("spoken") or ""),
                    str(data.get("quick_feedback") or ""),
                    bool(data.get("followed_up")),
                    bool(data.get("retry")),
                    str(data.get("correction") or ""))
        except (ValueError, TypeError):  # model broke the contract — degrade nicely
            return raw[:600], "", False, False, ""

    spoken, quick, followed_up, retry, correction = parse(llm_turn())
    if not spoken.strip():            # rare Ollama hiccup: one retry, then a canned line
        spoken, quick, followed_up, retry, correction = parse(llm_turn())
    if not spoken.strip():
        spoken = "Could you go a bit deeper on that?"
        quick, followed_up, retry, correction = "", True, False, ""

    s.add_user(transcript)
    s.add_assistant(spoken)
    if retry and s.attempts < max_attempts:
        # Learning loop: stay on the same question so they try again.
        s.retry_count += 1
        retry = True
    else:
        retry = False                 # limit reached or answer accepted
        correction = correction if not followed_up else ""
        if not followed_up:
            s.advance()

    return JSONResponse({
        "transcript": transcript, "reply": spoken, "quick_feedback": quick,
        "audio_url": tts.synth(spoken, voice),
        "followed_up": followed_up, "retry": retry,
        "correction": correction, "attempt": s.attempts,
        "max_attempts": max_attempts,
        "question_number": min(s.q_index + 1, s.total_questions) if s.bank else 0,
        "total_questions": s.total_questions,
        "fillers": s.fillers,
        "finished": s.exhausted,
    })


@app.post("/api/abandon")
def abandon(session_id: str = Form(...)) -> dict:
    """Drop a session without a coach report (mode switch / restart)."""
    SESSIONS.pop(session_id, None)
    return {"ok": True}


@app.get("/tts/{name}")
def tts_file(name: str) -> FileResponse:
    """Serve a spoken reply. Name must be hex.wav — no path traversal."""
    if not (len(name) == 32 + 4 and name.endswith(".wav")
            and all(c in "0123456789abcdef" for c in name[:32])):
        raise HTTPException(400, "bad tts name")
    path = config.PROJECT_ROOT / "tts_cache" / name
    if not path.exists():
        raise HTTPException(404, "expired or missing")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/feedback")
def feedback(session_id: str = Form(...)) -> dict:
    s = get(session_id)
    if s is None:
        raise HTTPException(404, "session not found")

    stats = s.stats()
    user_msg = (
        f"Mode: {s.mode}\nSession stats: {stats}\n\nTranscript:\n{s.digest()}"
    )
    raw = chat(feedback_system(), [{"role": "user", "content": user_msg}],
               temperature=0.3)
    try:
        report = extract_json(raw)
    except ValueError:
        report = {"summary": raw[:800]}

    path = s.save(report)
    SESSIONS.pop(session_id, None)
    return {"report": report, "stats": stats,
            "transcript_file": path.name}


app.mount("/", StaticFiles(directory=config.PROJECT_ROOT / "static",
                           html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT)
