"""Private, atomic runtime files and a process lock (macOS/Linux)."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cinemateca-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def run_lock(state: Path):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "run.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another Cinemateca run is active") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
