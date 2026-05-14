"""Routes — the deterministic dispatch layer.

Consumes a validated Envelope and routes each Item to its sink. Each
destination prefix maps to a handler that returns a write receipt.

This module also runs runtime validation (defense-in-depth on top of
the classifier's outputs).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pharoah.classifier.envelope import (
    Category, Envelope, Item, PrivacyFlag,
)
from pharoah.classifier.prompts import (
    HARD_PRIVATE_TRIGGERS, detect_hard_private_trigger,
)

log = logging.getLogger(__name__)

AUTO_ROUTE_CONFIDENCE = 0.70
HIGH_CONFIDENCE = 0.85

ALLOWED_DESTINATION_PREFIXES = (
    "clickup:", "linear:", "wiki:", "gbrain", "supabase:",
    "private_drive:", "triage",
)


def validate_destination(dest: str) -> bool:
    return any(dest.startswith(p) or dest == p for p in ALLOWED_DESTINATION_PREFIXES)


def enforce_guardrails(envelope: Envelope, transcript: str) -> Envelope:
    """Apply runtime guardrails on top of classifier output."""
    if detect_hard_private_trigger(transcript):
        envelope.privacy_flag = PrivacyFlag.PRIVATE_HARD
        log.info("Hard-private trigger detected; forcing private_hard.")

    has_therapy = any(it.category == Category.THERAPY for it in envelope.items)
    if has_therapy and envelope.privacy_flag == PrivacyFlag.PERSONAL:
        envelope.privacy_flag = PrivacyFlag.PRIVATE_SOFT

    # 3. If private_hard, force all items to private_drive and drop secondaries
    if envelope.privacy_flag == PrivacyFlag.PRIVATE_HARD:
        for it in envelope.items:
            if not it.destination.startswith("private_drive:"):
                date_str = envelope.classified_at.date().isoformat()
                category = it.category.value
                it.destination = f"private_drive:{category}/{date_str}.md"
            it.secondary_destinations = []

    # 4. Demote low-confidence items to triage
    for it in envelope.items:
        if it.confidence < AUTO_ROUTE_CONFIDENCE:
            log.info(f"Item {it.item_index} confidence {it.confidence} < {AUTO_ROUTE_CONFIDENCE}; routing to triage")
            it.destination = "triage"
            it.secondary_destinations = []

    # 5. Drop invalid destinations + log
    for it in envelope.items:
        if not validate_destination(it.destination):
            log.warning(f"Item {it.item_index} invalid destination '{it.destination}'; routing to triage")
            it.destination = "triage"
        it.secondary_destinations = [
            d for d in it.secondary_destinations if validate_destination(d)
        ]

    # 6. Set needs_triage flag
    envelope.needs_triage = any(
        it.confidence < AUTO_ROUTE_CONFIDENCE or it.destination == "triage"
        for it in envelope.items
    )

    return envelope


# ─── Dispatch stubs ──────────────────────────────────────────────────────
# Each handler accepts an Item and returns a write receipt dict.
# Real implementations live in packages/shared/clients/. These stubs let
# us wire and test the routing logic before the clients are built.


def dispatch_clickup(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: packages.shared.clients.clickup.create_task()."""
    log.info(f"[STUB] clickup dispatch: {item.title}")
    return {"destination": item.destination, "stub": True, "title": item.title}


def dispatch_linear(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: packages.shared.clients.linear.create_issue()."""
    log.info(f"[STUB] linear dispatch: {item.title}")
    return {"destination": item.destination, "stub": True, "title": item.title}


def dispatch_wiki(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: write markdown to Drive via shared.clients.gws."""
    log.info(f"[STUB] wiki dispatch: {item.destination}")
    return {"destination": item.destination, "stub": True}


def dispatch_gbrain(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: gbrain put_page / add_timeline_entry via MCP."""
    log.info(f"[STUB] gbrain dispatch: {item.title}")
    return {"destination": "gbrain", "stub": True}


def dispatch_supabase(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: insert row via shared.clients.supabase."""
    log.info(f"[STUB] supabase dispatch: {item.destination}")
    return {"destination": item.destination, "stub": True}


def dispatch_private_drive(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: write to My Drive/Personal/Private/* via shared.clients.gws."""
    log.info(f"[STUB] private_drive dispatch: {item.destination}")
    return {"destination": item.destination, "stub": True}


def dispatch_triage(item: Item, **ctx) -> dict[str, Any]:
    """Stub. Real impl: create issue in BEN-94 Linear triage project."""
    log.info(f"[STUB] triage dispatch: {item.title} (confidence={item.confidence})")
    return {"destination": "triage", "stub": True, "title": item.title}


DISPATCHERS = {
    "clickup:": dispatch_clickup,
    "linear:": dispatch_linear,
    "wiki:": dispatch_wiki,
    "gbrain": dispatch_gbrain,
    "supabase:": dispatch_supabase,
    "private_drive:": dispatch_private_drive,
    "triage": dispatch_triage,
}


def _resolve_dispatcher(destination: str):
    for prefix, handler in DISPATCHERS.items():
        if destination == prefix or destination.startswith(prefix):
            return handler
    return None


def dispatch_envelope(env: Envelope, **ctx) -> dict[int, list[dict[str, Any]]]:
    """Dispatch all items to primary + secondary sinks. Returns {idx: [receipts]}."""
    receipts: dict[int, list[dict[str, Any]]] = {}
    for item in env.items:
        rs = []
        all_dests = [item.destination] + list(item.secondary_destinations)
        for dest in all_dests:
            h = _resolve_dispatcher(dest)
            if h is None:
                log.warning(f"No dispatcher for {dest}")
                continue
            try:
                rs.append(h(item, destination_override=dest, **ctx))
            except Exception as e:
                log.exception(f"Dispatch {dest} failed: {e}")
                rs.append({"destination": dest, "error": str(e)})
        receipts[item.item_index] = rs
    return receipts
