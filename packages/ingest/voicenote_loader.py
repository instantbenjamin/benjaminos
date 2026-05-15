"""Load a voicenote SourceArtifact from a local Obsidian-plugin markdown file.

Obsidian-plugin voicenote files at ~/wiki/voicenotes/<YYYY-MM-DD title>.md
have YAML frontmatter (recording_id, duration, created_at) and a body.
This module parses one file into a SourceArtifact ready for classify().
"""
from __future__ import annotations

import re
from datetime import datetime, time
from pathlib import Path
from typing import Any

import yaml

from pharoah.classifier.envelope import SourceArtifact, SourceType


def load_obsidian_voicenote(path: str | Path) -> SourceArtifact:
    """Parse an Obsidian-plugin voicenote markdown file into a SourceArtifact."""
    path = Path(path).expanduser().resolve()
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw)
    captured_at = _captured_at(frontmatter, path)
    title_hint = _title_hint_from_body(body, path)
    return SourceArtifact(
        source_id=f"obsidian:{path.name}",
        source_type=SourceType.VOICENOTE_OBSIDIAN,
        source_uri=f"file://{path}",
        captured_at=captured_at,
        transcript=body.strip(),
        title_hint=title_hint,
        metadata={
            "recording_id": frontmatter.get("recording_id"),
            "duration": frontmatter.get("duration"),
            "file_name": path.name,
        },
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into (frontmatter_dict, body)."""
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2]


def _captured_at(frontmatter: dict[str, Any], path: Path) -> datetime:
    """Best-effort captured_at: frontmatter created_at, else filename, else mtime."""
    from datetime import UTC, date as date_cls
    v = frontmatter.get("created_at")
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, date_cls):
        return datetime.combine(v, time(12, 0, tzinfo=UTC))
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).replace(tzinfo=UTC) if "T" not in v \
                else datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", path.name)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), 12, 0, tzinfo=UTC)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _title_hint_from_body(body: str, path: Path) -> str | None:
    """Pull a # H1 from the body, else strip date prefix from filename."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    name = path.stem
    return re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", name) or None
