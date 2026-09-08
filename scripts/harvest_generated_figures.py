#!/usr/bin/env python3
"""
harvest_generated_figures.py
============================
Fill in the build-generated figures that `build_bioimage_course.py` left as
caption-only placeholders (``type: generated``, ``rendered: false``).

Those figures are produced at Jupyter-Book build time from hidden ``{code-cell}``
blocks and surfaced via ``{glue:figure}`` — so they exist only as rendered
``<img>`` on the published site, not as files in the source repo. For each one
this script:

  1. fetches the corresponding published page on bioimagebook.github.io,
  2. locates the rendered ``<figure>`` — by its ``:name:`` label (the HTML
     ``<figure id=…>``), falling back to a normalized caption match,
  3. downloads the PNG into ``assets/<chapter>/gen_<label>.png``,
  4. updates ``figure_index.json`` (``file`` + ``rendered: true``), and
  5. replaces the placeholder line in the content markdown with the real image.

Re-runnable: already-rendered figures are skipped, so it is safe to run again
after a content rebuild (it only fetches what is still pending).

Usage:
    python3 scripts/harvest_generated_figures.py --course skills/bioimage_course
    python3 scripts/harvest_generated_figures.py --course skills/bioimage_course --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

SITE = "https://bioimagebook.github.io/"

FIGURE_RE = re.compile(r"<figure\b([^>]*)>(.*?)</figure>", re.S)
ID_RE = re.compile(r'id="([^"]+)"')
SRC_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"')
CAP_RE = re.compile(r"<figcaption[^>]*>(.*?)</figcaption>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
FIGNO_RE = re.compile(r"^\s*Fig\.\s*\d+\s*", re.I)
# Build-generated images have content-hash filenames; static copies keep their
# original names. This tells the two apart for the positional fallback.
HASH_IMG_RE = re.compile(r"_images/[0-9a-f]{16,}\.")


def norm_caption(s: str) -> str:
    """Normalize a caption for fuzzy comparison across source vs. rendered HTML."""
    s = FIGNO_RE.sub("", s)                 # drop the "Fig. 3 " prefix the site adds
    s = re.sub(r"[*_`\\]", "", s)           # drop markdown emphasis / escapes
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def fetch(url: str, tries: int = 3, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "bioimage-course-harvester"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def parse_page_figures(html_text: str) -> list[dict]:
    """Every <figure> on the page -> {id, src, cap}, in document order."""
    figs = []
    for attrs, inner in FIGURE_RE.findall(html_text):
        fid = ID_RE.search(attrs)
        src = SRC_RE.search(inner)
        cap = CAP_RE.search(inner)
        figs.append({
            "id": fid.group(1) if fid else None,
            "src": src.group(1) if src else None,
            "cap": TAG_RE.sub("", cap.group(1)) if cap else "",
        })
    return figs


def refresh_manifest(course: Path, figure_index: dict) -> None:
    """Recompute the generated-figure render counts in MANIFEST.json so the
    build-time snapshot stays truthful after (re-)harvesting."""
    manifest_path = course / "MANIFEST.json"
    if not manifest_path.exists():
        return
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    gen = [v for v in figure_index.values() if v.get("type") == "generated"]
    rendered = sum(1 for v in gen if v.get("rendered"))
    man.setdefault("stats", {})["figures_generated_rendered"] = rendered
    man["stats"]["figures_generated_pending_render"] = len(gen) - rendered
    man["figures_harvested_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_path.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")


def match_figure(entry: dict, by_id: dict, by_cap: dict) -> dict | None:
    """Prefer the exact :name: label; fall back to a normalized-caption match,
    then a containment match for captions the site trims or rewords slightly."""
    if entry.get("label") and entry["label"] in by_id:
        return by_id[entry["label"]]
    key = norm_caption(entry["caption"])
    if key and key in by_cap:
        return by_cap[key]
    if key:
        for cap_key, fig in by_cap.items():
            if cap_key and (cap_key.startswith(key[:60]) or key.startswith(cap_key[:60])):
                return fig
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest build-generated figures from the published book.")
    ap.add_argument("--course", type=Path, required=True, help="Course package dir (build output).")
    ap.add_argument("--dry-run", action="store_true", help="Match only; download/write nothing.")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N pages (debug).")
    args = ap.parse_args(argv)

    course = args.course.resolve()
    index_path = course / "figure_index.json"
    figure_index = json.loads(index_path.read_text(encoding="utf-8"))

    pending = {k: v for k, v in figure_index.items()
               if v.get("type") == "generated" and not v.get("rendered")}
    if not pending:
        if not args.dry_run:
            refresh_manifest(course, figure_index)     # keep counts truthful on re-run
        print("Nothing to harvest — all generated figures already rendered.")
        return 0

    by_page: dict[str, list] = {}
    for fid, entry in pending.items():
        by_page.setdefault(entry.get("page") or "", []).append((fid, entry))

    stats = Counter()
    stats["pending"] = len(pending)
    md_edits: dict[Path, list[tuple[str, str]]] = {}
    unmatched: list[str] = []

    for pi, (page, items) in enumerate(sorted(by_page.items())):
        if args.limit and pi >= args.limit:
            break
        if not page:
            unmatched += [f"{fid} (no source page)" for fid, _ in items]
            stats["unmatched"] += len(items)
            continue

        url = urljoin(SITE, page + ".html")
        try:
            html_text = fetch(url).decode("utf-8", "replace")
        except Exception as exc:
            print(f"[!] page fetch failed: {url} ({exc})")
            stats["page_errors"] += 1
            continue
        stats["pages"] += 1

        page_figs = parse_page_figures(html_text)
        by_id = {f["id"]: f for f in page_figs if f["id"]}
        by_cap = {norm_caption(f["cap"]): f for f in page_figs}
        # All build-generated images on the page, in document order — used to
        # recover figures that render as a bare <img> (no <figure>, no caption).
        gen_imgs = [s for s in SRC_RE.findall(html_text) if HASH_IMG_RE.search(s)]

        # Pass 1 — match by label / caption. Pass 2 — assign whatever is left,
        # in document order, to the still-unused generated images.
        resolved: dict[str, str] = {}
        used: set[str] = set()
        leftovers: list[tuple[str, dict]] = []
        for fid, entry in items:
            m = match_figure(entry, by_id, by_cap)
            if m and m.get("src") and m["src"] not in used:
                resolved[fid] = m["src"]
                used.add(m["src"])
            else:
                leftovers.append((fid, entry))
        for (fid, _entry), src in zip(leftovers, [s for s in gen_imgs if s not in used]):
            resolved[fid] = src
            used.add(src)
            stats["positional"] += 1

        for fid, entry in items:
            src = resolved.get(fid)
            if not src:
                unmatched.append(f"{fid}  {entry['caption'][:60]!r}")
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1

            img_url = urljoin(url, src)
            stem = (entry.get("label") or fid.replace("#", "_")).replace("/", "_")
            dest_rel = f"assets/{entry['chapter']}/gen_{stem}.png"
            dest = course / dest_rel

            if not args.dry_run:
                try:
                    data = fetch(img_url)
                except Exception as exc:
                    print(f"[!] image fetch failed: {img_url} ({exc})")
                    stats["download_errors"] += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                time.sleep(0.05)                      # be polite to the host
            stats["downloaded"] += 1

            entry["file"] = dest_rel
            entry["rendered"] = True

            # Queue the placeholder rewrite (two forms: with / without caption).
            track = entry["track"]
            fname = "concept.md" if track == "concept" else f"{track}.md"
            md_path = course / "content" / entry["chapter"] / fname
            if entry["caption"]:
                old_line = f"> 🖼️ **Figure (generated):** {entry['caption']}"
                new_md = f"![{entry['caption']}]({dest_rel})\n\n*Figure —* {entry['caption']}"
            else:
                old_line = "> 🖼️ *(generated figure)*"
                new_md = f"![]({dest_rel})"
            md_edits.setdefault(md_path, []).append((old_line, new_md))

    if not args.dry_run:
        for md_path, edits in md_edits.items():
            if not md_path.exists():
                continue
            text = md_path.read_text(encoding="utf-8")
            for old, new in edits:
                if old in text:
                    text = text.replace(old, new, 1)
                else:
                    stats["placeholder_not_found"] += 1
            md_path.write_text(text, encoding="utf-8")
        index_path.write_text(json.dumps(figure_index, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        refresh_manifest(course, figure_index)

    print("\n=== harvest complete ===")
    print(json.dumps(dict(stats), indent=2))
    if unmatched:
        print(f"\nunmatched ({len(unmatched)}):")
        for u in unmatched[:20]:
            print("  -", u)
        if len(unmatched) > 20:
            print(f"  … and {len(unmatched) - 20} more")
    print("\n(dry run — no files written)" if args.dry_run else f"\nupdated: {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
