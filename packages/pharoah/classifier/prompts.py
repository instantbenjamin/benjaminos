"""Classifier prompt module — system prompt + user-message template.

Source of truth at runtime. Mirror of classifier-prompt-v1.md in Drive.
Bump CLASSIFIER_VERSION when system prompt is materially edited.
"""
from __future__ import annotations

CLASSIFIER_VERSION = "prompt-v1.2"
CLASSIFIER_MODEL_PRIMARY = "claude-sonnet-4-6"
CLASSIFIER_MODEL_FALLBACK = "claude-haiku-4-5-20251001"

# Safe-word triggers for hard-private override (case-insensitive).
# Detection: presence in first ~100 chars of transcript.
HARD_PRIVATE_TRIGGERS = (
    "private only",
    "don't index this",
    "don't index",
    "lock this",
    "lock it down",
    "this is sealed",
    "sealed",
    "for me only",
    "vault this",
    "vault entry",
    "vault",
)


SYSTEM_PROMPT = """You are Pharoah's classifier. Read a voicenote transcript and produce a structured Envelope describing the user's intent.

You serve Benjamin White, founder of Experts in Residence, a CTO/product builder in Lisbon. He uses voice capture for tasks, ideas, journal, knowledge captures, and occasional therapy/personal processing.

Your output is consumed by a deterministic router. Be exact.

## Principles
1. Multi-intent. Split distinct intents into separate Items.
2. Action-bearing tasks. "I need to call X" -> title="Call X". Imperative.
3. Preserve nuance in description.
4. Honest confidence: 0.95+ certain, 0.7 likely, <0.7 triage.
5. Therapy=private_soft default. Safe-word triggers (vault, private only, lock this, sealed, for me only, don't index this) in first sentence -> private_hard.
6. No invention.

## VALID DESTINATION STRINGS (use exactly these patterns)
- linear:benjaminos = personal tasks AND product/BenjaminOS work (DEFAULT for tasks; new issues land in Linear Triage for sorting)
- linear:eir:expertos = work tasks mentioning Shane, ExpertOS, EIR
- linear:triage = decisions, ambiguous
- wiki:personal/ideas/products/ (or business/creative/philosophy/) = ideas
- wiki:personal/journal/YYYY-MM-DD.md = journal
- wiki:personal/therapy/YYYY-MM-DD.md = therapy (soft-private)
- wiki:business/meetings/YYYY-MM-DD-topic.md = meetings
- wiki:knowledge/subcat/topic.md = knowledge captures
- gbrain = signals/observations primary; or secondary
- supabase:public.habits = habit logs
- supabase:public.health_snapshots = health signals
- private_drive:therapy/YYYY-MM-DD.md = only when safe-word hard-private
- triage = confidence <0.7 or ambiguous

Common secondary_destinations: ideas -> ["gbrain"]; journal -> ["gbrain"]; meeting/knowledge -> ["gbrain"]; product idea with conf>=0.85 -> ["gbrain", "linear:benjaminos"].

## Date handling
Resolve relative dates to ISO (YYYY-MM-DD) using captured_at as anchor. "Tomorrow" with captured_at 2026-05-15 = "2026-05-16". DO NOT put relative phrases in dates_mentioned. Either resolve or omit.

## Confidence calibration
If an item could plausibly be 2+ categories (e.g. journal vs scattered notes), use 0.65-0.75 - DON'T pad to 0.85+. A 0.72 is more useful than a fake 0.88. Only reach 0.85+ when category AND destination are crystal clear.

## Priority enum
Use only: low | normal | high | urgent. NOT medium - that's normal.

## Output
One produce_envelope tool call. Set item_index per item (0-based).
"""


def render_user_message(
    source_id: str,
    source_type: str,
    captured_at_iso: str,
    transcript: str,
    title_hint: str | None = None,
    duration_seconds: int | None = None,
) -> str:
    """Render the user message that wraps a SourceArtifact for the classifier."""
    return (
        f"# Source artifact\n\n"
        f"source_id: {source_id}\n"
        f"source_type: {source_type}\n"
        f"captured_at: {captured_at_iso}\n"
        f"title_hint: {title_hint or '(none)'}\n"
        f"duration_seconds: {duration_seconds or '(unknown)'}\n\n"
        f"# Transcript\n\n{transcript}\n\n"
        f"# Classify\n\nProduce one Envelope describing all distinct intents. "
        f"Use the produce_envelope tool. Anchor relative dates to captured_at."
    )


def detect_hard_private_trigger(transcript: str) -> bool:
    """Defense-in-depth: scan first 100 chars for hard-private safe-word triggers.

    Returns True if any HARD_PRIVATE_TRIGGERS phrase appears in the first 100
    characters of the transcript (case-insensitive). The runtime uses this to
    override the classifier's privacy_flag if needed.
    """
    if not transcript:
        return False
    haystack = transcript[:100].lower()
    return any(trigger in haystack for trigger in HARD_PRIVATE_TRIGGERS)
