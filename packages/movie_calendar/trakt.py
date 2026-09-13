"""Trakt OAuth and list operations. Credentials never enter reports or logs."""

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .storage import write_json


class Trakt:
    def __init__(self, state: Path, username: str):
        self.username = username
        self.client = {}
        if os.environ.get("TRAKT_CLIENT_FILE"):
            self.client = json.loads(Path(os.environ["TRAKT_CLIENT_FILE"]).expanduser().read_text())
        for field in ("client_id", "client_secret"):
            self.client[field] = os.environ.get("TRAKT_" + field.upper(), self.client.get(field))
        if not all(self.client.get(k) for k in ("client_id", "client_secret")):
            raise ValueError("Set TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET (or TRAKT_CLIENT_FILE)")
        self.token_path = Path(
            os.environ.get("TRAKT_TOKEN_FILE", str(state / "trakt-tokens.json"))
        ).expanduser()
        self.tokens = json.loads(self.token_path.read_text()) if self.token_path.exists() else {}
        if not self.tokens and os.environ.get("TRAKT_ACCESS_TOKEN"):
            self.tokens = {
                "access_token": os.environ["TRAKT_ACCESS_TOKEN"],
                "refresh_token": os.environ.get("TRAKT_REFRESH_TOKEN"),
                "created_at": int(os.environ.get("TRAKT_TOKEN_CREATED_AT", "0")),
                "expires_in": int(os.environ.get("TRAKT_TOKEN_EXPIRES_IN", "0")),
            }
        self.http = httpx.Client(timeout=30, headers={"User-Agent": "BenjaminOS-Cinemateca/1.0"})

    def oauth(self, path: str, payload: dict) -> dict:
        response = self.http.post("https://auth.trakt.tv/oauth/" + path, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Trakt OAuth failed (HTTP {response.status_code}); reconnect if revoked"
            )
        return response.json()

    def save_tokens(self, tokens: dict) -> None:
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise ValueError("Incomplete Trakt token response")
        write_json(self.token_path, tokens)
        self.tokens = tokens

    def ensure_token(self) -> None:
        if (
            self.tokens.get("access_token")
            and time.time()
            < self.tokens.get("created_at", 0) + self.tokens.get("expires_in", 0) - 120
        ):
            return
        refresh = self.tokens.get("refresh_token") or os.environ.get("TRAKT_REFRESH_TOKEN")
        if not refresh:
            raise ValueError("Connect Trakt with movie-calendar login first")
        self.save_tokens(
            self.oauth(
                "token",
                {
                    **self.client,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                },
            )
        )

    def request(
        self, method: str, path: str, *, params: dict | None = None, body: dict | None = None
    ) -> httpx.Response:
        self.ensure_token()
        response = self.http.request(
            method,
            "https://api.trakt.tv/" + path,
            params=params,
            json=body,
            headers={
                "trakt-api-version": "2",
                "trakt-api-key": self.client["client_id"],
                "Authorization": "Bearer " + self.tokens["access_token"],
            },
        )
        if not response.is_success:
            # Do not retry writes blindly. A rerun re-reads list membership first.
            raise RuntimeError(
                f"Trakt API failed (HTTP {response.status_code}); rerun after resolving authentication/rate limits"
            )
        return response

    def verify_account(self) -> None:
        profile = self.request("GET", "users/settings").json()
        if profile["user"]["username"].casefold() != self.username.casefold():
            raise ValueError("Trakt account does not match configured username")

    def movie_ids(self, path: str) -> set[int]:
        ids, page = set(), 1
        while True:
            response = self.request("GET", path, params={"page": page, "limit": 100})
            ids.update(
                item["movie"]["ids"]["trakt"] for item in response.json() if item.get("movie")
            )
            pages = int(response.headers.get("X-Pagination-Page-Count", "1"))
            if page >= pages:
                return ids
            page += 1
            if page > 10000:
                raise ValueError("Invalid Trakt pagination")

    def list_path(self, list_id: str) -> str:
        return f"users/{quote(self.username, safe='')}/lists/{quote(list_id, safe='')}/items"

    def add(self, list_id: str, ids: list[int]) -> None:
        for start in range(0, len(ids), 100):
            result = self.request(
                "POST",
                self.list_path(list_id),
                body={"movies": [{"ids": {"trakt": ident}} for ident in ids[start : start + 100]]},
            ).json()
            if result.get("not_found", {}).get("movies"):
                raise ValueError("Trakt rejected reviewed movie IDs; inspect mappings")

    def login(self) -> None:
        device = self.oauth("device/code", {"client_id": self.client["client_id"]})
        print(f"Open {device['verification_url']} and enter {device['user_code']}", flush=True)
        deadline = time.monotonic() + device["expires_in"]
        interval = max(5, device.get("interval", 5))
        while time.monotonic() < deadline:
            time.sleep(interval)
            response = self.http.post(
                "https://auth.trakt.tv/oauth/device/token",
                json={**self.client, "code": device["device_code"]},
            )
            if response.status_code == 200:
                self.tokens = response.json()
                self.verify_account()
                self.save_tokens(self.tokens)
                return
            if response.status_code == 429:
                interval += 5
            elif response.status_code != 400:
                raise RuntimeError(f"Trakt authorization failed (HTTP {response.status_code})")
        raise RuntimeError("Trakt device authorization expired")
