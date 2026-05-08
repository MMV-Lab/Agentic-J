"""Environment introspection for the supervisor.

Exposes the container snapshot (data/environment/container_snapshot.md) as a
searchable lookup so the agent can verify "is X installed and at what version?"
without dragging the full ~15 KB file into context.

Design goals (the tool MUST be bulletproof, since the agent quotes its output
verbatim and acts on it):

  * Token-based AND matching, not literal substring. "conda env cellpose"
    must match a row containing "env `cellpose4` (Python 3.11, cellpose 4.1.1)"
    even though backticks and word order break a naive substring search.
  * Markdown noise (backticks, asterisks, underscores, slashes, parentheses,
    pipes) is stripped before matching so it never blocks a hit.
  * Header rows are identified by parser context (the line preceding a
    `|---|---|` divider), not by a hardcoded list of known header words.
  * NEVER claim "package likely NOT installed". On no-AND-hit, fall back to
    OR-rank and surface the closest matches; on no-OR-hit, suggest similar
    tokens via difflib. The agent should always have something to look at.
"""

from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain.tools import tool


_CONTAINER_SNAPSHOT = Path("/app/data/environment/container_snapshot.md")
_HOST_SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "data" / "environment" / "container_snapshot.md"
)


def _resolve_snapshot_path() -> Optional[Path]:
    if _CONTAINER_SNAPSHOT.exists():
        return _CONTAINER_SNAPSHOT
    if _HOST_SNAPSHOT.exists():
        return _HOST_SNAPSHOT
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_sections(text: str) -> Dict[str, List[str]]:
    """
    Split markdown into sections keyed by `## ` / `### ` headings.

    Header rows of markdown tables are detected via context: a line is a
    header iff the next non-empty line is a divider (`|---|---|`). Headers
    are dropped on the spot so they never show up in `check_environment`
    output (which returns its rows untouched).
    """
    sections: Dict[str, List[str]] = {"preamble": []}
    current = "preamble"
    lines = text.splitlines()
    skip_idx: set[int] = set()

    # First pass: mark indices that are header-row-followed-by-divider as skipped.
    for i, line in enumerate(lines):
        if "---" in line and "|" in line and line.strip().startswith("|"):
            # Walk back to find the nearest non-empty preceding line.
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0 and "|" in lines[j]:
                skip_idx.add(j)
            skip_idx.add(i)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            current = stripped.lstrip("#").strip()
            sections.setdefault(current, [])
            continue
        if i in skip_idx:
            continue
        sections[current].append(line)
    return sections


_SECTIONS_CACHE: Optional[Dict[str, List[str]]] = None


def _get_sections() -> Dict[str, List[str]]:
    global _SECTIONS_CACHE
    if _SECTIONS_CACHE is not None:
        return _SECTIONS_CACHE
    path = _resolve_snapshot_path()
    if path is None:
        _SECTIONS_CACHE = {}
        return _SECTIONS_CACHE
    try:
        _SECTIONS_CACHE = _parse_sections(path.read_text(encoding="utf-8"))
    except Exception:
        _SECTIONS_CACHE = {}
    return _SECTIONS_CACHE


# ---------------------------------------------------------------------------
# Row classification (kept for backwards compat with existing tests)
# ---------------------------------------------------------------------------

def _is_data_row(line: str) -> bool:
    """
    Backwards-compat predicate. The new parser already drops headers via
    context, so this is mostly a safety net. Still rejects:
      - lines without a pipe
      - markdown dividers
      - blank lines
      - the small set of known header rows that appeared in the original
        snapshot before parser context-detection was added
    """
    if "|" not in line:
        return False
    if "---" in line:
        return False
    s = line.strip().lower()
    if not s:
        return False
    # Legacy header guards (still useful when callers pass raw rows that
    # bypassed the parser).
    KNOWN_HEADERS = (
        "| package ", "| jar ", "| component ",
        "| alias ", "| plugin ", "| name ", "| field ",
    )
    if any(s.startswith(h) for h in KNOWN_HEADERS):
        return False
    return True


