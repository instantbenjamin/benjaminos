#!/usr/bin/env python3
"""
raindrop_sync.py — bulk-sync Raindrop bookmarks into the BenjaminOS wiki vault.

Reads the RAINDROP_TOKEN from env or a .env file, walks the tier mapping below,
and writes one markdown file per bookmark in raw/reading/raindrop/, mirroring the
Raindrop collection tree as subfolders.

Tier 1: full pull (excerpt + URL in body, full frontmatter, ingest candidate).
Tier 2: stub-only (frontmatter + one-liner excerpt).
Tier 3: skip entirely (Pocket, Diigo, Delicious, File, Sprinter).

Idempotent — files already on disk (matched by *-<source_id>.md anywhere in
raw/reading/raindrop/) are skipped, so re-runs only add what's new.

Usage:
    export RAINDROP_TOKEN=...                # or put in .env
    python3 .claude/scripts/raindrop_sync.py             # default: tier 1+2
    python3 .claude/scripts/raindrop_sync.py --tier=1    # tier 1 only
    python3 .claude/scripts/raindrop_sync.py --tier=2    # tier 2 stubs only
    python3 .claude/scripts/raindrop_sync.py --dry-run   # preview without writing
    python3 .claude/scripts/raindrop_sync.py --collection="AI"  # one collection by name
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Vault paths (resolved relative to this script's location)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT = SCRIPT_DIR.parent.parent  # .claude/scripts/ -> .claude/ -> vault root
RAINDROP_ROOT = VAULT / "raw" / "reading" / "raindrop"
TOPICS_DIR = VAULT / "wiki" / "topics"
LOG_PATH = VAULT / "log.md"

API_BASE = "https://api.raindrop.io/rest/v1"
PERPAGE = 50
RATE_DELAY = 0.2  # seconds between API calls

# ---------------------------------------------------------------------------
# Collection tier mapping — single source of truth for sync behavior
# Format: (id, title, parent_id_or_None, tier)
# Update this when collections move tiers; keep in sync with .claude/commands/sync-raindrop.md
# ---------------------------------------------------------------------------

COLLECTIONS = [
    # ---- Tier 1: knowledge top-level ----
    (33682282, "AI", None, 1),
    (8248679,  "The Future is Now", None, 1),
    (1165943,  "Thinking + Ideas", None, 1),
    (695119,   "Tools + Services", None, 1),
    (695264,   "Wellness", None, 1),
    (693967,   "Work + Process", None, 1),
    (693958,   "Startups", None, 1),
    (1170347,  "Architecture", None, 1),
    (758853,   "Finance", None, 1),
    (695064,   "Music Creation", None, 1),
    (693959,   "VC", None, 1),
    (693960,   "Design-Product", None, 1),
    (693969,   "Design-Visual", None, 1),
    (33348100, "Photography", None, 1),
    (952242,   "Food", None, 1),
    (1017943,  "Parenting", None, 1),
    (37779561, "Books", None, 1),
    (14371339, "Surfing", None, 1),
    (33435825, "Guitar", None, 1),
    (1064690,  "Curiosities", None, 1),
    (1364159,  "Marketing", None, 1),
    (1184580,  "Writing", None, 1),
    (695042,   "Brand + Narrative", None, 1),
    (897280,   "Product", None, 1),
    (842306,   "IT", None, 1),
    (693966,   "Media", None, 1),
    (4486257,  "Agency", None, 1),
    (696117,   "Fishing", None, 1),
    (30880609, "Coffee", None, 1),
    (70306536, "Music", None, 1),
    (70306585, "Meditation", None, 1),
    (70306648, "Productivity", None, 1),
    (70306689, "Retail", None, 1),
    (70306692, "Art", None, 1),
    (70306879, "Buddhism", None, 1),
    (16379840, "Adventures-Local", None, 1),
    (6026679,  "ReadLater", None, 1),
    (53848145, "BJW-BenjaminOS", None, 1),
    (70063022, "EIR-Experts in Residence", None, 1),
    (4907525,  "OpenProject", None, 1),
    (1068787,  "My Portfolio", None, 1),
    (39535342, "Portugal", None, 1),
    (63566450, "Black Friday", None, 1),
    (26557877, "Hubspot", None, 1),
    # ---- Tier 1: nested ----
    (33682286, "Midjourney", 33682282, 1),
    (33682298, "ChatGPT", 33682282, 1),
    (33706513, "Music", 33682282, 1),                # AI > Music (different from top-level Music)
    (34821582, "Startup Studio", 33682282, 1),
    (42119063, "AI / Future of Work", 33682282, 1),
    (42111892, "AI Advisory Project", 33682282, 1),
    (70306512, "AI Tools", 33682282, 1),
    (37779552, "Sustainable Fashion", 8248679, 1),
    (13154397, "Niche Publishing", 8248679, 1),
    (22290971, "Bounty", 8248679, 1),
    (22598125, "Knowledgebase", 8248679, 1),
    (22598131, "Cultivate", 8248679, 1),
    (23669659, "Decentralized Mfg", 8248679, 1),
    (1028651,  "Startup Compensation", 693958, 1),
    # ---- Tier 2: project archives, top-level ----
    (3363586,  "WHT-1005", None, 2),
    (998390,   "WHT-343", None, 2),
    (998392,   "WHT-231", None, 2),
    (998393,   "WHT-SFO", None, 2),
    (1420738,  "WHT-448 Noe", None, 2),
    (27531770, "BRM-Braamcamp", None, 2),
    (887224,   "SFO-House Project", None, 2),
    (21688218, "HSN-House Numbers", None, 2),
    (22598142, "FSP-fuseproject", None, 2),
    (1371620,  "QPT-Qapital", None, 2),
    (695062,   "NXT-Project Next", None, 2),
    (1165149,  "TRP-Tripstr", None, 2),
    (799695,   "SPL-Superela", None, 2),
    (37779790, "SXP-Sixup", None, 2),
    (716219,   "CVN-Cavan", None, 2),
    (27167888, "MMA-Mima", None, 2),
    (34417687, "NRT-Northstar", None, 2),
    (23037066, "GLD-Goldfront", None, 2),
    (1258690,  "SPT-Spotify", None, 2),
    (747167,   "SHP-Shopper", None, 2),
    (34499831, "VAN-Vanlife", None, 2),
    (5233722,  "UNI-Unison", None, 2),
    (799696,   "UNT-Untold", None, 2),
    (5192851,  "FXN-FX Networks", None, 2),
    (1298190,  "FRN-Frances", None, 2),
    (37780468, "BUK-Buk", None, 2),
    (1148997,  "EXP-Expa", None, 2),
    (1275668,  "MOD-Mod Space", None, 2),
    (711230,   "FVR-Favorite", None, 2),
    (42451031, "Marea", None, 2),
    (37779610, "Prenuvo", None, 2),
    (37779713, "Wool", None, 2),
    (28193145, "Adventures", None, 2),
    (693968,   "Design-Home", None, 2),
    (1031553,  "Gear/Style", None, 2),
    (902336,   "Video-Streaming", None, 2),
    (6401839,  "Offsite", None, 2),
    (37779670, "Furniture", None, 2),
    (30880566, "Audiophile", None, 2),
    (28193139, "Projects (Archive)", None, 2),
    # ---- Tier 2: nested ----
    (8088530,  "Toni", 28193139, 2),
    (28193657, "Sweden", 28193145, 2),
    (26543773, "Sicily", 28193145, 2),
    (28193610, "Japan", 28193145, 2),
    (28193532, "Mexico", 28193145, 2),
    (28193218, "California", 28193145, 2),
    (1123261,  "Brazil", 28193145, 2),
    (959642,   "General", 28193145, 2),
    (31025299, "Dolomites Ski Trip", 28193145, 2),
    (7350629,  "Portugal", 28193145, 2),                # Adventures > Portugal (distinct from top-level)
    (33128073, "Porto+North", 28193145, 2),
    (23771444, "Greece", 28193145, 2),
    (37779571, "Catskills", 28193145, 2),
    (37779578, "Albania", 28193145, 2),
    (37779616, "Azores", 28193145, 2),
    (25972952, "Sales", 23037066, 2),
    (26176262, "Teamable", 23037066, 2),
    (26602160, "LiveAction", 23037066, 2),
    (27007239, "KeyFactor", 23037066, 2),
    (27228187, "NEA", 23037066, 2),
    (28192884, "Household", 27531770, 2),
    (28192832, "Design", 27531770, 2),
    (30956783, "Fireplace", 27531770, 2),
    (70307450, "Grill", 27531770, 2),
    # ---- Tier 3: skip-by-default ----
    (567738,   "Pocket", None, 3),
    (567734,   "Diigo", None, 3),
    (567739,   "Delicious", None, 3),
    (693963,   "File", None, 3),
    (13067024, "Sprinter", None, 3),
]

LOOKUP = {c[0]: c for c in COLLECTIONS}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(s, maxlen=60):
    s = (s or "").lower()
    s = re.sub(r"[\s_+/]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:maxlen].rstrip("-") or "untitled"


def folder_path(cid):
    """Relative path under raw/reading/raindrop/ for collection cid (mirrors parent chain)."""
    chain = []
    current = cid
    while current is not None:
        c = LOOKUP[current]
        chain.append(slugify(c[1]))
        current = c[2]
    return Path(*reversed(chain))


def topic_slug(cid):
    """Slug for the wiki/topics/<slug>.md page (parent-prefixed for nested)."""
    c = LOOKUP[cid]
    if c[2]:
        return f"{slugify(LOOKUP[c[2]][1])}-{slugify(c[1])}"
    return slugify(c[1])


def get_token():
    token = os.environ.get("RAINDROP_TOKEN", "").strip()
    if token:
        return token
    for env_path in (VAULT / ".env", VAULT / ".claude" / ".env"):
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("RAINDROP_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: RAINDROP_TOKEN not found.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Get your token at:", file=sys.stderr)
    print("  https://app.raindrop.io/settings/integrations", file=sys.stderr)
    print("  -> 'For Developers' -> create new app -> copy the Test token", file=sys.stderr)
    print("", file=sys.stderr)
    print("Then either:", file=sys.stderr)
    print(f"  export RAINDROP_TOKEN=<your_token>", file=sys.stderr)
    print(f"  echo 'RAINDROP_TOKEN=<your_token>' >> {VAULT}/.claude/.env", file=sys.stderr)
    sys.exit(1)


def api_get(path, token, params=None, retries=3):
    url = API_BASE + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    for attempt in range(retries):
        try:
            req = Request(url, headers={"Authorization": f"Bearer {token}"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 401:
                print("ERROR: 401 Unauthorized. Check your RAINDROP_TOKEN.", file=sys.stderr)
                sys.exit(1)
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  rate limited, sleeping {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"ERROR: HTTP {e.code} on {path}: {e.read().decode('utf-8', errors='replace')[:300]}", file=sys.stderr)
            return None
        except URLError as e:
            print(f"ERROR: network error on {path}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None


def list_raindrops(collection_id, token):
    """Yield every raindrop in the collection, paginated."""
    page = 0
    while True:
        data = api_get(f"/raindrops/{collection_id}", token, {"perpage": PERPAGE, "page": page, "sort": "-created"})
        if not data or "items" not in data:
            return
        items = data["items"]
        for item in items:
            yield item
        if len(items) < PERPAGE:
            return
        page += 1
        time.sleep(RATE_DELAY)


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def yaml_str(s):
    return json.dumps(str(s or ""))


def yaml_list(lst):
    if not lst:
        return "[]"
    return "[" + ", ".join(yaml_str(x) for x in lst) + "]"


_EXISTING_IDS_CACHE = None

def _build_existing_ids_cache():
    """Walk raw/reading/raindrop/ once and extract source_ids from filenames."""
    global _EXISTING_IDS_CACHE
    if not RAINDROP_ROOT.exists():
        _EXISTING_IDS_CACHE = set()
        return
    ids = set()
    pat = re.compile(r"-(\d+)\.md$")
    for fp in RAINDROP_ROOT.rglob("*.md"):
        m = pat.search(fp.name)
        if m:
            ids.add(int(m.group(1)))
    _EXISTING_IDS_CACHE = ids


def existing_id_file(rid):
    """O(1) check: does *-<rid>.md exist anywhere under RAINDROP_ROOT?"""
    global _EXISTING_IDS_CACHE
    if _EXISTING_IDS_CACHE is None:
        _build_existing_ids_cache()
    return rid in _EXISTING_IDS_CACHE


def _record_new_id(rid):
    if _EXISTING_IDS_CACHE is not None:
        _EXISTING_IDS_CACHE.add(rid)


def render_raindrop_md(item, collection, today, tier):
    rid = item["_id"]
    title = item.get("title") or "untitled"
    important = bool(item.get("important", False))
    priority = "high" if important else "normal"
    url = item.get("link", "")
    excerpt = (item.get("excerpt") or "").strip()
    note = (item.get("note") or "").strip()
    tags = item.get("tags", [])
    rtype = item.get("type", "link")
    created_at = item.get("created", "")

    body_extras = ""
    if note and tier == 1:
        body_extras = f"\n\n<!-- Notes from Raindrop -->\n{note}"

    return f"""---
