import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from datetime import datetime, UTC
from pharoah.classifier.envelope import SourceArtifact, SourceType
from pharoah.classifier.classifier import classify

s = SourceArtifact(source_id='smoke:linear-default',
    source_type=SourceType.VOICENOTE_OBSIDIAN,
    source_uri='test://linear-default', captured_at=datetime.now(UTC),
    transcript='Add to my list: schedule a dentist appointment for June and pick up flowers for moms birthday on Saturday.',
    title_hint='Dentist + flowers')
e = classify(s)
print(f'overall: {e.overall_category} | priv: {e.privacy_flag}')
for it in e.items:
    print(f'  [{it.item_index}] {it.category.value:18s} conf={it.confidence:.2f} -> {it.destination}')
    print(f'         title: {it.title}')
