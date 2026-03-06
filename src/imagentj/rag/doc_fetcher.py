"""
Shared document fetching utilities for plugin documentation.

Used by:
  - enrich_registry.py   (building plugin_registry_update.json)
  - plugin_tools.py      (get_plugin_docs — live on-demand fetch)

Returns DocContent with both text and image_urls so callers can
optionally pass images to a vision-capable LLM (e.g. for dialog screenshots).
"""

import os
import re
import tempfile
import urllib.request
import multiprocessing
import requests
from dataclasses import dataclass, field

# ── Config ────────────────────────────────────────────────────────────────────

TIMEOUT     = 12
#MAX_CONTENT = 16000

session = requests.Session()
session.headers.update({"User-Agent": "PluginRegistryEnricher/1.0 (ImagentJ)"})


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class DocContent:
    text: str
    image_urls: list = field(default_factory=list)   # candidate dialog/screenshot URLs for vision
    source_url: str = ""
    url_type: str = ""


# ── URL classification ────────────────────────────────────────────────────────

def is_pdf(url: str) -> bool:
    return url.lower().rstrip("/").endswith(".pdf")

def is_imagej_net(url: str) -> bool:
    return "imagej.net" in url

def is_github_repo(url: str) -> bool:
    return bool(re.match(r"https?://github\.com/[^/]+/[^/]+/?$", url))

def is_github_subpage(url: str) -> bool:
    return "github.com" in url and not is_github_repo(url)

def classify_url(url: str) -> str:
    if not url:                         return "none"
    if is_pdf(url):                     return "pdf"
    if is_imagej_net(url):              return "imagej.net"
    if is_github_repo(url):             return "github-repo"
    if is_github_subpage(url):          return "github-subpage"
    if "readthedocs.io" in url:         return "readthedocs"
    if "github.io" in url:              return "github.io"
    if "forum.image.sc" in url:         return "forum"
    return "external"


# ── Image extraction ──────────────────────────────────────────────────────────

# Keywords that suggest a screenshot contains useful UI / parameter information
_SCREENSHOT_HINTS = {
    "dialog", "screenshot", "plugin", "window", "gui", "param",
    "option", "settings", "interface", "panel", "wizard", "menu",
}
# Keywords that identify noise (logos, icons, CI badges)
_NOISE_HINTS = {"logo", "icon", "badge", "button", "arrow", "banner", "avatar", "favicon"}


def extract_image_urls(html: str, base_url: str) -> list:
    """
    Extract candidate dialog/screenshot image URLs from a documentation page.

    Scoring:
      - Images whose src or alt text mention UI/parameter keywords score higher.
      - imagej.net/media images are almost always useful screenshots (+2).
      - SVGs, favicons, and noise keywords are excluded.

    No hard cap — all positively scored images are returned, ranked by score.
    The caller decides how many to use (pass to a vision LLM, etc.).
    """
    from urllib.parse import urljoin

    srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    alts = re.findall(r'<img[^>]+alt=["\']([^"\']*)["\']', html, re.IGNORECASE)

    scored = []
    for i, src in enumerate(srcs):
        if not src.startswith("http"):
            src = urljoin(base_url, src)

        src_lower = src.lower()
        alt_lower = alts[i].lower() if i < len(alts) else ""
        combined  = src_lower + " " + alt_lower

        if any(h in combined for h in _NOISE_HINTS):
            continue
        if src_lower.endswith(".svg") or "favicon" in src_lower:
            continue

        score = sum(1 for h in _SCREENSHOT_HINTS if h in combined)
        if "imagej.net/media" in src_lower:
            score += 2

        if score > 0:
            scored.append((score, src))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in scored]


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_html(url: str) -> DocContent | None:
    """Fetch an HTML page; extract text and candidate screenshot image URLs."""
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        images = extract_image_urls(r.text, url)
        return DocContent(
            text=_strip_html(r.text),#[:MAX_CONTENT],
            image_urls=images,
            source_url=url,
            url_type=classify_url(url),
        )
    except Exception as e:
        print(f"    HTML fetch failed: {e}")
        return None


def fetch_raw(url: str) -> DocContent | None:
    """Fetch plain text (raw GitHub files, readthedocs plain text, etc.)."""
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return DocContent(
            text=r.text, #[:MAX_CONTENT],
            source_url=url,
            url_type="raw",
        )
    except Exception as e:
        print(f"    Raw fetch failed: {e}")
        return None


def _find_github_readme(owner: str, repo: str) -> str | None:
    for branch in ("main", "master"):
        for name in ("README.md", "readme.md", "README.rst", "README"):
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
            try:
                if session.head(raw_url, timeout=TIMEOUT).ok:
                    return raw_url
            except Exception:
                continue
    return None


def fetch_github_repo(url: str) -> DocContent | None:
    """For root repo URLs: fetch the raw README, fall back to HTML."""
    parts = url.rstrip("/").split("/")
    if len(parts) >= 5:
        readme_url = _find_github_readme(parts[3], parts[4])
        if readme_url:
            print(f"    Fetching README: {readme_url}")
            return fetch_raw(readme_url)
    print("    No README found, falling back to HTML")
    return fetch_html(url)


def fetch_pdf(url: str) -> DocContent | None:
    """
    Download a PDF and extract text via docling (same config as the RAG pipeline).
    Catches RuntimeError from pypdfium for corrupt/unsupported documents.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice,
        )
        from docling.datamodel.base_models import InputFormat
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    except ImportError:
        print("    docling not available, skipping PDF")
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        print("    Downloading PDF ...")
        urllib.request.urlretrieve(url, tmp_path)

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = True
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=multiprocessing.cpu_count(),
            device=AcceleratorDevice.CPU,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=PyPdfiumDocumentBackend,
                )
            }
        )
        result = converter.convert(tmp_path)
        text   = result.document.export_to_markdown()

        # Extract embedded figures as base64 data URLs for vision LLM
        image_urls = []
        try:
            import base64, io
            for pic in result.document.pictures:
                if pic.image is None:
                    continue
                buf = io.BytesIO()
                pic.image.pil_image.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                image_urls.append(f"data:image/png;base64,{b64}")
        except Exception as e:
            print(f"    PDF image extraction skipped: {e}")

        return DocContent(
            text=text, #[:MAX_CONTENT],
            image_urls=image_urls,
            source_url=url,
            url_type="pdf",
        )

    except RuntimeError as e:
        # pypdfium cannot load certain PDFs (encrypted, corrupt, unsupported version)
        print(f"    PDF backend error (skipping): {e}")
        return None
    except Exception as e:
        print(f"    PDF extraction failed: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def fetch_content(url: str) -> DocContent | None:
    """
    Route to the right fetcher based on URL structure.

    Returns DocContent with:
      .text       — plain text of the documentation page
      .image_urls — ranked list of candidate dialog/screenshot URLs for vision LLM
    """
    if not url:
        return None
    if is_pdf(url):
        return fetch_pdf(url)
    if is_imagej_net(url):
        # MediaWiki API not reliable; HTML gives equivalent content
        return fetch_html(url)
    if is_github_repo(url):
        return fetch_github_repo(url)
    # GitHub subpages, readthedocs, github.io, forum, external sites
    return fetch_html(url)
