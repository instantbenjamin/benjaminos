"""Classifier — turns SourceArtifact into Envelope via Anthropic tool-use."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from pharoah.classifier.envelope import (
    Category, Envelope, ExtractedEntities, Item,
    OverallCategory, PrivacyFlag, Priority, SourceArtifact,
)
from pharoah.classifier.prompts import (
    CLASSIFIER_MODEL_PRIMARY, CLASSIFIER_VERSION,
    SYSTEM_PROMPT, render_user_message,
)
from pharoah.classifier.routes import enforce_guardrails

log = logging.getLogger(__name__)


def classify(source: SourceArtifact, model: str | None = None,
             api_key: str | None = None, dry_run: bool = False) -> Envelope:
    """Classify a SourceArtifact. Returns a guardrail-enforced Envelope."""
    model = model or CLASSIFIER_MODEL_PRIMARY
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if dry_run:
        return _stub_envelope(source, model)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    env = _call_anthropic(source, model, api_key)
    env = enforce_guardrails(env, source.transcript)
    return env


def _stub_envelope(source: SourceArtifact, model: str) -> Envelope:
    """Deterministic stub for dry_run testing — skips LLM call AND guardrails."""
    return Envelope(
        source_id=source.source_id, source_type=source.source_type,
        classifier_model=model, classifier_version=CLASSIFIER_VERSION,
        items=[Item(item_index=0, category=Category.MANUAL_TRIAGE,
                    title="[dry-run stub]", destination="triage",
                    confidence=0.99, reasoning="dry_run=True")],
        overall_category=OverallCategory.AMBIGUOUS,
        privacy_flag=PrivacyFlag.PERSONAL,
        transcript_excerpt=source.transcript[:200],
    )


def _envelope_tool_schema() -> dict[str, Any]:
    """JSON schema for produce_envelope. LLM only fills LLM-owned fields."""
    return {
        "type": "object",
        "required": ["items", "overall_category", "privacy_flag", "needs_triage"],
        "properties": {
            "items": {"type": "array", "items": _item_schema(), "minItems": 1},
            "overall_category": {"type": "string",
                "enum": [v.value for v in OverallCategory]},
            "privacy_flag": {"type": "string",
                "enum": [v.value for v in PrivacyFlag]},
            "needs_triage": {"type": "boolean"},
        },
    }


def _item_schema() -> dict[str, Any]:
    return {"type": "object",
        "required": ["item_index","category","title","destination",
                     "confidence","reasoning"],
        "properties": _item_props()}


def _item_props() -> dict[str, Any]:
    return {
        "item_index": {"type": "integer"},
        "category": {"type": "string", "enum": [v.value for v in Category]},
        "subcategory": {"type": ["string", "null"]},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "destination": {"type": "string"},
        "secondary_destinations": {"type": "array", "items": {"type": "string"}},
        "due_date": {"type": ["string", "null"]},
        "priority": {"type": ["string", "null"], "enum": [v.value for v in Priority] + [None]},
        "extracted_entities": _entities_schema(),
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    }


def _entities_schema() -> dict[str, Any]:
    str_arr = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "people": str_arr, "projects": str_arr, "tags": str_arr,
            "linear_issue_refs": str_arr, "dates_mentioned": str_arr,
        },
    }


def _call_anthropic(source: SourceArtifact, model: str, api_key: str) -> Envelope:
    """Real Anthropic tool-use call. Returns a fully-formed Envelope."""
    from shared.clients.anthropic import AnthropicClient
    client = AnthropicClient(api_key=api_key)
    user_msg = render_user_message(
        source_id=source.source_id, source_type=source.source_type.value,
        captured_at_iso=source.captured_at.isoformat(),
        transcript=source.transcript,
        title_hint=source.title_hint,
        duration_seconds=source.metadata.get("duration_seconds"),
    )
    tool_input = client.classify_voicenote(
        system_prompt=SYSTEM_PROMPT, user_message=user_msg,
        envelope_tool_schema=_envelope_tool_schema(), model=model,
    )
    return _build_envelope_from_tool_input(source, tool_input, model)


def _build_envelope_from_tool_input(
    source: SourceArtifact, tool_input: dict[str, Any], model: str,
) -> Envelope:
    """Wrap LLM-produced content into a full Envelope, filling runtime fields."""
    if "items" not in tool_input or not tool_input.get("items"):
        import logging
        logging.getLogger(__name__).warning(
            f"LLM envelope missing items (keys={list(tool_input.keys())})"
        )
        return _triage_fallback(source, model)
    items = [_build_item(d) for d in tool_input["items"]]
    return Envelope(
        source_id=source.source_id,
        source_type=source.source_type,
        classifier_model=model,
        classifier_version=CLASSIFIER_VERSION,
        items=items,
        overall_category=OverallCategory(tool_input["overall_category"]),
        privacy_flag=PrivacyFlag(tool_input["privacy_flag"]),
        needs_triage=tool_input["needs_triage"],
        transcript_excerpt=source.transcript[:200],
    )


def _build_item(d: dict[str, Any]) -> Item:
    """Build an Item from the LLM's tool input dict, with safe defaults."""
    ee_in = d.get("extracted_entities") or {}
    from datetime import date
    dates = []
    for s in ee_in.get("dates_mentioned") or []:
        try:
            dates.append(date.fromisoformat(s))
        except Exception:
            log.warning(f"Bad date_mentioned: {s!r}")
    ee = ExtractedEntities(
        people=ee_in.get("people") or [],
        projects=ee_in.get("projects") or [],
        tags=ee_in.get("tags") or [],
        linear_issue_refs=ee_in.get("linear_issue_refs") or [],
        dates_mentioned=dates,
    )
    return _finalize_item(d, ee)


def _finalize_item(d: dict[str, Any], ee: ExtractedEntities) -> Item:
    """Construct Item with safe parsing for nullable date/priority."""
    from datetime import date
    due = None
    if d.get("due_date"):
        try:
            due = date.fromisoformat(d["due_date"])
        except Exception:
            log.warning(f"Bad due_date: {d['due_date']!r}")
    prio = None
    if d.get("priority"):
        p = d["priority"].lower().strip()
        synonyms = {"medium": "normal", "med": "normal", "mid": "normal",
                    "high priority": "high", "top": "urgent", "critical": "urgent"}
        p = synonyms.get(p, p)
        try:
            prio = Priority(p)
        except ValueError:
            log.warning(f"Unknown priority value: {d["priority"]!r}; dropping")
    return Item(
        item_index=d["item_index"], category=Category(d["category"]),
        subcategory=d.get("subcategory"), title=d["title"],
        description=d.get("description", ""), destination=d["destination"],
        secondary_destinations=d.get("secondary_destinations") or [],
        due_date=due, priority=prio, extracted_entities=ee,
        confidence=d["confidence"], reasoning=d.get("reasoning", ""),
    )


def _triage_fallback(source: SourceArtifact, model: str) -> Envelope:
    """Fallback when LLM response is malformed (truncated, missing items)."""
    return Envelope(
        source_id=source.source_id, source_type=source.source_type,
        classifier_model=model, classifier_version=CLASSIFIER_VERSION,
        items=[Item(item_index=0, category=Category.MANUAL_TRIAGE,
                    title="Malformed classifier response — manual triage",
                    description="LLM tool_use lacked items (likely truncation).",
                    destination="triage", confidence=0.99,
                    reasoning="Defensive fallback.")],
        overall_category=OverallCategory.AMBIGUOUS,
        privacy_flag=PrivacyFlag.PERSONAL, needs_triage=True,
        transcript_excerpt=source.transcript[:200],
    )
