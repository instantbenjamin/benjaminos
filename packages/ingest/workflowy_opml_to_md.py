#!/usr/bin/env python3
"""Convert WorkFlowy OPML export to markdown, splitting PARA top-levels at depth 1."""
import argparse, re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT = SCRIPT_DIR.parent.parent
DEFAULT_OUT = VAULT / "raw" / "personal" / "workflowy"

# Top-level titles where we write one file PER CHILD instead of one file for the whole tree
DEEP_SPLIT = {"0-inbox", "1-projects", "2-areas", "3-resources", "4-archives"}
# Root-level nodes with fewer than this many descendants get bundled into _misc.md
BUNDLE_THRESHOLD = 5


def slugify(s, maxlen=80):
    s = (s or "").lower()
    s = re.sub(r"[\s_+/]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:maxlen].rstrip("-") or "untitled"


def render_node(outline, depth=0, lines=None):
    if lines is None:
        lines = []
    text = outline.attrib.get("text", "").strip()
    note = outline.attrib.get("_note", "").strip()
    completed = outline.attrib.get("_complete") in ("true", "True", "1")
    indent = "  " * depth
    prefix = "- [x] " if completed else "- "
    if text:
        lines.append(f"{indent}{prefix}{text}")
    if note:
        for nl in note.split("\n"):
            nl = nl.strip()
            if nl:
                lines.append(f"{indent}  *{nl}*")
    for child in outline.findall("outline"):
        render_node(child, depth + 1, lines)
    return lines


def count_nodes(outline):
    n = 1
    for child in outline.findall("outline"):
        n += count_nodes(child)
    return n


def yaml_str(s):
    s = (s or "").replace('"', '\\"')
    return f'"{s}"'


def fm(title, slug, parent_slug, node_count, today, opml_filename, extra_tags=None):
    tags = ["workflowy", "bujo"] + (extra_tags or [])
    parent_uri = f"workflowy://export/{slug}" if parent_slug is None else f"workflowy://export/{parent_slug}/{slug}"
    workflowy_path = f"{parent_slug}/{title}" if parent_slug else title
    return [
        "---",
        f"title: {yaml_str(title)}",
        "type: source",
        "source_records:",
        f"  - {parent_uri}",
        "domain: personal",
        f"tags: [{', '.join(tags)}]",
        f"created: {today}",
        f"updated: {today}",
        f"exported_at: {today}",
        f"export_file: {yaml_str(opml_filename)}",
        f"workflowy_path: {yaml_str(workflowy_path)}",
        f"node_count: {node_count}",
        "wiki_refs: []",
        "---", "",
        f"# {title}", "",
    ]


def write_file(path, lines, dry_run):
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("opml")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    opml = Path(args.opml).resolve()
    out = Path(args.out).resolve()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"Reading: {opml}")
    print(f"Writing: {out}")
    print()

    tree = ET.parse(str(opml))
    body = tree.getroot().find("body")
    top = body.findall("outline")
    print(f"Found {len(top)} top-level Workflowy nodes\n")

    written = 0
    bundled = 0
    misc_lines = fm("Workflowy root miscellany", "_misc", None, 0, today, opml.name, extra_tags=["misc"])
    misc_lines.append(f"_Bundled root-level Workflowy nodes with fewer than {BUNDLE_THRESHOLD} children. Each appears as its own H2 section below._\n")

    for tl in top:
        title = tl.attrib.get("text", "").strip() or "untitled"
        slug = slugify(title)
        nc = count_nodes(tl)

        if slug in DEEP_SPLIT:
            sub = out / slug
            children = tl.findall("outline")
            print(f"  [folder] {slug}/   ({len(children)} children)")
            for child in children:
                ctitle = child.attrib.get("text", "").strip() or "untitled"
                cslug = slugify(ctitle)
                cnc = count_nodes(child)
                lines = fm(ctitle, cslug, slug, cnc, today, opml.name)
                lines.append(f"_From Workflowy `{title} > {ctitle}`. {cnc} nodes._\n")
                rendered = []
                for grandchild in child.findall("outline"):
                    render_node(grandchild, 0, rendered)
                lines.extend(rendered)
                lines.append("")
                write_file(sub / f"{cslug}.md", lines, args.dry_run)
                written += 1
        elif nc < BUNDLE_THRESHOLD:
            misc_lines.append(f"## {title}")
            misc_lines.append("")
            rendered = []
            for child in tl.findall("outline"):
                render_node(child, 0, rendered)
            misc_lines.extend(rendered)
            misc_lines.append("")
            bundled += 1
        else:
            lines = fm(title, slug, None, nc, today, opml.name)
            lines.append(f"_Imported from Workflowy. {nc} nodes._\n")
            rendered = []
            for child in tl.findall("outline"):
                render_node(child, 0, rendered)
            lines.extend(rendered)
            lines.append("")
            write_file(out / f"{slug}.md", lines, args.dry_run)
            written += 1
            print(f"  [file] {slug}.md  ({nc} nodes)")

    if bundled:
        write_file(out / "_misc.md", misc_lines, args.dry_run)
        print(f"  [bundle] _misc.md  ({bundled} small roots bundled)")

    print()
    print(f"{'(dry-run) ' if args.dry_run else ''}Wrote {written} files + {1 if bundled else 0} bundle ({bundled} bundled entries). Total root nodes: {len(top)}.")


if __name__ == "__main__":
    main()
