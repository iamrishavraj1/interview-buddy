"""Speech-to-text via faster-whisper (local, free, CPU).

Concepts (docs/01-concepts.md §3):
- faster-whisper = Whisper re-implemented on CTranslate2 with int8
  quantization: 4x faster, 1/4 the RAM of openai/whisper on CPU.
- `initial_prompt` biases the decoder toward our vocabulary (RAG, LoRA,
  recall@k...) so domain words survive.
- beam_size=1 (greedy) is plenty for short spoken answers and 2-4x faster.
- The model loads lazily: first transcription pays ~10s, after that ~0.5s.
"""
import threading

from faster_whisper import WhisperModel

from yourspeakreps.config import WHISPER_MODEL, WHISPER_THREADS

# Tech vocabulary the decoder would otherwise mangle ("RAG" -> "rag", etc.)
INITIAL_PROMPT = (
    "Interview about AI engineering: RAG, retrieval, recall, MRR, embeddings, "
    "pgvector, LLM, LoRA, fine-tuning, evals, guardrails, FastAPI, agent, "
    "prompt injection, hybrid search, reranking."
)

_model: WhisperModel | None = None
_lock = threading.Lock()  # model load is not thread-safe


def get_model() -> WhisperModel:
    """Lazy singleton — one shared model for the whole server."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = WhisperModel(
                    WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=WHISPER_THREADS,
                )
    return _model


def transcribe(audio_path: str) -> str:
    """Audio file (aiff/wav/webm/mp3 — PyAV decodes it all) -> English text."""
    segments, _info = get_model().transcribe(
        audio_path,
        language="en",            # practice language is English — pin it
        beam_size=1,
        initial_prompt=INITIAL_PROMPT,
        vad_filter=True,          # skip silence; fewer hallucinated words
    )
    return " ".join(s.text for s in segments).strip()
