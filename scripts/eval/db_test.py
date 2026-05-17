import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from datetime import datetime, UTC
from pharoah.classifier.envelope import (SourceArtifact, SourceType,
    Item, Category, Envelope, OverallCategory)
from scripts.classify_one import dispatch
from shared.clients.pharoah_db import PharoahDB

src = SourceArtifact(source_id="test:db:1",
    source_type=SourceType.MANUAL, source_uri="test://db",
    captured_at=datetime.now(UTC), transcript="smoke")
env = Envelope(source_id=src.source_id, source_type=src.source_type,
    classifier_model="claude", classifier_version="v",
    items=[Item(item_index=0, category=Category.MANUAL_TRIAGE,
                title="DB smoke", destination="triage",
                confidence=0.99, reasoning="t")],
    overall_category=OverallCategory.SINGLE_TASK)
r = dispatch(env, source=src)
print("ok", PharoahDB().is_processed("test:db:1"))
