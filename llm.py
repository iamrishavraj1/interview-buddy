"""LLM calls to the local Ollama model via its OpenAI-compatible API.

Concepts (docs/01-concepts.md §4-5):
- Ollama serves the SAME chat API shape as OpenAI at /v1 — only base_url
  changes, so this file would work unchanged against gpt-4o-mini too.
- qwen3 is a "thinking" model: it may spend output tokens on <think>...</think>
  before answering. We (a) append the /no_think soft switch to system prompts
  and (b) strip any think-blocks that still appear.
- JSON is enforced by PROMPT (contract) + robust extraction (never trust
  a model's claim that it produced JSON).
"""
import json
import re

from openai import OpenAI

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")  # key ignored locally

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def chat(system: str, messages: list[dict], *, temperature: float = 0.7,
         max_tokens: int = 600) -> str:
    """One completion. `messages` excludes the system prompt (added here)."""
    resp = _client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    return _THINK_BLOCK.sub("", text).strip()


def extract_json(text: str) -> dict:
    """Pull the first {...} block out of a possibly chatty reply.

    Fences, preamble and trailing remarks all get sliced off — if we still
    can't parse, the caller falls back to treating the text as spoken.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    return json.loads(text[start:end + 1])
