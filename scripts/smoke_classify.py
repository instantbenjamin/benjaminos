from datetime import datetime, UTC
from pharoah.classifier.envelope import SourceArtifact, SourceType
from pharoah.classifier.classifier import classify

TXT = ('Buy milk after work. Also remind me to check the gbrain doctor '
       'output tomorrow morning. And I had an idea for the morning artifact: '
       'what if it surfaced stalled threads where I have not replied in 2 weeks.')

s = SourceArtifact(source_id='smoke:2',
    source_type=SourceType.VOICENOTE_OBSIDIAN,
    source_uri='test://smoke', captured_at=datetime.now(UTC),
    transcript=TXT, title_hint='Errands + idea')

e = classify(s)
print(f'overall: {e.overall_category} | priv: {e.privacy_flag} | triage: {e.needs_triage}')
for it in e.items:
    print(f'  [{it.item_index}] {it.category.value:18s} conf={it.confidence:.2f} -> {it.destination}')
    if it.secondary_destinations: print(f'         +sec: {it.secondary_destinations}')
    print(f'         title: {it.title}')
    if it.due_date: print(f'         due: {it.due_date}')
