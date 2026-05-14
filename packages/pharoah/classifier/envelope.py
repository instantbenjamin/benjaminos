"""Envelope schema — the contract between any source and any sink.

See classifier-envelope-spec.md for the canonical definition. This module
is the source of truth at runtime; the spec doc and this file MUST stay
in sync.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    VOICENOTE_WEBHOOK = "voicenote_webhook"
    VOICENOTE_OBSIDIAN = "voicenote_obsidian"
    NOTABILITY_OCR = "notability_ocr"
    MANUAL = "manual"


class Category(StrEnum):
    TASK = "task"
    IDEA = "idea"
    JOURNAL = "journal"
    THERAPY = "therapy"
    MEETING_NOTE = "meeting_note"
    KNOWLEDGE_CAPTURE = "knowledge_capture"
    HABIT_LOG = "habit_log"
    HEALTH_SIGNAL = "health_signal"
    SIGNAL = "signal"
    MANUAL_TRIAGE = "manual_triage"


class OverallCategory(StrEnum):
    SINGLE_TASK = "single_task"
    SINGLE_IDEA = "single_idea"
    MIXED = "mixed"
    JOURNAL = "journal"
    THERAPY = "therapy"
    AMBIGUOUS = "ambiguous"


class PrivacyFlag(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    PRIVATE_SOFT = "private_soft"
    PRIVATE_HARD = "private_hard"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SourceArtifact(BaseModel):
    """Normalized input to the classifier — any intake source produces one of these."""

    source_id: str
    source_type: SourceType
    source_uri: str
    captured_at: datetime
    transcript: str
    metadata: dict = Field(default_factory=dict)
    title_hint: str | None = None


class ExtractedEntities(BaseModel):
    people: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    linear_issue_refs: list[str] = Field(default_factory=list)
    dates_mentioned: list[date] = Field(default_factory=list)


class Item(BaseModel):
    item_index: int
    category: Category
    subcategory: str | None = None
    title: str
    description: str = ""
    destination: str
    secondary_destinations: list[str] = Field(default_factory=list)
    due_date: date | None = None
    priority: Priority | None = None
    extracted_entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class Envelope(BaseModel):
    envelope_id: UUID = Field(default_factory=uuid4)
    source_id: str
    source_type: SourceType
    classified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    classifier_model: str
    classifier_version: str
    items: list[Item]
    overall_category: OverallCategory
    privacy_flag: PrivacyFlag = PrivacyFlag.PERSONAL
    needs_triage: bool = False
    raw_classifier_output: str = ""
    transcript_excerpt: str = ""

    def is_hard_private(self) -> bool:
        return self.privacy_flag == PrivacyFlag.PRIVATE_HARD

    def actionable_items(self) -> list[Item]:
        """Items routed to action-bearing sinks (ClickUp, Linear) — used for ack."""
        action_prefixes = ("clickup:", "linear:", "triage")
        return [i for i in self.items if i.destination.startswith(action_prefixes)]