# ---------------------------------------------------------------------------
# Normalization + tokenization (the actual matching brain)
# ---------------------------------------------------------------------------

# Characters we treat as token boundaries. Backticks, slashes (used in alias
# lists like "cellpose-sam / cpsam / cellpose 4 SAM"), pipes, parens, etc.
_NOISE_CHARS = "`*_/|()[]{}<>,;:.!?\"'"


def _normalize(text: str) -> str:
    r"""Lowercase, replace markdown / punctuation with spaces, collapse whitespace.

    Designed so that:
      "env `cellpose4`"        ->  "env cellpose4"
      "Cellpose-SAM / cpsam"   ->  "cellpose-sam cpsam"
      "**Java**"               ->  "java"
    """
    t = text.lower()
    for ch in _NOISE_CHARS:
        t = t.replace(ch, " ")
    # Hyphens are ambiguous: in "scikit-image" they're meaningful, in
    # "Cellpose-SAM" they're cosmetic. We DON'T strip them — token matching
    # uses substring lookup, so "cellpose" matches inside "cellpose-sam".
    return " ".join(t.split())


def _tokenize_query(q: str) -> List[str]:
    """Tokenize a query string.

    Keeps digit tokens even at length 1 ("cellpose 4" → ["cellpose", "4"])
    because version digits are meaningful. Drops other 1-char tokens
    ('a', 'i', etc.) — too noisy.
    """
    out = []
    for tok in _normalize(q).split():
        if len(tok) >= 2 or tok.isdigit():
            out.append(tok)
    return out


def _row_score(row: str, tokens: List[str]) -> int:
    """Return how many query tokens appear (as substrings) in the row."""
    norm = _normalize(row)
    return sum(1 for t in tokens if t in norm)


def _all_row_words(sections: Dict[str, List[str]]) -> set[str]:
    """Collect every word appearing in any data row, for difflib suggestions."""
    words: set[str] = set()
    for s, lines in sections.items():
        if s == "preamble":
            continue
        for line in lines:
            if not _is_data_row(line):
                continue
            for tok in _normalize(line).split():
                if len(tok) >= 3:
                    words.add(tok)
    return words


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

