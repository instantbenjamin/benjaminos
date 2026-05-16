"""Smoke tests for shared client init + credential validation."""
import pytest
from shared.clients.supabase import SupabaseClient
from shared.clients.linear import LinearClient
from shared.clients.clickup import ClickUpClient, INBOX_LIST_ID
from shared.clients.anthropic import AnthropicClient


def test_supabase_requires_creds(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        SupabaseClient()


def test_linear_requires_key(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LINEAR_API_KEY"):
        LinearClient()


def test_clickup_requires_key(monkeypatch):
    monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CLICKUP_API_KEY"):
        ClickUpClient()


def test_anthropic_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient()


def test_clickup_inbox_constant():
    assert INBOX_LIST_ID == "901403040568"
