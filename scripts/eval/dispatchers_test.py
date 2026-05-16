import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from pharoah.classifier.envelope import Item, Category, ExtractedEntities
from scripts.classify_one import _to_supabase, _to_gbrain

sig = Item(item_index=0, category=Category.HEALTH_SIGNAL,
    subcategory="sleep", title="[smoke] Low energy 5h sleep",
    description="Subjective health signal from smoke test.",
    destination="supabase:public.health_snapshots",
    confidence=0.85, reasoning="Smoke",
    extracted_entities=ExtractedEntities(tags=["pharoah","smoke"]))
print("SUPABASE:", _to_supabase(sig, sig.destination))