@tool
def check_environment(query: str = "", section: str = "") -> str:
    """
    Look up software installed in the running container.

    Use this to verify whether a Python package, conda env, Fiji plugin,
    Fiji jar, or system tool is available BEFORE recommending it in a
    pipeline. Cheaper than reading the full snapshot file.

    Behaviour:
      * Multi-word queries are tokenized; tokens are matched independently.
        First the tool tries to find rows containing ALL tokens; if none,
        it falls back to ranked partial matches (most-tokens-matched first).
      * Markdown formatting (backticks, asterisks, slashes) is stripped before
        matching, so "env `cellpose4`" is reachable via "env cellpose4" or
        "conda cellpose" or "cellpose 4".
      * The tool NEVER claims a package is "not installed" — that's a false
        negative trap. On a true zero-hit it returns difflib suggestions.

    Args:
        query: One or more keywords (case-insensitive). Examples:
            "stardist", "cellpose", "cellpose 4", "conda env cellpose",
            "scikit-image", "trackmate cellpose", "cuda", "java".
            Multiple words act as an AND filter (then OR fallback).
            Leave empty (with `section=`) to list every entry in one section.
        section: Optional. Limit the search to one section. Pass "list" to
            see all section names. Common sections:
            "System / runtime", "Main conda env",
            "conda env `cellpose`", "conda env `cellpose4`",
            "conda env `stardist`", "Appose / DeepImageJ env",
            "Fiji plugins", "Key Fiji jars", "Cellpose aliases".

    Returns:
        Matching rows grouped by section. On no-AND-hit, ranked partial
        matches with a "(matched N/M tokens)" tag. On true no-hit, difflib
        suggestions for each query token. On missing snapshot, a clear
        actionable error.
    """
    sections = _get_sections()
    if not sections:
        return (
            "Container snapshot not available. Expected at "
            f"{_CONTAINER_SNAPSHOT} (or {_HOST_SNAPSHOT} on the host). "
            "Regenerate the snapshot or ask the user."
        )

    # --- "list" sentinel ----------------------------------------------------
    if section.strip().lower() == "list":
        names = [name for name in sections if name and name != "preamble"]
        return "Available sections:\n- " + "\n- ".join(names)

    # --- Section filter (substring match, normalised) -----------------------
    sec_filter = _normalize(section) if section.strip() else ""
    if sec_filter:
        target = [s for s in sections
                  if sec_filter in _normalize(s) and s != "preamble"]
        if not target:
            return (
                f"No section matches '{section}'. "
                "Call check_environment(section='list') to see options."
            )
    else:
        target = [s for s in sections if s != "preamble"]

    # --- Tokenize query -----------------------------------------------------
    tokens = _tokenize_query(query)

    # --- No tokens: list all rows in target sections ------------------------
    if not tokens:
        return _format_hits(
            sections, target, lambda row: True, header=None,
        ) or "Snapshot section is empty."

    # --- Pass 1: AND match (every token appears) ----------------------------
    n_tokens = len(tokens)
    out_and = _format_hits(
        sections, target,
        predicate=lambda row: _row_score(row, tokens) == n_tokens,
        header=None,
    )
    if out_and:
        return out_and

    # --- Pass 2: OR fallback, ranked by token overlap -----------------------
    candidates: List[Tuple[str, str, int]] = []
    for s in target:
        for line in sections[s]:
            if not _is_data_row(line):
                continue
            n = _row_score(line, tokens)
            if n > 0:
                candidates.append((s, line.strip(), n))
    candidates.sort(key=lambda x: -x[2])

    if candidates:
        head = (
            f"No row matches all of {tokens}. Closest partial matches "
            f"(ranked by tokens matched out of {n_tokens}):"
        )
        body = []
        for s, line, n in candidates[:15]:
            body.append(f"  [{s}] {line}  (matched {n}/{n_tokens})")
        tail = (
            "If none of these are the runtime/package you meant, try fewer "
            "or different keywords, or check_environment(section='list')."
        )
        return "\n".join([head, *body, "", tail])

    # --- Pass 3: no token even partially matched. difflib suggestions -------
    pool = _all_row_words(sections)
    sugg_lines: List[str] = []
    for t in tokens:
        sug = get_close_matches(t, pool, n=3, cutoff=0.6)
        if sug:
            sugg_lines.append(f"  '{t}' → did you mean: {', '.join(sug)}?")

    msg = [
        f"No match for '{query}' in any section — none of these tokens "
        f"appear in any row: {tokens}.",
    ]
    if sugg_lines:
        msg.append("")
        msg.append("Suggestions:")
        msg.extend(sugg_lines)
    msg.append("")
    msg.append(
        "This does NOT prove the package is unavailable — the snapshot "
        "may be out of date or the name may differ. Cross-check with "
        "plugin_manager (for Fiji) or ask the user. Call "
        "check_environment(section='list') to see all sections."
    )
    return "\n".join(msg)


# ---------------------------------------------------------------------------
# Internal: format matched rows grouped by section
# ---------------------------------------------------------------------------

def _format_hits(
    sections: Dict[str, List[str]],
    target: List[str],
    predicate,
    header: Optional[str] = None,
) -> str:
    CAP = 60
    out: List[str] = []
    if header:
        out.append(header)
    for s in target:
        rows = [line for line in sections[s] if _is_data_row(line)]
        matches = [r for r in rows if predicate(r)]
        if not matches:
            continue
        out.append(f"## {s}")
        out.extend(matches[:CAP])
        if len(matches) > CAP:
            out.append(f"... ({len(matches) - CAP} more rows truncated; refine your query)")
        out.append("")
    return "\n".join(out).strip()
