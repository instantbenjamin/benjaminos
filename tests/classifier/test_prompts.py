"""Tests for prompt module + safe-word trigger detection."""
import pytest
from pharoah.classifier.prompts import (
    CLASSIFIER_VERSION, HARD_PRIVATE_TRIGGERS, SYSTEM_PROMPT,
    detect_hard_private_trigger, render_user_message,
)


def test_version_pinned():
    assert CLASSIFIER_VERSION == "prompt-v1.3"


def test_system_prompt_non_empty():
    assert len(SYSTEM_PROMPT) > 200


def test_triggers_present():
    assert "vault" in HARD_PRIVATE_TRIGGERS
    assert "lock this" in HARD_PRIVATE_TRIGGERS
    assert "sealed" in HARD_PRIVATE_TRIGGERS


@pytest.mark.parametrize("transcript,expected", [
    ("Vault this. Heavy session.", True),
    ("Private only. Just for me today.", True),
    ("Lock this down — don't share.", True),
    ("Sealed. Just thinking out loud.", True),
    ("For me only. Some private processing.", True),
    ("Don't index this conversation.", True),
    ("Add buy milk to my grocery list.", False),
    ("I had an idea about the morning artifact.", False),
    ("", False),
])
def test_safe_word_detection(transcript, expected):
    assert detect_hard_private_trigger(transcript) == expected


def test_render_user_message_includes_transcript():
    msg = render_user_message(
        source_id="s:1", source_type="manual",
        captured_at_iso="2026-05-14T10:00:00Z",
        transcript="Test content",
    )
    assert "Test content" in msg
    assert "s:1" in msg
    assert "produce_envelope" in msg
