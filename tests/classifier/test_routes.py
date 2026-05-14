"""Tests for routing guardrails + dispatch."""
from pharoah.classifier.envelope import (
    Category, Envelope, Item, OverallCategory, PrivacyFlag, SourceType,
)
from pharoah.classifier.routes import enforce_guardrails, dispatch_envelope


def _envelope(items, transcript="x"):
    e = Envelope(
        source_id="t", source_type=SourceType.VOICENOTE_WEBHOOK,
        classifier_model="m", classifier_version="v",
        overall_category=OverallCategory.MIXED, items=items,
    )
    return enforce_guardrails(e, transcript)


def test_low_confidence_demotes_to_triage():
    e = _envelope([Item(item_index=0, category=Category.TASK, title="x",
                        destination="clickup:inbox", confidence=0.5)])
    assert e.items[0].destination == "triage"
    assert e.needs_triage is True


def test_high_confidence_kept():
    e = _envelope([Item(item_index=0, category=Category.TASK, title="x",
                        destination="clickup:inbox", confidence=0.95)])
    assert e.items[0].destination == "clickup:inbox"
    assert e.needs_triage is False


def test_therapy_promotes_to_soft_private():
    e = _envelope([Item(item_index=0, category=Category.THERAPY, title="x",
                        destination="wiki:personal/therapy/2026.md",
                        secondary_destinations=["gbrain"], confidence=0.92)])
    assert e.privacy_flag == PrivacyFlag.PRIVATE_SOFT


def test_vault_trigger_forces_hard_private():
    e = _envelope([Item(item_index=0, category=Category.THERAPY, title="x",
                        destination="wiki:personal/therapy/2026.md",
                        secondary_destinations=["gbrain"], confidence=0.92)],
                  transcript="Vault this. Heavy session today.")
    assert e.privacy_flag == PrivacyFlag.PRIVATE_HARD
    assert e.items[0].secondary_destinations == []
    assert e.items[0].destination.startswith("private_drive:")


def test_dispatch_returns_receipts():
    e = _envelope([Item(item_index=0, category=Category.TASK, title="Buy milk",
                        destination="clickup:inbox",
                        secondary_destinations=["gbrain"], confidence=0.95)])
    r = dispatch_envelope(e)
    assert 0 in r
    assert len(r[0]) == 2
