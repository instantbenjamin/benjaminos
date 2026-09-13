"""Retrieve only named Cinemateca secrets through an authenticated Infisical CLI."""

import os
import subprocess
from contextlib import contextmanager

TRAKT_KEYS = {
    "TRAKT_CLIENT_ID": "benjaminos-trakt-clientid",
    "TRAKT_CLIENT_SECRET": "benjaminos-trakt-secret",
    "TRAKT_REFRESH_TOKEN": "benjaminos-trakt-refresh-token",
    "TRAKT_ACCESS_TOKEN": "benjaminos-trakt-access-token",
    "TRAKT_TOKEN_CREATED_AT": "benjaminos-trakt-token-created-at",
    "TRAKT_TOKEN_EXPIRES_IN": "benjaminos-trakt-token-expires-in",
}


@contextmanager
def credentials(config: dict | None, *, trakt: bool, google: bool):
    """Temporarily inject selected secrets. Never log subprocess output/errors."""
    if not config:
        yield
        return
    keys = dict(TRAKT_KEYS) if trakt else {}
    if google:
        keys["BENJAMINOS_SA_JSON"] = "BENJAMINOS_SA_JSON"
    previous = {name: os.environ.get(name) for name in keys}
    try:
        command = config.get("command", ["infisical"])
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) for part in command)
        ):
            raise ValueError("Infisical command must be an operator-configured argument array")
        for name, secret in keys.items():
            args = [
                *command,
                "secrets",
                "get",
                secret,
                "--plain",
                "--silent",
                "--env=" + config.get("environment", "dev"),
                "--path=" + config.get("path", "/"),
            ]
            for field, flag in (("project_id", "--projectId="), ("domain", "--domain=")):
                if config.get(field):
                    args.append(flag + config[field])
            result = subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)
            if result.returncode or not result.stdout.strip():
                raise RuntimeError(
                    f"Could not read named Infisical secret {secret}; check CLI authentication and project access"
                )
            os.environ[name] = result.stdout.strip()
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
