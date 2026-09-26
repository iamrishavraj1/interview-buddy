"""Interview Buddy — FastAPI backend.

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
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from llm import chat, extract_json
from prompts import feedback_system, interviewer_system
from questions import DAILY_STARTERS
from session import SESSIONS, Session, get
from stt import transcribe

app = FastAPI(title="Interview Buddy", version="1.0.0")

OPENINGS = {
    "interview": ("Hi! I'm Buddy. We'll go through {n} questions, and you answer "
                  "like you're talking to a real interviewer. Ready? "
                  "First question: {q}"),
    "behavioral": ("Hi! I'm Buddy. Today we practice behavioral answers — "
                   "use the STAR way: situation, task, action, result. "
                   "First question: {q}"),
    "daily": "Hi! Great to hear you. Let's just chat — " + DAILY_STARTERS[0],
}


class StartRequest(BaseModel):
    mode: str  # "interview" | "behavioral" | "daily"


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
            "question_number": 1 if first_q else 0,
            "total_questions": s.total_questions}


@app.post("/api/answer")
def answer(session_id: str = Form(...), audio: UploadFile = File(...)) -> JSONResponse:
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
        return JSONResponse({
            "transcript": "", "reply": "Sorry, I didn't catch that — say it again?",
            "quick_feedback": "", "followed_up": True,
            "question_number": min(s.q_index + 1, s.total_questions),
            "total_questions": s.total_questions, "fillers": s.fillers,
        })

    # 2) LLM turn — server keeps control of progression via the control note.
    next_q = "the question bank is finished — wrap up warmly" if s.exhausted \
        else repr(s.bank[s.q_index] if s.bank else None)
    note = (
        f"[SERVER NOTE — not to be read aloud]\n"
        f"Current question: {s.current_question or '(free conversation — keep it going)'}\n"
        f"Next bank question: {next_q}\n"
        f"Decide: ask ONE follow-up on the same question (followed_up=true) if the "
        f"answer lacks depth, specifics or a result — otherwise move on "
        f"(followed_up=false)."
    )
    raw = chat(interviewer_system(s.mode),
               s.llm_messages(transcript, note), temperature=0.7)
    try:
        data = extract_json(raw)
        spoken = str(data.get("spoken") or raw)[:600]
        quick = str(data.get("quick_feedback") or "")
        followed_up = bool(data.get("followed_up"))
    except (ValueError, TypeError):  # model broke the contract — degrade nicely
        spoken, quick, followed_up = raw[:600], "", False

    s.add_user(transcript)
    s.add_assistant(spoken)
    if not followed_up:
        s.advance()

    return JSONResponse({
        "transcript": transcript, "reply": spoken, "quick_feedback": quick,
        "followed_up": followed_up,
        "question_number": min(s.q_index + 1, s.total_questions) if s.bank else 0,
        "total_questions": s.total_questions,
        "fillers": s.fillers,
        "finished": s.exhausted,
    })


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


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static",
                           html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT)
