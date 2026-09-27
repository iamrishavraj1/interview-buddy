"""LLM calls to the local Ollama model.

Concepts (docs/01-concepts.md §4-5):
- We use Ollama's NATIVE /api/chat (not the OpenAI-compat /v1) for one
  reason: the `think: false` parameter. qwen3 is a thinking model — without
  this it burned ~400 hidden reasoning tokens per reply (53 s); with it,
  ~40 tokens (1.7 s). Same model, 30x faster turns. To move this app to a
  cloud model, swap this function for the openai SDK pointed at the
  provider — everything else stays identical.
- `num_predict` (max output tokens) is capped: a stuck generation can't
  spin forever.
- JSON is enforced by PROMPT (contract) + robust extraction (never trust
  a model's claim that it produced JSON). A think-strip regex stays as a
  safety net for models that ignore think:false.
"""
import re

import httpx

from speakloop.config import OLLAMA_BASE_URL, OLLAMA_MODEL

# base_url arrives as http://localhost:11434/v1 -> native API lives at the root
_ROOT = OLLAMA_BASE_URL.removesuffix("/v1")

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def chat(system: str, messages: list[dict], *, temperature: float = 0.7,
         max_tokens: int = 350) -> str:
    """One completion. `messages` excludes the system prompt (added here)."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, *messages],
        "think": False,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    resp = httpx.post(f"{_ROOT}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    text = resp.json()["message"]["content"] or ""
    return _THINK_BLOCK.sub("", text).strip()


def extract_json(text: str) -> dict:
    """Pull the first {...} block out of a possibly chatty reply.

    Fences, preamble and trailing remarks all get sliced off — if we still
    can't parse, the caller falls back to treating the text as spoken.
    Then _unwrap_richest handles double-encoded JSON.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    import json

    data = json.loads(text[start:end + 1])
    return _unwrap_richest(data)


def _unwrap_richest(data: dict) -> dict:
    """Models sometimes double-encode a payload: the outer JSON's string
    values contain the real object. If any string value parses to a dict
    with MORE keys than the outer one, prefer it (recursively)."""
    import json

    best = data
    for value in data.values():
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                inner = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(inner, dict) and len(inner) > len(best):
                best = _unwrap_richest(inner)
    return best