title: {yaml_str(title)}
url: {url}
source_records:
  - raindrop://{rid}
domain: reading
collection: {yaml_str(collection[1])}
collection_id: {collection[0]}
tags: {yaml_list(tags)}
important: {str(important).lower()}
priority: {priority}
tier: {tier}
raindrop_type: {rtype}
created: {created_at}
captured: {today}
wiki_refs: []
---

# {title}

> {excerpt}

[Open source]({url}) · [Open in Raindrop](https://app.raindrop.io/my/0/item/preview/{rid}){body_extras}
"""


def touch_topic_page(cid, item_count, today):
    """Update the wiki/topics/<slug>.md page's item_count and last_synced fields."""
    slug = topic_slug(cid)
    path = TOPICS_DIR / f"{slug}.md"
    if not path.exists():
        return
    text = path.read_text()
    new_text = re.sub(r"^item_count: .*$", f"item_count: {item_count}", text, count=1, flags=re.M)
    new_text = re.sub(r"^last_synced: .*$", f"last_synced: {today}", new_text, count=1, flags=re.M)
    new_text = re.sub(r"^updated: .*$", f"updated: {today}", new_text, count=1, flags=re.M)
    if new_text != text:
        path.write_text(new_text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bulk sync Raindrop bookmarks into the wiki vault.")
    parser.add_argument("--tier", choices=["1", "2", "all"], default="all", help="Which tier to sync (default: all = tier 1+2).")
    parser.add_argument("--collection", help="Sync only this collection by name (case-insensitive substring match). Bypasses tier filter.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be pulled, don't write files.")
    parser.add_argument("--include-tier-3", action="store_true", help="Also sync Tier 3 (Pocket/Diigo/Delicious/File/Sprinter). Default: off.")
    args = parser.parse_args()

    token = get_token()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Pick which collections to sync
    if args.collection:
        needle = args.collection.lower()
        targets = [c for c in COLLECTIONS if needle in c[1].lower()]
        if not targets:
            print(f"No collection matching '{args.collection}' found.", file=sys.stderr)
            sys.exit(1)
    else:
        if args.tier == "1":
            tiers = {1}
        elif args.tier == "2":
            tiers = {2}
        else:
            tiers = {1, 2}
        if args.include_tier_3:
            tiers.add(3)
        targets = [c for c in COLLECTIONS if c[3] in tiers]

    print(f"Syncing {len(targets)} collections to {RAINDROP_ROOT}")
    print(f"Tier filter: {args.tier}{'+3' if args.include_tier_3 else ''}{', collection=' + args.collection if args.collection else ''}")
    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    total_created = 0
    total_skipped = 0
    total_starred = 0
    total_errors = 0

    for collection in targets:
        cid, name, parent, tier = collection
        rel_folder = folder_path(cid)
        target_dir = RAINDROP_ROOT / rel_folder

        print(f"[{tier}] {name} (#{cid}) → {rel_folder}/")

        c_created = 0
        c_skipped = 0
        c_starred = 0
        api_count = 0

        try:
            for item in list_raindrops(cid, token):
                api_count += 1
                rid = item["_id"]
                if existing_id_file(rid):
                    c_skipped += 1
                    continue
                if bool(item.get("important", False)):
                    c_starred += 1
                if not args.dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    title = item.get("title") or "untitled"
                    filepath = target_dir / f"{slugify(title)}-{rid}.md"
                    filepath.write_text(render_raindrop_md(item, collection, today, tier))
                    _record_new_id(rid)
                c_created += 1
        except Exception as e:
            print(f"    ERROR syncing {name}: {e}", file=sys.stderr)
            total_errors += 1
            continue

        print(f"    {api_count} fetched, {c_created} created, {c_skipped} skipped, {c_starred} starred")
        if not args.dry_run:
            touch_topic_page(cid, api_count, today)

        total_created += c_created
        total_skipped += c_skipped
        total_starred += c_starred
        time.sleep(RATE_DELAY)

    print()
    print("=" * 60)
    print(f"Sync complete.")
    print(f"  Collections: {len(targets)}")
    print(f"  Created: {total_created}")
    print(f"  Skipped (already existed): {total_skipped}")
    print(f"  Starred (priority=high): {total_starred}")
    print(f"  Errors: {total_errors}")

    if not args.dry_run:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        log_line = (
            f"{ts} | sync-raindrop | script | "
            f"tier={args.tier}{'+3' if args.include_tier_3 else ''} "
            f"collections={len(targets)} created={total_created} "
            f"skipped={total_skipped} starred={total_starred} errors={total_errors}\n"
        )
        with LOG_PATH.open("a") as f:
            f.write(log_line)
        print(f"  Logged to {LOG_PATH.name}")


if __name__ == "__main__":
    main()
