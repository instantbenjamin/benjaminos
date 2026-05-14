"""Tests for the Envelope pydantic schema."""
from pharoah.classifier.envelope import (
    Category, Envelope, Item, OverallCategory, PrivacyFlag, SourceType,
)


def _make(**kw):
    d = dict(source_id="t", source_type=SourceType.MANUAL,
             classifier_model="m", classifier_version="v",
             overall_category=OverallCategory.SINGLE_TASK,
             items=[Item(item_index=0, category=Category.TASK, title="x",
                         destination="clickup:inbox", confidence=0.95)])
    d.update(kw)
    return Envelope(**d)


def test_minimum_valid():
    e = _make()
    assert e.envelope_id is not None
    assert e.privacy_flag == PrivacyFlag.PERSONAL


def test_is_hard_private():
    assert _make(privacy_flag=PrivacyFlag.PRIVATE_HARD).is_hard_private()
    assert not _make(privacy_flag=PrivacyFlag.PRIVATE_SOFT).is_hard_private()
