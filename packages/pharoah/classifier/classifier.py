"""Classifier — the LLM call that turns a SourceArtifact into an Envelope.

For v1 the classifier is a single Anthropic API call using tool-use to
enforce the Envelope schema. The router (routes.py) applies guardrails on
top of the LLM output before dispatch.

Implementation note: this module is intentionally thin. The real work is
in the prompt (prompts.py) and the schema (envelope.py). Swapping models
or providers is one constant change here.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from pharoah.classifier.envelope import (
    Envelope, SourceArtifact,
)
from pharoah.classifier.prompts import (
    CLASSIFIER_MODEL_PRIMARY, CLASSIFIER_VERSION,
    SYSTEM_PROMPT, render_user_message,
)
from pharoah.classifier.routes import enforce_guardrails

log = logging.getLogger(__name__)


def classify(source: SourceArtifact, model: str | None = None,
             api_key: str | None = None, dry_run: bool = False) -> Envelope:
    """Classify a SourceArtifact into an Envelope.

    Args:
        source: normalized intake artifact
        model: override classifier model (default: CLASSIFIER_MODEL_PRIMARY)
        api_key: Anthropic API key (default: ANTHROPIC_API_KEY env var)
        dry_run: if True, return stub Envelope without calling the LLM
    """
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
    """Build a minimal valid Envelope for dry-run testing."""
    from pharoah.classifier.envelope import (
        Category, Item, OverallCategory, PrivacyFlag,
    )
    return Envelope(
        source_id=source.source_id,
        source_type=source.source_type,
        classifier_model=model,
        classifier_version=CLASSIFIER_VERSION,
        items=[Item(
            item_index=0,
            category=Category.MANUAL_TRIAGE,
            title="[dry-run stub]",
            destination="triage",
            confidence=0.99,
            reasoning="dry_run=True; no LLM call performed",
        )],
        overall_category=OverallCategory.AMBIGUOUS,
        privacy_flag=PrivacyFlag.PERSONAL,
        transcript_excerpt=source.transcript[:200],
    )


def _call_anthropic(source: SourceArtifact, model: str, api_key: str) -> Envelope:
    """Make the actual Anthropic API call with tool-use for Envelope schema.

    Stub for v1: this will call anthropic SDK with a 'produce_envelope' tool
    whose input_schema is derived from the Envelope pydantic model. The tool
    call arguments are validated into an Envelope instance.

    Not yet implemented — placeholder raises NotImplementedError. Wire up
    once packages/shared/clients/anthropic.py exists (or use the SDK
    directly here for v1).
    """
    raise NotImplementedError(
        "_call_anthropic not yet implemented. "
        "Use dry_run=True for routing tests until the Anthropic client is wired."
    )
