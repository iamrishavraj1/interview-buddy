"""Smoke tests — config defaults, question banks, app routes.

Kept import-light: whisper loads lazily, so importing the server does not
pull the model into memory.
"""
from speakloop import config, questions


def test_config_defaults():
    assert config.PORT == 8001
    assert config.OLLAMA_MODEL
    assert config.PROJECT_ROOT.exists()


def test_question_banks_nonempty():
    assert questions.DAILY_STARTERS
    assert questions.AI_ENGINEER
    assert questions.BEHAVIORAL


def test_app_routes():
    from speakloop.server import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/" in paths            # static frontend mounted
    assert "/api/health" in paths  # health endpoint
