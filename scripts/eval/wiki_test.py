import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from pharoah.classifier.envelope import (
    Item, Category, ExtractedEntities)
from scripts.classify_one import _to_wiki

item = Item(
    item_index=0, category=Category.IDEA,
    subcategory="product_idea",
    title="Pharoah wiki dispatcher smoke test entry",
    description="If you're reading this, the wiki dispatcher works.",
    destination="wiki:personal/ideas/products/",
    confidence=0.95, reasoning="Smoke test.",
    extracted_entities=ExtractedEntities(
        tags=["pharoah", "smoke-test"]),
)
r = _to_wiki(item, item.destination)
print("RECEIPT:", r)
