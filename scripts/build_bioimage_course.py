#!/usr/bin/env python3
"""
build_bioimage_course.py
========================
Ingest Pete Bankhead's *Introduction to Bioimage Analysis* Jupyter Book
(https://github.com/bioimagebook/bioimagebook.github.io, CC-BY 4.0) into a
self-contained "course package" that the Imagent_J education mode teaches from.

The book already splits every concept into a concept page plus sibling
``imagej`` and ``python`` pages (see its ``_toc.yml`` ``sections:``). We preserve
that as per-chapter *tracks* so the tutor can explain a concept and then, on
request, show the ImageJ and/or Python demonstration of it.

Outputs (under --out):
    curriculum.json      Whole-course structure: parts -> chapters -> tracks.
    figure_index.json    Every figure -> asset path, caption, chapter, type.
    practicals.json      Extracted Practical/Solution (& Question/Answer) pairs.
    content/<id>/...      Cleaned teaching markdown: concept.md, imagej.md,
                         python.md, and any sub-pages (e.g. macro walkthroughs).
    assets/<id>/...       Static images copied out of the source repo.
    MANIFEST.json         Provenance + build stats + unhandled-construct report.
    README.md             Attribution (required by CC-BY) and layout notes.

Two figure kinds are handled differently:
  * static    - screenshots/diagrams committed to the repo -> copied + indexed.
  * generated - produced at build time by hidden {code-cell} blocks surfaced via
                {glue:figure}. These have no file in the repo, so we keep their
                captions as placeholders (``rendered: false``); a later harvester
                can fill in the PNGs without touching anything else.

Usage:
    python3 scripts/build_bioimage_course.py --repo /path/to/clone --out skills/bioimage_course
    python3 scripts/build_bioimage_course.py --clone               --out skills/bioimage_course
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_URL = "https://github.com/bioimagebook/bioimagebook.github.io"
SITE_URL = "https://bioimagebook.github.io"
LICENSE = "CC-BY 4.0"

# --- Part numbering ---------------------------------------------------------
# Map the toc's part captions to (number, kind). ``None`` = skip entirely.
# Unknown captions fall through to AUTO numbering so the pipeline still runs if
# the book gains a new part. Numbers double as the prefix for chapter ids
# ("1.1", "2.3", ...) and are what a custom-course playlist references.
PART_CONFIG: dict[str, tuple[str, str] | None] = {
    "Front matter": None,                       # acknowledgements/license/disclaimer/changelog
    "Before we begin": ("0", "intro"),
    "Introducing images": ("1", "core"),
    "Processing & analysis": ("2", "core"),
    "Fluorescence microscopy": ("3", "core"),
    "Appendices": ("4", "appendix"),
}

TRACK_STEMS = {"imagej", "python"}              # a section with this stem is a track, not a sub-page

# Admonition class -> (emoji, label) for rendering callouts as blockquotes.
ADMONITIONS = {
    "tip": ("💡", "Tip"), "note": ("📝", "Note"), "hint": ("💡", "Hint"),
    "warning": ("⚠️", "Warning"), "caution": ("⚠️", "Caution"),
    "attention": ("❗", "Attention"), "important": ("❗", "Important"),
    "danger": ("🚫", "Important"), "error": ("⛔", "Error"),
    "seealso": ("🔗", "See also"), "info": ("ℹ️", "Info"),
    "margin": ("🗒️", "Aside"), "admonition": ("📌", ""),
}

# Line that opens a fenced block: 3+ backticks/tildes/colons, optional {name}.
FENCE_OPEN = re.compile(r"^([`~]{3,}|:{3,})(\{[^}\n]+\})?(.*)$")
OPTION_RE = re.compile(r"^\s*:([\w+-]+):\s?(.*)$")
ANCHOR_RE = re.compile(r"^\(([\w:-]+)\)=\s*$")   # MyST cross-ref target, e.g. (chap_pixels)=


# ===========================================================================
# MyST block parser
# ===========================================================================

def parse_blocks(text: str) -> list[tuple]:
    """Split MyST text into a flat list of blocks, one nesting level deep.

    Returns a list of either:
        ("text", raw_str)
        ("dir", name, inline_arg, options_dict, body_str)

    Nested directives (tab-items inside a tab-set, figures inside an
    admonition) stay packed inside ``body_str``; handlers recurse by calling
    ``parse_blocks`` again. Fences close on a line of the *exact same* marker
    run, which is precisely MyST's nesting rule (outer fences use more
    backticks/colons than the inner ones they contain).
    """
    lines = text.split("\n")
    blocks: list[tuple] = []
    buf: list[str] = []
    i, n = 0, len(lines)

    def flush() -> None:
        if buf:
            blocks.append(("text", "\n".join(buf)))
            buf.clear()

    while i < n:
        line = lines[i]
        m = FENCE_OPEN.match(line)
        if m:
            fence, brace, inline = m.group(1), m.group(2), m.group(3).strip()
            is_colon = fence[0] == ":"
            if brace:                                    # a directive fence
                name = brace[1:-1].strip()
                j, options = i + 1, {}
                # MyST allows two option syntaxes right after the opener:
                #   (a) a YAML block delimited by ---  (b) ":key: value" lines.
                if j < n and lines[j].strip() == "---":
                    k = j + 1
                    while k < n and lines[k].strip() != "---":
                        k += 1
                    try:
                        parsed = yaml.safe_load("\n".join(lines[j + 1:k])) or {}
                        if isinstance(parsed, dict):
                            options.update({str(a): str(b) for a, b in parsed.items()})
                    except Exception:
                        pass
                    j = k + 1
                else:
                    while j < n:
                        om = OPTION_RE.match(lines[j])
                        if not om:
                            break
                        options[om.group(1)] = om.group(2).strip()
                        j += 1
                # Body runs until a line that is exactly the opening marker.
                k = j
                while k < n and lines[k].rstrip() != fence:
                    k += 1
                flush()
                blocks.append(("dir", name, inline, options, "\n".join(lines[j:k])))
                i = k + 1
                continue
            if not is_colon:                             # plain code fence ```lang
                k = i + 1
                while k < n and lines[k].rstrip() != fence:
                    k += 1
                buf.extend(lines[i:k + 1])               # keep verbatim, incl. fences
                i = k + 1
                continue
            # A bare ``:::`` with no {name} is not a directive -> treat as text.
        buf.append(line)
        i += 1

    flush()
    return blocks


# ===========================================================================
# Inline normalisation (roles, raw HTML, entities)
# ===========================================================================

def _ref_text(inner: str) -> str:
    """Text of a {ref}/{doc}/{download} role: 'label <target>' -> 'label'."""
    return inner.split("<", 1)[0].strip() or "the linked section"


def normalize_inline(s: str) -> str:
    """Turn MyST inline roles and HTML entities into plain, readable markdown."""
    s = re.sub(r"\{kbd\}`([^`]*)`", r"`\1`", s)
    s = re.sub(r"\{guilabel\}`([^`]*)`", r"**\1**", s)
    s = re.sub(r"\{menuselection\}`([^`]*)`",
               lambda m: "**" + m.group(1).replace("-->", "→").strip() + "**", s)
    s = re.sub(r"\{(?:numref)\}`[^`]*`", "the figure", s)
    s = re.sub(r"\{(?:eq)\}`[^`]*`", "the equation", s)
    s = re.sub(r"\{(?:ref|doc|download)\}`([^`]*)`", lambda m: _ref_text(m.group(1)), s)
    s = re.sub(r"\{(?:term|abbr|command|file|sub|sup)\}`([^`]*)`", r"\1", s)
    for ent, rep in (("&rarr;", "→"), ("&larr;", "←"), ("&nbsp;", " "),
                     ("&mu;", "µ"), ("&times;", "×"), ("&deg;", "°")):
        s = s.replace(ent, rep)
    return s


LAUNCH_BADGE_RE = re.compile(r"\[!\[[^\]]*launch imagej\.js[^\]]*\]\([^)]*\)\]\(([^)]*)\)", re.I)
VIDEO_RE = re.compile(r"<video[\s\S]*?</video>", re.I)
IMG_RE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*?>", re.I)
ANCHOR_HTML_RE = re.compile(r"<a\b[^>]*/>|<a\b[^>]*>\s*</a>", re.I)   # empty <a name=…> anchors
CELLBREAK_RE = re.compile(r"(?m)^\+\+\+\s*$")                         # MyST cell separators
HARDBREAK_RE = re.compile(r"\\(?=\s|$)")                              # trailing line-continuation "\"
HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
BLANKS_RE = re.compile(r"\n{3,}")


# ===========================================================================
# Per-chapter cleaner
# ===========================================================================

class ChapterContext:
    """Cleans one chapter's markdown files, copying assets and collecting
    figures/practicals as it goes. One instance per chapter id."""

    def __init__(self, builder: "CourseBuilder", chapter_id: str, src_dir: Path):
        self.b = builder
        self.chapter_id = chapter_id
        self.src_dir = src_dir                       # source dir of the concept page
        self.assets_out = builder.out / "assets" / chapter_id
        self._asset_map: dict[str, str] = {}         # resolved src path -> rel dest
        self.current_track = "concept"

    # -- assets --------------------------------------------------------------
    def copy_asset(self, ref: str) -> str | None:
        """Resolve an image reference against the chapter dir (then repo root),
        copy it into assets/<id>/, and return its root-relative path."""
        ref = ref.split("?", 1)[0].split("#", 1)[0].strip()
        for base in (self.src_dir, self.b.repo):
            src = (base / ref).resolve()
            if src.is_file():
                break
        else:
            self.b.missing_assets.append(f"{self.chapter_id}: {ref}")
            return None
        key = str(src)
        if key in self._asset_map:
            return self._asset_map[key]
        self.assets_out.mkdir(parents=True, exist_ok=True)
        dest = self.assets_out / src.name
        # Guard against two different sources sharing a basename in one chapter.
        if dest.exists() and dest.stat().st_size != src.stat().st_size:
            dest = self.assets_out / f"{src.stem}__{abs(hash(key)) % 10000}{src.suffix}"
        shutil.copy2(src, dest)
        rel = f"assets/{self.chapter_id}/{dest.name}"
        self._asset_map[key] = rel
        self.b.assets_copied.add(rel)
        return rel

    # -- figures / practicals ------------------------------------------------
    def add_figure(self, *, caption: str, file: str | None, generated: bool,
                   ref: str, label: str | None = None) -> str:
        self.b.fig_counter[self.chapter_id] += 1
        fid = f"{self.chapter_id}#{self.b.fig_counter[self.chapter_id]}"
        self.b.figure_index[fid] = {
            "chapter": self.chapter_id,
            "track": self.current_track,
            "page": self.current_page,          # source page path (no ext) -> built .html URL
            "file": file,
            "caption": normalize_inline(" ".join(caption.split())),
            "type": "generated" if generated else "static",
            "rendered": (not generated),
            "label": label,                     # {glue:figure} :name: (– for _) -> HTML <figure> id
            "source_ref": ref,
        }
        self._chapter_fig_ids.append(fid)
        return fid

    def add_practical(self, prompt: str, solution: str) -> None:
        self.b.practicals.append({
            "id": f"{self.chapter_id}-p{len(self._chapter_prac) + 1}",
            "chapter": self.chapter_id,
            "track": self.current_track,
            "prompt": prompt.strip(),
            "solution": solution.strip(),
        })
        self._chapter_prac.append(1)

    # -- top-level entry -----------------------------------------------------
    def clean_file(self, path: Path, track: str) -> dict:
        """Clean one source .md, write it to content/<id>/<track>.md, and return
        a small record (title, output path, figure ids, practical count)."""
        self.current_track = track
        self.current_page = str(path.relative_to(self.b.repo).with_suffix(""))
        self._chapter_fig_ids: list[str] = []
        self._chapter_prac: list[int] = []

        raw = path.read_text(encoding="utf-8")
        raw = self._strip_frontmatter(raw)
        title = self._extract_title(raw)
        raw = "\n".join(l for l in raw.split("\n") if not ANCHOR_RE.match(l))

        body = self._render(parse_blocks(raw))
        body = self._finalize(body)

        out_dir = self.b.out / "content" / self.chapter_id
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = "concept.md" if track == "concept" else f"{track}.md"
        (out_dir / fname).write_text(body, encoding="utf-8")

        return {
            "title": title,
            "file": f"content/{self.chapter_id}/{fname}",
            "figures": list(self._chapter_fig_ids),
            "n_practicals": len(self._chapter_prac),
            "n_words": len(body.split()),
        }

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                return text[text.find("\n", end + 1) + 1:]
        return text

    @staticmethod
    def _extract_title(text: str) -> str:
        for line in text.split("\n"):
            if line.startswith("# "):
                return normalize_inline(line[2:].strip())
        return ""

    def _finalize(self, text: str) -> str:
        text = HTML_COMMENT_RE.sub("", text)
        text = ANCHOR_HTML_RE.sub("", text)
        text = CELLBREAK_RE.sub("", text)
        text = VIDEO_RE.sub("> 🎬 *(video demonstration in the online book)*", text)
        text = LAUNCH_BADGE_RE.sub(r"[▶ Launch ImageJ.JS](\1)", text)
        text = IMG_RE.sub(self._img_sub, text)
        text = normalize_inline(text)
        text = BLANKS_RE.sub("\n\n", text)
        return text.strip() + "\n"

    def _img_sub(self, m: re.Match) -> str:
        rel = self.copy_asset(m.group(1))
        return f"![]({rel})" if rel else ""

    # -- block rendering -----------------------------------------------------
    def _render(self, blocks: list[tuple]) -> str:
        out: list[str] = []
        for blk in blocks:
            if blk[0] == "text":
                out.append(blk[1])
                continue
            _, name, inline, options, body = blk
            handler = self._DISPATCH.get(name)
            if handler:
                out.append(handler(self, name, inline, options, body))
            elif name.startswith("glue"):
                out.append(self._h_glue(name, inline, options, body))
            elif name in ADMONITIONS or options.get("class") in ADMONITIONS:
                out.append(self._h_admonition(name, inline, options, body))
            else:
                self.b.unhandled[name] += 1            # degrade: keep the text, drop wrapper
                out.append(self._render(parse_blocks(body)))
        return "\n\n".join(s for s in out if s.strip())

    def _caption(self, body: str) -> str:
        """Rendered figure caption squashed to a single clean line."""
        c = HARDBREAK_RE.sub("", self._render(parse_blocks(body)).strip())
        return " ".join(c.split())

    def _h_figure(self, name, inline, options, body):
        cls = options.get("class", "")
        rel = self.copy_asset(inline) if inline else None
        caption = self._caption(body)
        label = (options.get("name") or "").replace("_", "-") or None
        self.add_figure(caption=caption, file=rel, generated=False, ref=inline, label=label)
        if "only-dark" in cls:                         # skip dark duplicate of a light figure
            return ""
        if not rel:
            return f"> 🖼️ *(figure: {caption})*" if caption else ""
        # Caption goes in alt-text (LLM-visible) plus a rendered line. Only the
        # "Figure —" label is emphasized, so a caption that itself contains
        # *emphasis* stays valid markdown.
        return f"![{caption}]({rel})" + (f"\n\n*Figure —* {caption}" if caption else "")

    def _h_glue(self, name, inline, options, body):
        caption = self._caption(body)
        label = (options.get("name") or "").replace("_", "-") or None
        self.add_figure(caption=caption, file=None, generated=True, ref=inline.strip(), label=label)
        return f"> 🖼️ **Figure (generated):** {caption}" if caption else \
               "> 🖼️ *(generated figure)*"

    def _h_code_cell(self, name, inline, options, body):
        tags = options.get("tags", "")
        boiler = ("thebe-init" in tags
                  or any(t in body for t in ("%load_ext autoreload", "from helpers import",
                                             "sys.path.append", "import glue")))
        if boiler:
            return ""
        if self.current_track == "python":
            self.b.code_examples += 1
            return f"```python\n{body.strip()}\n```"
        return ""                                       # concept/imagej: figure machinery -> drop

    def _h_tab_set(self, name, inline, options, body):
        items: list[tuple[str, str]] = []
        for blk in parse_blocks(body):
            if blk[0] == "dir" and blk[1] == "tab-item":
                items.append((blk[2].strip(), self._render(parse_blocks(blk[4])).strip()))
        labels = {lbl.lower(): txt for lbl, txt in items}
        prompt_key = next((k for k in ("practical", "question", "exercise") if k in labels), None)
        sol_key = next((k for k in ("solution", "answer") if k in labels), None)
        if prompt_key and sol_key:
            prompt, solution = labels[prompt_key], labels[sol_key]
            self.add_practical(prompt, solution)
            head = "📝 Practical" if prompt_key != "question" else "❓ Question"
            return (f"> **{head}**\n" + _quote(prompt) +
                    "\n\n<details>\n<summary>Show solution</summary>\n\n" +
                    solution + "\n\n</details>")
        return "\n\n".join(f"**{lbl}**\n\n{txt}" for lbl, txt in items)

    def _h_admonition(self, name, inline, options, body):
        cls = name if name in ADMONITIONS else options.get("class", "admonition")
        emoji, default_label = ADMONITIONS.get(cls, ("📌", ""))
        title = inline.strip() or default_label or cls.capitalize()
        inner = self._render(parse_blocks(body)).strip()
        return f"> **{emoji} {title}**\n>\n" + _quote(inner)

    def _h_math(self, name, inline, options, body):
        body = body.strip()
        return f"$$\n{body}\n$$" if body else ""

    def _h_verbatim(self, name, inline, options, body):
        """Directives we keep as-is (e.g. tables) rather than dropping."""
        return body.strip()

    def _h_passthrough(self, name, inline, options, body):
        return self._render(parse_blocks(body))


# Dispatch table built at module scope (a class-body comprehension can't see
# the method names). Maps directive name -> unbound handler(self, ...).
ChapterContext._DISPATCH = {
    "figure": ChapterContext._h_figure,
    "image": ChapterContext._h_figure,
    "code-cell": ChapterContext._h_code_cell,
    "tab-set": ChapterContext._h_tab_set,
    "math": ChapterContext._h_math,
    "list-table": ChapterContext._h_verbatim,
    "csv-table": ChapterContext._h_verbatim,
    "admonition": ChapterContext._h_admonition,
    "margin": ChapterContext._h_admonition,
    **{k: ChapterContext._h_admonition for k in ADMONITIONS},
}


def _quote(text: str) -> str:
    return "\n".join(("> " + l) if l else ">" for l in text.split("\n"))


# ===========================================================================
# Course builder / orchestrator
# ===========================================================================

class CourseBuilder:
    def __init__(self, repo: Path, out: Path):
        self.repo = repo
        self.out = out
        self.figure_index: dict[str, dict] = {}
        self.fig_counter: Counter = Counter()
        self.practicals: list[dict] = []
        self.assets_copied: set[str] = set()
        self.missing_assets: list[str] = []
        self.unhandled: Counter = Counter()
        self.code_examples = 0

    def build(self) -> dict:
        toc = yaml.safe_load((self.repo / "_toc.yml").read_text(encoding="utf-8"))
        parts_out, chapters_out = [], {}
        auto_num = 5

        for part in toc.get("parts", []):
            caption = part.get("caption", "")
            cfg = PART_CONFIG.get(caption, "AUTO")
            if cfg is None:
                continue
            if cfg == "AUTO":
                num, kind = str(auto_num), "core"
                auto_num += 1
            else:
                num, kind = cfg

            chap_ids = []
            for ci, chap in enumerate(part.get("chapters", []), start=1):
                cid = f"{num}.{ci}"
                rec = self._build_chapter(cid, num, chap)
                if rec:
                    chapters_out[cid] = rec
                    chap_ids.append(cid)
            if chap_ids:
                parts_out.append({"num": num, "title": caption, "kind": kind,
                                  "chapters": chap_ids})

        curriculum = {
            "title": "Introduction to Bioimage Analysis",
            "author": "Pete Bankhead",
            "source_url": SITE_URL,
            "source_repo": REPO_URL,
            "source_commit": _git_sha(self.repo),
            "license": LICENSE,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_parts": len(parts_out),
            "n_chapters": len(chapters_out),
            "parts": parts_out,
            "chapters": chapters_out,
        }
        self._write_outputs(curriculum)
        return curriculum

    def _build_chapter(self, cid: str, part_num: str, chap: dict) -> dict | None:
        concept_file = chap.get("file")
        if not concept_file:
            return None
        src_path = self._resolve_md(concept_file)
        if not src_path:
            self.missing_assets.append(f"MISSING PAGE: {concept_file}")
            return None

        ctx = ChapterContext(self, cid, src_path.parent)
        concept = ctx.clean_file(src_path, "concept")

        tracks: dict[str, str] = {}
        subpages: list[dict] = []
        for si, sec in enumerate(chap.get("sections", []) or [], start=1):
            sfile = sec.get("file")
            if not sfile:
                continue
            sp = self._resolve_md(sfile)
            if not sp:
                self.missing_assets.append(f"MISSING SECTION: {sfile}")
                continue
            stem = Path(sfile).stem
            if stem in TRACK_STEMS:
                rec = ctx.clean_file(sp, stem)
                tracks[stem] = rec["file"]
            else:
                # sub-page (e.g. a macro walkthrough): own cleaner keeps its assets
                sub_ctx = ChapterContext(self, f"{cid}.{si}", sp.parent)
                rec = sub_ctx.clean_file(sp, "concept")
                subpages.append({"num": f"{cid}.{si}", "title": rec["title"],
                                 "file": rec["file"], "figures": rec["figures"]})

        return {
            "id": cid,
            "part": part_num,
            "title": concept["title"],
            "slug": Path(concept_file).parent.name,
            "source_dir": str(src_path.parent.relative_to(self.repo)),
            "concept_file": concept["file"],
            "tracks": tracks,
            "subpages": subpages,
            "figures": concept["figures"],
            "n_practicals": sum(1 for p in self.practicals if p["chapter"] == cid),
            "has_imagej": "imagej" in tracks,
            "has_python": "python" in tracks,
        }

    def _resolve_md(self, file_ref: str) -> Path | None:
        """A toc file entry is a path without extension (usually)."""
        cand = self.repo / file_ref
        for p in (cand, cand.with_suffix(".md"), cand.with_suffix(".ipynb")):
            if p.is_file():
                return p
        return None

    def _write_outputs(self, curriculum: dict) -> None:
        _dump(self.out / "curriculum.json", curriculum)
        _dump(self.out / "figure_index.json", self.figure_index)
        _dump(self.out / "practicals.json", self.practicals)

        static = sum(1 for f in self.figure_index.values() if f["type"] == "static")
        generated = len(self.figure_index) - static
        manifest = {
            "source_repo": REPO_URL,
            "source_commit": _git_sha(self.repo),
            "license": LICENSE,
            "generated_at": curriculum["generated_at"],
            "stats": {
                "parts": curriculum["n_parts"],
                "chapters": curriculum["n_chapters"],
                "figures_total": len(self.figure_index),
                "figures_static": static,
                "figures_generated_pending_render": generated,
                "practicals": len(self.practicals),
                "assets_copied": len(self.assets_copied),
                "python_code_examples": self.code_examples,
            },
            "missing_assets": self.missing_assets,
            "unhandled_directives": dict(self.unhandled),
        }
        _dump(self.out / "MANIFEST.json", manifest)
        (self.out / "README.md").write_text(_readme(manifest), encoding="utf-8")
        self._manifest = manifest


# ===========================================================================
# small helpers
# ===========================================================================

def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _git_sha(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _readme(manifest: dict) -> str:
    s = manifest["stats"]
    return (
        "# Bioimage Analysis Course (generated)\n\n"
        f"Generated from **Introduction to Bioimage Analysis** by Pete Bankhead\n"
        f"(<{SITE_URL}>, commit `{manifest['source_commit'][:10]}`), "
        f"licensed **{LICENSE}**.\n\n"
        "> This directory is machine-generated by `scripts/build_bioimage_course.py`.\n"
        "> Content is adapted from the source book under CC-BY 4.0 — attribution above.\n\n"
        "## Layout\n"
        "- `curriculum.json` — parts → chapters → tracks (imagej/python) & sub-pages.\n"
        "- `content/<id>/` — cleaned teaching markdown (`concept.md`, `imagej.md`, `python.md`).\n"
        "- `assets/<id>/` — static figures copied from the source repo.\n"
        "- `figure_index.json` — figure id → asset path, caption, type.\n"
        "- `practicals.json` — Practical/Solution pairs for check-understanding.\n\n"
        "## Build stats\n"
        f"- {s['chapters']} chapters across {s['parts']} parts\n"
        f"- {s['figures_static']} static figures copied; "
        f"{s['figures_generated_pending_render']} generated figures pending render\n"
        f"- {s['practicals']} practicals; {s['python_code_examples']} python examples\n"
    )


def _clone(dest: Path) -> Path:
    if dest.exists():
        print(f"[clone] reusing existing clone at {dest}")
        return dest
    print(f"[clone] cloning {REPO_URL} -> {dest}")
    subprocess.check_call(["git", "clone", "--depth", "1", f"{REPO_URL}.git", str(dest)])
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the bioimage-analysis tutor course package.")
    ap.add_argument("--repo", type=Path, help="Path to an existing clone of the book repo.")
    ap.add_argument("--clone", action="store_true", help="Clone the book repo fresh.")
    ap.add_argument("--out", type=Path, required=True, help="Output course directory.")
    ap.add_argument("--clean", action="store_true", help="Remove --out before building.")
    args = ap.parse_args(argv)

    if args.repo:
        repo = args.repo.resolve()
    elif args.clone:
        # Clone into the system temp dir, never inside the repo — a clone under
        # skills/ would be picked up by the agent's SkillsMiddleware scan.
        repo = _clone(Path(tempfile.gettempdir()) / "bioimagebook_src")
    else:
        ap.error("provide --repo PATH or --clone")

    if not (repo / "_toc.yml").is_file():
        ap.error(f"{repo} does not look like the book repo (_toc.yml missing)")

    if args.clean and args.out.exists():
        shutil.rmtree(args.out)

    builder = CourseBuilder(repo, args.out.resolve())
    builder.build()

    m = builder._manifest
    print("\n=== build complete ===")
    print(json.dumps(m["stats"], indent=2))
    if m["unhandled_directives"]:
        print("unhandled directives:", m["unhandled_directives"])
    if m["missing_assets"]:
        print(f"missing assets/pages: {len(m['missing_assets'])} (see MANIFEST.json)")
    print(f"output: {builder.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
