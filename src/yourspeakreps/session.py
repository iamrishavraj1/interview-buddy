"""Session state: conversation memory, question progression, filler stats.

Concepts (docs/01-concepts.md §6):
- The LLM is stateless — "memory" is just us replaying recent turns into
  each request (trimmed to MAX_HISTORY_TURNS so context stays small).
- The SERVER owns question progression (self.q_index), not the model —
  deterministic, inspectable, and impossible for the model to skip ahead.
- Filler words are counted locally with regexes (cheap, explainable);
  the LLM judges quality, code counts the "um"s. Right tool for each job.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from yourspeakreps.questions import AI_ENGINEER, BEHAVIORAL, DAILY_STARTERS
from yourspeakreps.config import MAX_HISTORY_TURNS, PROJECT_ROOT

BANKS = {"interview": AI_ENGINEER, "behavioral": BEHAVIORAL}

# Single words (um, uhh...) counted with word boundaries; phrases counted
# as substrings. "like"/"right" overcount legitimate uses — that is a known,
# documented limitation; the feedback LLM interprets totals accordingly.
_WORD_FILLERS = re.compile(r"\b(um+|uh+|hmm+|erm+|er+)\b", re.IGNORECASE)
_PHRASE_FILLERS = ["basically", "actually", "literally", "you know",
                   "kind of", "sort of", "like", "right"]

TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"


class Session:
    def __init__(self, mode: str):
        self.id: str = ""
        self.mode = mode
        self.bank = BANKS.get(mode)
        self.q_index = 0                 # which bank question is "active"
        self.current_question: str | None = None
        self.attempts = 0                # tries on the CURRENT question
        self.retry_count = 0             # coaching retries in the session
        self.pairs: list[dict] = []      # {"question": ..., "answer": ...}
        self.history: list[dict] = []    # {"role": ..., "content": ...}
        self.fillers: dict[str, int] = {}
        self.started = time.time()

    # ---- question bookkeeping ------------------------------------------
    @property
    def total_questions(self) -> int:
        return len(self.bank) if self.bank else 0

    @property
    def exhausted(self) -> bool:
        return self.bank is not None and self.q_index >= len(self.bank)

    def activate_next_question(self) -> str | None:
        self.attempts = 0
        if self.bank is None:  # daily mode has no bank
            return None
        self.current_question = None if self.exhausted else self.bank[self.q_index]
        return self.current_question

    def advance(self) -> None:
        """Move to the next bank question (called when the LLM didn't
        follow up or retry). Daily mode never advances."""
        if self.bank is not None:
            self.q_index += 1
            self.attempts = 0

    # ---- conversation bookkeeping ---------------------------------------
    def add_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        self.pairs.append({"question": self.current_question, "answer": text})
        self.attempts += 1
        low = text.lower()
        for m in _WORD_FILLERS.findall(low):
            self.fillers[m] = self.fillers.get(m, 0) + 1
        for p in _PHRASE_FILLERS:
            n = low.count(p)
            if n:
                self.fillers[p] = self.fillers.get(p, 0) + n

    def add_assistant(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def llm_messages(self, latest_transcript: str, note: str) -> list[dict]:
        """Build the request: older turns (trimmed) + a final user message
        holding the latest answer plus the server's control note.
        (add_user runs AFTER this call, so full history = genuinely older.)"""
        older = self.history[-2 * MAX_HISTORY_TURNS:]
        combined = f"Candidate just said: \"{latest_transcript}\"\n\n{note}"
        return [*older, {"role": "user", "content": combined}]

    # ---- reporting -------------------------------------------------------
    def digest(self) -> str:
        """Q/A transcript for the feedback call (and saved files)."""
        lines = []
        for i, p in enumerate(self.pairs, 1):
            q = p["question"] or "(free conversation)"
            lines.append(f"[{i}] Q: {q}\n    A: {p['answer']}")
        return "\n".join(lines) or "(no answers given)"

    def stats(self) -> dict:
        return {
            "mode": self.mode,
            "turns": len(self.pairs),
            "questions_asked": min(self.q_index + (0 if self.exhausted else 1),
                                   self.total_questions) if self.bank else 0,
            "total_questions": self.total_questions,
            "coaching_retries": self.retry_count,
            "fillers": dict(sorted(self.fillers.items(),
                                   key=lambda kv: -kv[1])),
            "duration_min": round((time.time() - self.started) / 60, 1),
        }

    def save(self, report: dict) -> Path:
        """Write transcript + report to transcripts/<ts>-<mode>.md and .json."""
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = TRANSCRIPTS_DIR / f"{stamp}-{self.mode}"
        s = self.stats()
        (base.with_suffix(".md")).write_text(
            f"# YourSpeakReps session — {stamp} ({self.mode})\n\n"
            f"Score: {report.get('overall_score', '?')}/10\n\n"
            f"## Stats\n```json\n{json.dumps(s, indent=2)}\n```\n\n"
            f"## Transcript\n{self.digest()}\n\n"
            f"## Coach report\n```json\n{json.dumps(report, indent=2)}\n```\n",
            encoding="utf-8")
        base.with_suffix(".json").write_text(
            json.dumps({"stats": s, "pairs": self.pairs, "report": report},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        return base.with_suffix(".md")


# Single-user local app: in-memory dict is honest and enough (docs/01 §6).
SESSIONS: dict[str, Session] = {}


def get(session_id: str) -> Session | None:
    return SESSIONS.get(session_id)
