"""Verify scoped retrieval and cleanup without ever retrieving real secrets."""

import os
from types import SimpleNamespace

import pytest
from movie_calendar.infisical import credentials


def test_google_only_fetches_one_named_key_and_restores_environment(monkeypatch):
    monkeypatch.setenv("BENJAMINOS_SA_JSON", "previous")
    calls = []

    def fetch(args, **kwargs):
        calls.append(args)
        assert kwargs["capture_output"]
        return SimpleNamespace(returncode=0, stdout="test-value", stderr="")

    monkeypatch.setattr("movie_calendar.infisical.subprocess.run", fetch)
    with credentials({"command": ["infisical"]}, trakt=False, google=True):
        assert os.environ["BENJAMINOS_SA_JSON"] == "test-value"
    assert os.environ["BENJAMINOS_SA_JSON"] == "previous"
    assert len(calls) == 1
    assert calls[0][1:4] == ["secrets", "get", "BENJAMINOS_SA_JSON"]


def test_provider_errors_do_not_expose_secret_output(monkeypatch):
    def fail(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="private", stderr="sensitive")

    monkeypatch.setattr("movie_calendar.infisical.subprocess.run", fail)
    with (
        pytest.raises(RuntimeError) as exc,
        credentials({"command": ["infisical"]}, trakt=False, google=True),
    ):
        pass
    assert "private" not in str(exc.value)
    assert "sensitive" not in str(exc.value)


def test_login_only_requires_client_secrets(monkeypatch):
    calls = []

    def fetch(args, **kwargs):
        secret = args[3]
        calls.append(secret)
        assert secret in {"benjaminos-trakt-clientid", "benjaminos-trakt-secret"}
        return SimpleNamespace(returncode=0, stdout="test-client-value", stderr="")

    monkeypatch.setattr("movie_calendar.infisical.subprocess.run", fetch)
    with credentials({"command": ["infisical"]}, trakt=True, google=False, trakt_tokens=False):
        assert os.environ["TRAKT_CLIENT_ID"] == "test-client-value"
    assert len(calls) == 2
