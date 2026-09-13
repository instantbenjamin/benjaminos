"""HTTP-boundary tests: pagination, credential refresh and account isolation."""

import json
import time
from types import SimpleNamespace

import httpx
import pytest
from movie_calendar.cli import run
from movie_calendar.trakt import Trakt


def client(monkeypatch, tmp_path, handler):
    monkeypatch.delenv("TRAKT_CLIENT_FILE", raising=False)
    monkeypatch.delenv("TRAKT_TOKEN_FILE", raising=False)
    monkeypatch.setenv("TRAKT_CLIENT_ID", "test-id")
    monkeypatch.setenv("TRAKT_CLIENT_SECRET", "test-secret")
    c = Trakt(tmp_path, "test-user")
    c.http.close()
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    c.tokens = {
        "access_token": "test-access",
        "refresh_token": "test-refresh",
        "created_at": time.time(),
        "expires_in": 3600,
    }
    return c


def test_pagination_reads_all_pages(monkeypatch, tmp_path):
    pages = []

    def handler(request):
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(
            200,
            json=[{"movie": {"ids": {"trakt": page}}}],
            headers={"X-Pagination-Page-Count": "3"},
        )

    c = client(monkeypatch, tmp_path, handler)
    assert c.movie_ids("users/me/watchlist/movies") == {1, 2, 3}
    assert pages == [1, 2, 3]


def test_expired_token_refreshes_and_persists_rotation(monkeypatch, tmp_path):
    def handler(request):
        assert request.url.host == "auth.trakt.tv"
        assert "trakt-api-key" not in request.headers
        assert json.loads(request.content)["grant_type"] == "refresh_token"
        return httpx.Response(
            200,
            json={
                "access_token": "new",
                "refresh_token": "rotated",
                "created_at": time.time(),
                "expires_in": 3600,
            },
        )

    c = client(monkeypatch, tmp_path, handler)
    c.tokens["created_at"] = 0
    c.ensure_token()
    assert json.loads(c.token_path.read_text())["refresh_token"] == "rotated"
    assert c.token_path.stat().st_mode & 0o777 == 0o600


def test_wrong_account_blocks_writes(monkeypatch, tmp_path):
    c = client(
        monkeypatch,
        tmp_path,
        lambda _: httpx.Response(200, json={"user": {"username": "somebody-else"}}),
    )
    with pytest.raises(ValueError, match="does not match"):
        c.verify_account()


def test_error_does_not_echo_body_or_token(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path, lambda _: httpx.Response(429, text="sensitive-response"))
    with pytest.raises(RuntimeError) as exc:
        c.request("POST", "users/me/lists/1/items", body={"movies": []})
    assert "sensitive" not in str(exc.value)
    assert "test-access" not in str(exc.value)


def test_reconnect_ignores_broken_previous_tokens(monkeypatch, tmp_path):
    monkeypatch.delenv("TRAKT_CLIENT_FILE", raising=False)
    monkeypatch.setenv("TRAKT_CLIENT_ID", "test-id")
    monkeypatch.setenv("TRAKT_CLIENT_SECRET", "test-secret")
    path = tmp_path / "old-tokens.json"
    path.write_text("incomplete-json")
    monkeypatch.setenv("TRAKT_TOKEN_FILE", str(path))
    monkeypatch.setenv("TRAKT_ACCESS_TOKEN", "old-access")
    monkeypatch.setenv("TRAKT_TOKEN_CREATED_AT", "invalid")
    c = Trakt(tmp_path, "test-user", load_tokens=False)
    try:
        assert c.tokens == {}
        assert c.token_path == path
    finally:
        c.http.close()


def test_run_after_login_needs_no_infisical_token_seeds(monkeypatch, tmp_path):
    monkeypatch.delenv("TRAKT_CLIENT_FILE", raising=False)
    monkeypatch.delenv("TRAKT_TOKEN_FILE", raising=False)
    (tmp_path / "trakt-tokens.json").write_text(
        json.dumps(
            {
                "access_token": "local-access",
                "refresh_token": "local-refresh",
                "created_at": time.time(),
                "expires_in": 3600,
            }
        )
    )
    calls = []

    def fetch(args, **kwargs):
        calls.append(args[3])
        assert args[3] in {"benjaminos-trakt-clientid", "benjaminos-trakt-secret"}
        return SimpleNamespace(returncode=0, stdout="client-value", stderr="")

    def respond(request):
        assert request.headers["Authorization"] == "Bearer local-access"
        value = (
            {"user": {"username": "test-user"}} if request.url.path.endswith("/settings") else []
        )
        return httpx.Response(200, json=value)

    factory = httpx.Client
    monkeypatch.setattr("movie_calendar.infisical.subprocess.run", fetch)
    monkeypatch.setattr(
        "movie_calendar.trakt.httpx.Client",
        lambda **kwargs: factory(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(
        "movie_calendar.cli.scrape",
        lambda *args: {
            "upcoming_screenings": [],
            "fetched_at": "2026-09-13T12:00:00Z",
            "scope": "test",
        },
    )
    result = run(
        {
            "state_dir": str(tmp_path),
            "infisical": {"command": ["infisical"]},
            "trakt": {"username": "test-user", "list_id": "1"},
        },
        use_trakt=True,
    )
    assert result["trakt_additions"] == []
    assert len(calls) == 2
