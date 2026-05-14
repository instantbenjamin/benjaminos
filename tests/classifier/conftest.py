"""Test fixtures for classifier tests."""
from datetime import datetime, UTC
import pytest
from pharoah.classifier.envelope import SourceArtifact, SourceType


@pytest.fixture
def source_factory():
    """Build a SourceArtifact for tests."""
    def _make(transcript: str, **kwargs):
        return SourceArtifact(
            source_id=kwargs.get("source_id", "test:1"),
            source_type=kwargs.get("source_type", SourceType.MANUAL),
            source_uri=kwargs.get("source_uri", "manual://test"),
            captured_at=kwargs.get("captured_at", datetime.now(UTC)),
            transcript=transcript,
            title_hint=kwargs.get("title_hint"),
        )
    return _make
