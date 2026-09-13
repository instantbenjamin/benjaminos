"""HTTP-boundary tests: pagination, credential refresh and account isolation."""

import json
import time

import httpx
import pytest
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
