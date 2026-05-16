import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from pharoah.classifier.envelope import Item, Category, ExtractedEntities
from scripts.classify_one import _to_gbrain

gb = Item(item_index=0, category=Category.SIGNAL, subcategory="observation",
    title="[smoke] Pharoah gbrain dispatch test",
    description="Signal voicenote item written via CLI subprocess.",
    destination="gbrain", confidence=0.95, reasoning="Smoke",
    extracted_entities=ExtractedEntities(tags=["pharoah","smoke"]))
print("GBRAIN:", _to_gbrain(gb, gb.destination))
