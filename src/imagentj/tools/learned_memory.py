"""learned_memory.py — a file-based, shareable wiki of the agent's verified
pitfalls and recipes, curated by a background "Librarian" subagent.

LAYOUT (all under a WRITABLE dir; /app/skills is read-only):
    pitfalls/CORE.<Lang>.md  promoted pitfalls — ALWAYS injected, fixed-size floor
    pitfalls/<Lang>.md       regular pitfall library — pulled via recall()
    recipes/CORE.<Lang>.md   featured recipes — ALWAYS injected (lean), fixed-size
    recipes/<Lang>.md        regular recipe library — one-offs + everything, recall()
    recipes/code/            the verified recipe scripts (read on demand; never injected)
    log.md                   append-only audit
CORE is per-language (the Python analyst never sees Groovy entries; each language's
CORE caps independently: <=12 pitfalls, <=5 recipes).
Entries are markdown bullets tagged in an HTML comment: <!--p:HASH seen:N lang:L
type:T class:C scope:S kw:aliases--> (pitfall) / <!--r:HASH seen:N lang:L chash:CH
kw:aliases--> (recipe). "CORE" is literally membership of a CORE.<Lang>.md file.

HOW IT WORKS:
  * RETRIEVE is fast + deterministic and needs no LLM: CORE pitfalls + featured
    recipes are injected as a fixed-size floor; recall() pulls the rest by
    keyword/symbol overlap (incl. Librarian-written keywords), with a GATED LLM
    fallback only when exact recall is empty AND a lexically-near candidate exists.
  * CAPTURE + CURATE is the Librarian subagent (agents.librarian_agent, defined
    with the skills/learned_memory skill). on_success() fires it in a BACKGROUND
    thread on every verified-green run — the task never waits. On a NORMAL run it
    just files the new recipe/pitfall. Dispatches are counted in a persisted .runcount
    that drives a TWO-TIER lint cadence (kept context-bounded as the library grows):
    every LINT_RECENT_EVERY-th dispatch reviews the newest entries; every
    LINT_FULL_EVERY-th reviews the next similarity-sorted shard via a persisted cursor
    (.lintcursor) so all entries are covered over time. Each lint pass shows at most
    LINT_BUDGET regular entries plus the (capped) CORE, then dedups and rebalances CORE
    (promotion AND demotion). It acts ONLY through the deterministic library_* tools
    below, so it can judge but never garble or lose the format.
"""
import os
import re
import math
import hashlib
import datetime
import threading
from typing import Optional, Dict, List

from langchain.tools import tool

ROOT = os.environ.get("LEARNED_ROOT", "/app/data/learned")   # writable (skills/ is read-only)
PITFALLS_DIR = os.path.join(ROOT, "pitfalls")
RECIPES_DIR = os.path.join(ROOT, "recipes")
RECIPE_CODE_DIR = os.path.join(RECIPES_DIR, "code")
LOG_PATH = os.path.join(ROOT, "log.md")

# CORE is per-language (CORE.<Language>.md), like the regular library, so the Python
# analyst never sees Groovy entries and each language's CORE caps independently.
CORE_MAX = 12             # fixed cap on CORE pitfalls per language
CORE_RECIPE_MAX = 5       # fixed cap on featured recipes per language
# Two-tier linting keeps the Librarian's context BOUNDED as the library grows:
#  - tier 1 (recent): every LINT_RECENT_EVERY dispatches, review the newest entries.
#  - tier 2 (full):   every LINT_FULL_EVERY dispatches, review the next similarity-
#    sorted shard via a persisted cursor, so all entries are covered over time.
# Either way at most LINT_BUDGET regular entries are shown per pass.
LINT_RECENT_EVERY = 3
LINT_FULL_EVERY = 10
LINT_RECENT_N = 10
LINT_BUDGET = 30
RECALL_K = 5
# A recipe whose tokens cover at least this fraction of the (de-noised) task query is a
# STRONG match — the SAME operation the task describes — so it should be reused VERBATIM
# (only inputs swapped) rather than rewritten. Below it, a recipe is merely RELATED and
# is adapted as a template. Deliberately not too high: task queries carry file-name noise.
RECIPE_STRONG_COVER = 0.5
DEEP_RECALL = os.environ.get("LEARNED_DEEP_RECALL", "1") != "0"

_EXT = {".groovy": "Groovy", ".py": "Python"}
# Stopwords stripped before matching: structural/filler words plus conversational verbs
# ("help", "please", "using", …) that would otherwise dilute the STRONG-match coverage.
_STOP = {"the", "and", "for", "with", "from", "this", "that", "image", "images",
         "script", "data", "use", "via", "into", "run", "all", "new", "get", "set",
         "help", "please", "using", "make", "create", "want", "need", "would", "like",
         "file", "files", "generate", "write", "code", "you", "can", "the"}
_LOCK = threading.Lock()
_PENDING: Dict[str, dict] = {}    # script_path -> buffered failure->fix lesson
_RUNCOUNT_PATH = os.path.join(ROOT, ".runcount")    # persisted dispatch counter (survives restarts)
_LINTCURSOR_PATH = os.path.join(ROOT, ".lintcursor")  # per-language tier-2 sweep cursor
_BLOCK_RE = re.compile(r"<!--[pr]:[^>]*-->.*?(?=\n<!--[pr]:|\Z)", re.S)
# Plugin/environment-specific lessons are NEVER promoted to CORE: they are version/
# install-site specific, so injecting them into every run is noise (and can be wrong
# on another deployment). They stay recall-only in the regular library.
# Match REAL plugin/environment signals only — NOT the bare word "plugin". ImageJ's
# own classes live in the ij.plugin.* package, so matching "plugin" alone false-flags
# ordinary import lessons (e.g. "import ij.plugin.ImageCalculator") as plugin-scoped
# and wrongly bars them from CORE.
_PLUGIN_RE = re.compile(
    r"(update[\s-]?site|not installed|isn'?t installed|missing dependency|"
    r"install (?:the )?\S+ plugin|enable (?:the )?\S+ update site)", re.I)

__all__ = ["register_pending_lesson", "on_success", "core_pitfalls", "core_recipes",
           "recall", "library_add_pitfall", "library_add_recipe", "library_remove",
           "library_set_core"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _hash(s: str) -> str:
    """Short stable id: first 8 hex chars of the SHA-1 of the trimmed string. Used to
    derive an entry's [HASH] from its rule (pitfall) / name (recipe) and a recipe's
    content hash (chash) from its code."""
    return hashlib.sha1(s.strip().encode("utf-8")).hexdigest()[:8]

def _read(path: str) -> str:
    """Read a file's text, returning "" if it does not exist / can't be read (so callers
    never have to guard for a missing page)."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""

def _tokens(*parts: str) -> set:
    """Tokenise the given text pieces into a lowercase set of ≥3-char alphanumeric words
    with stopwords removed. The unit of matching for recall and similarity ranking."""
    text = " ".join(p for p in parts if p)
    return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text)} - _STOP

def _pitfall_page(language: str) -> str:
    """Path to the regular (recall-searchable) pitfall page for a language."""
    return os.path.join(PITFALLS_DIR, f"{language}.md")

def _recipe_page(language: str) -> str:
    """Path to the regular (recall-searchable) recipe page for a language."""
    return os.path.join(RECIPES_DIR, f"{language}.md")

def _core_pitfall_page(language: str) -> str:
    """Path to the always-injected CORE pitfall page for a language."""
    return os.path.join(PITFALLS_DIR, f"CORE.{language}.md")

def _core_recipe_page(language: str) -> str:
    """Path to the always-injected CORE recipe page for a language."""
    return os.path.join(RECIPES_DIR, f"CORE.{language}.md")

def _blocks(path: str) -> List[str]:
    """Parse a page into its list of entry blocks (each = the HTML-comment metadata line
    plus its markdown body), via the _BLOCK_RE splitter. Empty for a missing page."""
    return _BLOCK_RE.findall(_read(path))

def _lang_blocks(path: str, language: str) -> List[str]:
    """The blocks in a page whose lang: tag matches (defensive filter; pages are already
    per-language)."""
    return [b for b in _blocks(path) if _lang_of(b) == language]

def _seen(block: str) -> int:
    """The reinforcement count (seen:N) parsed from a block's metadata; 1 if absent."""
    m = re.search(r"\bseen:(\d+)", block)
    return int(m.group(1)) if m else 1

def _lang_of(block: str) -> str:
    """The language (lang:L) parsed from a block's metadata, or "" if absent."""
    m = re.search(r"\blang:(\w+)", block)
    return m.group(1) if m else ""

def _hash_of(block: str) -> str:
    """The entry [HASH] parsed from a block's opening <!--p:HASH / <!--r:HASH marker."""
    m = re.match(r"<!--[pr]:(\w+)", block)
    return m.group(1) if m else ""

def _kw(block: str) -> set:
    """The Librarian-written search aliases (kw:a,b,c) parsed from a block, as a set."""
    m = re.search(r"\bkw:([^>]*)-->", block)
    return {k.strip().lower() for k in m.group(1).split(",")} - {""} if m else set()

def _norm_kw(keywords) -> str:
    """Normalise a Librarian-supplied alias list (comma/semicolon/list) into a clean,
    deduped, lowercase, comma-joined string (bounded to 8) for the kw: tag."""
    if isinstance(keywords, (list, tuple, set)):
        keywords = ",".join(str(k) for k in keywords)
    out, seen = [], set()
    for k in re.split(r"[,;]", keywords or ""):
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(k)
    return ",".join(out[:8])

def _body(block: str) -> str:
    """The human-readable part of a block: everything after the metadata comment (the
    bullet rule/name + description + snippet/SCRIPT lines)."""
    return block.split("-->", 1)[1].strip("\n")

def _match_tokens(block: str) -> set:
    """The full token set an entry can be matched on: its body tokens PLUS its keyword
    aliases. Used by recall scoring and by similarity ranking/clustering."""
    return _tokens(_body(block)) | _kw(block)

def _scope_of(block: str) -> str:
    """The scope (scope:general|plugin) parsed from a block; "" if absent."""
    m = re.search(r"\bscope:(\S+)", block)
    return m.group(1) if m else ""

def _is_plugin(rule: str, error_type: str, class_involved: str) -> bool:
    """True if a lesson is plugin/environment-specific (error_type 'plugin', or the rule/
    class matches _PLUGIN_RE). Such lessons are deployment-specific and never promoted to
    CORE — they stay recall-only."""
    return ((error_type or "").strip().lower() == "plugin"
            or bool(_PLUGIN_RE.search(" ".join((rule or "", class_involved or "")))))

def _script_path_of(block: str) -> str:
    """The recipe code path parsed from a recipe block's `SCRIPT: <path>` line; "" if none."""
    m = re.search(r"SCRIPT:\s*(\S+)", block)
    return m.group(1) if m else ""

def _is_recipe(block: str) -> bool:
    """True if a block is a recipe (<!--r:), False if a pitfall (<!--p:)."""
    return block.lstrip().startswith("<!--r:")

def _append_or_bump(path: str, marker: str, block: str) -> None:
    """Idempotent write: if an entry with this marker (<!--p:HASH / <!--r:HASH) already
    exists in the page, increment its seen: count in place; otherwise append the new
    block. This is how re-encountering the same lesson/recipe reinforces it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = _read(path)
    if marker in text:                                   # idempotent: bump seen
        old = next(b for b in _BLOCK_RE.findall(text) if marker in b)
        bumped = re.sub(r"\bseen:(\d+)", lambda m: f"seen:{int(m.group(1)) + 1}", old, count=1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, bumped))
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(("" if not text or text.endswith("\n") else "\n") + block + "\n")

def _write_blocks(path: str, blocks: List[str]) -> None:
    """Overwrite a page with exactly this list of blocks (used to rewrite a page after a
    removal or a CORE promotion/demotion)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks) + ("\n" if blocks else ""))

def _move_blocks(src: str, dst: str, hashes: set) -> None:
    """Move the blocks with the given hashes from src into dst (promotion/demotion)."""
    blocks = _blocks(src)
    move = [b for b in blocks if _hash_of(b) in hashes]
    if not move:
        return
    keep = [b for b in blocks if _hash_of(b) not in hashes]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    dtext = _read(dst)
    with open(dst, "a", encoding="utf-8") as f:
        f.write(("" if not dtext or dtext.endswith("\n") else "\n") + "\n".join(move) + "\n")
    _write_blocks(src, keep)

def _log(language: str, kind: str, etype: str, h: str, summary: str) -> None:
    """Append one audit line to log.md: `ts | language | kind | etype | hash | summary`.
    Records adds, lint dispatches, dedup removals, and CORE rebalances so the whole
    lifecycle is observable."""
    os.makedirs(ROOT, exist_ok=True)
    ts = datetime.datetime.utcnow().isoformat(timespec="seconds")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {language} | {kind} | {etype} | {h} | {summary[:100]}\n")

def _bump_runcount() -> int:
    """Persisted, restart-proof count of Librarian dispatches. Lives on the writable
    data mount so 'every Nth run' is a true cumulative count, not reset on reboot."""
    with _LOCK:
        try:
            n = int(_read(_RUNCOUNT_PATH).strip() or "0")
        except ValueError:
            n = 0
        n += 1
        os.makedirs(ROOT, exist_ok=True)
        with open(_RUNCOUNT_PATH, "w", encoding="utf-8") as f:
            f.write(str(n))
    return n

def _lint_cursor(language: str) -> int:
    """Read the persisted per-language position of the full-lint rotating sweep (0 if
    unset). Lets successive full-lint passes cover the whole library over time."""
    import json
    try:
        return int(json.loads(_read(_LINTCURSOR_PATH) or "{}").get(language, 0))
    except Exception:
        return 0

def _set_lint_cursor(language: str, value: int) -> None:
    """Persist the full-lint sweep position for a language (advanced after each full pass)."""
    import json
    with _LOCK:
        try:
            d = json.loads(_read(_LINTCURSOR_PATH) or "{}")
        except Exception:
            d = {}
        d[language] = value
        os.makedirs(ROOT, exist_ok=True)
        with open(_LINTCURSOR_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(d))

def _safe_name(name: str) -> str:
    """Turn a recipe name into a filesystem-safe stem (lowercase, alnum+underscore, ≤50
    chars) for its code file under recipes/code/."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "recipe").strip()).strip("_").lower()
    return s[:50] or "recipe"

def _recipe_exists(language: str, chash: str) -> bool:
    """True if a recipe with this exact code (content hash) is already stored for the
    language (in either the CORE or regular page) — the exact-duplicate guard."""
    tag = f"chash:{chash}"
    return tag in _read(_core_recipe_page(language)) or tag in _read(_recipe_page(language))


# --------------------------------------------------------------------------- #
# CAPTURE — the debugger/analyst buffers the error->fix lesson here; on_success
# hands it (plus the verified recipe) to the background Librarian.
# --------------------------------------------------------------------------- #
def register_pending_lesson(script_path: str, *, language: str, rule: str,
                            failed_code: str = "", working_code: str = "",
                            error_type: str = "Logic", class_involved: str = "") -> None:
    """Buffer a debugger/analyst error->fix lesson, keyed by the script it fixed. The
    debugger cannot verify its own fix, so it does NOT save directly; it registers the
    lesson here and on_success commits it (via the Librarian) once execute_script confirms
    the rerun is green. No-op if there's no script path or empty rule."""
    if not script_path or not (rule or "").strip():
        return
    _PENDING[os.path.abspath(script_path)] = {
        "language": language or "Groovy", "rule": rule.strip(),
        "working_code": working_code or "", "error_type": error_type or "Logic",
        "class_involved": class_involved or "",
    }

def _run_succeeded(out: str) -> bool:
    """Whether an execute_script output represents a verified-green run (SUCCESS/WARNING
    and no ERROR) — the gate before anything is learned."""
    if not out or "STATUS: ERROR" in out:
        return False
    return ("STATUS: SUCCESS" in out or "STATUS: WARNING" in out
            or out.lstrip().startswith("SUCCESS:"))


# --------------------------------------------------------------------------- #
# RETRIEVE — CORE floor (always injected, fixed size) + recall (+ gated fallback)
# --------------------------------------------------------------------------- #
def core_pitfalls(language: str = "Groovy") -> str:
    """The always-injected CORE pitfalls for this language (read from CORE.<lang>.md)."""
    core = sorted(_blocks(_core_pitfall_page(language)), key=_seen, reverse=True)
    if not core:
        return ""
    body = "\n".join(_body(b) for b in core[:CORE_MAX])
    return ("KNOWN PITFALLS (verified lessons from past failures — apply "
            "unconditionally where the same class/call appears):\n" + body)

def core_recipes(language: str = "Groovy") -> str:
    """The featured recipes for this language (lean catalogue from recipes/CORE.<lang>.md)."""
    core = sorted(_blocks(_core_recipe_page(language)), key=_seen, reverse=True)
    if not core:
        return ""
    body = "\n".join(_body(b) for b in core[:CORE_RECIPE_MAX])
    return ("FEATURED RECIPES (verified reusable scripts — read a SCRIPT path for "
            "the code, then ADAPT it, do not copy verbatim):\n" + body)

def _scored(query_tokens: set, blocks: List[str]) -> List[str]:
    """Rank by IDF-weighted token overlap (a BM25-lite): a matched token is worth
    log(1 + N/df), so RARE/distinctive terms dominate and common ones (image, save,
    channel) stop crowding results as the library grows — preserving specificity at
    scale. seen breaks ties. Matches body tokens + Librarian keyword aliases."""
    toks = [_match_tokens(b) for b in blocks]
    n = len(blocks)
    df = {}
    for ts in toks:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    rows = []
    for b, ts in zip(blocks, toks):
        common = query_tokens & ts
        if not common:
            continue
        score = sum(math.log(1 + n / (1 + df.get(t, 0))) for t in common)
        rows.append((score, _seen(b), _body(b)))
    rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [body for _, _, body in rows]

def _scored_recipes(query_tokens: set, blocks: List[str]):
    """Like _scored, but for recipes: also flag STRONG matches. `cover` is the fraction
    of the query's tokens the recipe covers — high cover means the recipe does the SAME
    operation the task describes, so it should be REUSED VERBATIM (only inputs swapped)
    rather than rewritten (rewriting a known-good script reintroduces bugs it solved).
    Returns [(body, is_strong), ...] ordered by IDF score."""
    toks = [_match_tokens(b) for b in blocks]
    n = len(blocks)
    df = {}
    for ts in toks:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    rows = []
    for b, ts in zip(blocks, toks):
        common = query_tokens & ts
        if not common:
            continue
        score = sum(math.log(1 + n / (1 + df.get(t, 0))) for t in common)
        cover = len(common) / max(1, len(query_tokens))
        strong = cover >= RECIPE_STRONG_COVER and len(common) >= 2
        rows.append((score, _seen(b), _body(b), strong))
    rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [(body, strong) for _, _, body, strong in rows]

@tool("recall")
def recall(query: str, language: str = "Groovy") -> str:
    """Pull verified lessons and reusable recipes relevant to the work at hand.

    Call this BEFORE writing or fixing a script: pass the TASK description (coder /
    analyst) or the ERROR / stack-trace (debugger). Returns relevant pitfalls beyond
    the CORE ones already in your context, plus recipes. A recipe tagged [STRONG MATCH]
    does the SAME operation as your task — read its SCRIPT and reuse it VERBATIM (swap
    only inputs); a merely related recipe is a template to adapt. Empty when nothing
    matches.
    """
    # The model does not always honour the `str` annotation — it may send a list of
    # keywords. LangChain passes that straight through, so every downstream regex
    # then raises TypeError and takes the agent turn down with it. Coerce instead.
    if not isinstance(query, str):
        query = " ".join(str(q) for q in query) if isinstance(query, (list, tuple)) else str(query)
    if not isinstance(language, str):
        language = str(language)

    want = _tokens(query)
    if not want:
        return ""
    out = []
    pit = _scored(want, _blocks(_pitfall_page(language)))
    if pit:
        out.append("RELEVANT PITFALLS (apply where the same call appears):\n"
                   + "\n".join(pit[:RECALL_K]))
    rec_core = _scored_recipes(want, _blocks(_core_recipe_page(language)))
    core_bodies = {b for b, _ in rec_core}
    rec_reg = [(b, s) for (b, s) in _scored_recipes(want, _blocks(_recipe_page(language)))
               if b not in core_bodies]
    rec = rec_core + rec_reg
    if rec:
        lines = []
        for body, strong in rec[:3]:
            if strong:
                lines.append(
                    "[STRONG MATCH — this recipe does the SAME operation as your task. "
                    "Read its SCRIPT and REUSE IT VERBATIM: copy the script and change "
                    "ONLY concrete input/output paths and task-specified parameters. Do "
                    "NOT restructure, rename, or 'improve' it.]\n" + body)
            else:
                lines.append(body)
        out.append("AVAILABLE RECIPES (featured first — read the SCRIPT path for the "
                   "code. Reuse a STRONG MATCH verbatim; adapt a merely related one "
                   "as a template):\n" + "\n".join(lines))
    if out:
        return "\n\n".join(out)
    return _deep_recall(query, want, language) if DEEP_RECALL else ""

def _loose(a: str, b: str) -> bool:
    """Fuzzy token match (shared 4-char prefix or substring), used only to GATE the LLM
    fallback: it decides whether any stored entry is 'near enough' to be worth an LLM
    check, so no LLM call is made when nothing is even lexically close."""
    return len(a) >= 4 and len(b) >= 4 and (a[:4] == b[:4] or a in b or b in a)

def _message_text(content) -> str:
    """Normalize a LangChain message's `.content` to plain text.

    `.content` is NOT always a str. Reasoning models on the Responses API (this
    curator runs on gpt-5.4-mini there) return a LIST of content blocks, e.g.
    [{"type": "text", "text": "NONE"}]. Feeding that straight to `re.split` raises
    `TypeError: expected string or bytes-like object, got 'list'`, which escapes the
    recall tool and ends the whole agent turn — observed killing a run mid-task.

    A twin of this lives in imagej_tools._message_text; it is duplicated rather than
    imported because that module pulls in imagej_context, which configures and starts
    the JVM at import time — far too heavy for the learned-memory path.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content or "")


def _deep_recall(query: str, want: set, language: str, cap: int = 8) -> str:
    """Gated LLM fallback for recall: only runs when exact scoring found nothing AND a
    lexically-near candidate exists (_loose). Shows the curator LLM the near candidates
    and asks which genuinely apply, returning those. Returns "" if nothing is near or no
    LLM is configured — so the common path stays LLM-free."""
    candidates = []
    for page in (_pitfall_page(language), _recipe_page(language)):
        for b in _blocks(page):
            if any(_loose(w, t) for w in want for t in _match_tokens(b)):
                candidates.append(b)
    for b in _blocks(_core_recipe_page(language)):
        if any(_loose(w, t) for w in want for t in _match_tokens(b)):
            candidates.append(b)
    if not candidates:                      # gate: nothing near -> no LLM call
        return ""
    llm = _get_curator_llm()
    if llm is None:
        return ""
    candidates = candidates[:cap]
    listing = "\n".join(f"[{_hash_of(b)}] {_body(b)}" for b in candidates)
    try:
        ans = llm.invoke(
            "A coding task/error and some candidate lessons (each tagged [HASH]) are "
            "given. Return ONLY the comma-separated HASHes of the lessons that "
            "genuinely apply, or NONE.\n\n"
            f"TASK/ERROR: {query}\n\nCANDIDATES:\n{listing}").content
    except Exception:
        return ""
    picked = {h.strip() for h in re.split(r"[,\s]+", _message_text(ans)) if h.strip()}
    hits = [_body(b) for b in candidates if _hash_of(b) in picked]
    return ("RELEVANT (semantic match — adapt as needed):\n" + "\n".join(hits[:RECALL_K])) if hits else ""

_CURATOR_LLM = None
def _get_curator_llm():
    """Lazily fetch the shared curator LLM (for the gated recall fallback)."""
    global _CURATOR_LLM
    if _CURATOR_LLM is not None:
        return _CURATOR_LLM or None
    try:
        from ..agents import llm_curator
        _CURATOR_LLM = llm_curator
    except Exception:
        _CURATOR_LLM = False
    return _CURATOR_LLM or None


# --------------------------------------------------------------------------- #
# LIBRARIAN TOOLS — the ONLY way the wiki is mutated. The Librarian subagent
# judges; these apply deterministically so the format can never be garbled and a
# bad plan can never lose a bullet outside an explicit remove/merge.
# --------------------------------------------------------------------------- #
def _enforce_core_cap(language: str, kind: str) -> None:
    """Keep a CORE file within its fixed cap by demoting the least-seen entries."""
    core_path = _core_pitfall_page(language) if kind == "pitfall" else _core_recipe_page(language)
    reg_path = _pitfall_page(language) if kind == "pitfall" else _recipe_page(language)
    maxn = CORE_MAX if kind == "pitfall" else CORE_RECIPE_MAX
    core = _blocks(core_path)
    if len(core) <= maxn:
        return
    keep = {_hash_of(b) for b in sorted(core, key=_seen, reverse=True)[:maxn]}
    demote = {_hash_of(b) for b in core} - keep
    _move_blocks(core_path, reg_path, demote)

@tool("library_add_pitfall")
def library_add_pitfall(language: str, rule: str, snippet: str = "",
                        error_type: str = "Logic", class_involved: str = "",
                        core: bool = False, keywords: str = "") -> str:
    """Add a verified error->fix lesson to the wiki. `rule` is one imperative line
    (symptom AND fix); `snippet` is a minimal working fix (optional). `keywords` is a
    comma-separated list of 5-8 SEARCH ALIASES a future task/error would use to find
    this (synonyms, paraphrases, the class/method/error names) — they make recall
    robust to wording. Set core=True ONLY for a broadly-useful, recurring/high-severity
    trap (plugin/environment-specific lessons are forced to the regular library)."""
    rule = (rule or "").strip()
    if not rule:
        return "skipped: empty rule"
    language = language or "Groovy"
    h = _hash(rule)
    scope = "plugin" if _is_plugin(rule, error_type, class_involved) else "general"
    to_core = bool(core) and scope != "plugin"
    block = (f"<!--p:{h} seen:1 lang:{language} type:{error_type or 'Logic'} "
             f"class:{class_involved or ''} scope:{scope} kw:{_norm_kw(keywords)}-->\n- {rule}")
    if snippet:
        block += "\n" + "\n".join("    " + ln for ln in snippet.strip().splitlines())
    target = _core_pitfall_page(language) if to_core else _pitfall_page(language)
    with _LOCK:
        _append_or_bump(target, f"<!--p:{h} ", block)
        if to_core:
            _enforce_core_cap(language, "pitfall")
        _log(language, "pitfall", error_type or "Logic", h, rule)
    return f"added {'CORE ' if to_core else ''}pitfall [{h}] {rule[:60]}"

@tool("library_add_recipe")
def library_add_recipe(language: str, name: str, description: str, inputs: str,
                       source_path: str, core: bool = False, keywords: str = "") -> str:
    """File a VERIFIED, just-run script as a recipe. `source_path` is the path to the
    working script (its code is copied into the store). Write a short reusable `name`,
    a 1-3 sentence `description`, and the `inputs` it expects. `keywords` is a comma-
    separated list of 5-8 SEARCH ALIASES a future, differently-worded task would use to
    find this recipe (synonyms and paraphrases of the operation, the plugins/methods
    involved) — they make recall robust to vocabulary. Set core=True only for a broadly-
    reusable workflow a future, different task could adapt; one-offs go to the regular
    library (core=False) — still saved, just not featured."""
    name = (name or "").strip()
    if not name or not source_path or not os.path.isfile(source_path):
        return "skipped: need a name and an existing source_path"
    language = language or _EXT.get(os.path.splitext(source_path)[1].lower()) or "Groovy"
    try:
        code = open(source_path, encoding="utf-8").read()
    except OSError:
        return "skipped: could not read source_path"
    chash = _hash(code)
    if _recipe_exists(language, chash):
        return f"skipped: duplicate of an existing recipe (chash {chash})"
    ext = ".py" if language == "Python" else ".groovy"
    code_path = os.path.join(RECIPE_CODE_DIR, f"{_safe_name(name)}{ext}")
    try:
        os.makedirs(RECIPE_CODE_DIR, exist_ok=True)
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
    except OSError:
        return "skipped: could not write recipe code"
    h = _hash(name)
    block = (f"<!--r:{h} seen:1 lang:{language} chash:{chash} kw:{_norm_kw(keywords)}-->\n"
             f"- {name}  [inputs: {inputs}]\n  {description}\n  SCRIPT: {code_path}")
    target = _core_recipe_page(language) if core else _recipe_page(language)
    with _LOCK:
        _append_or_bump(target, f"<!--r:{h} ", block)
        if core:
            _enforce_core_cap(language, "recipe")
        _log(language, "recipe", "core" if core else "lib", h, name)
    return f"added {'CORE ' if core else ''}recipe [{h}] {name}"

@tool("library_remove")
def library_remove(entry_hash: str) -> str:
    """Delete an entry by its [HASH] — use to clean up a duplicate or a wrong entry.
    For a recipe, its stored code file is removed too. The kept duplicate is unchanged
    (bump it first with library_add_* if you want its seen count to absorb the dup)."""
    entry_hash = (entry_hash or "").strip()
    if not entry_hash:
        return "skipped: no hash"
    removed = 0
    with _LOCK:
        for d in (PITFALLS_DIR, RECIPES_DIR):
            for fn in (os.listdir(d) if os.path.isdir(d) else []):
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(d, fn)
                blocks = _blocks(path)
                kept = [b for b in blocks if _hash_of(b) != entry_hash]
                if len(kept) == len(blocks):
                    continue
                for b in blocks:
                    if _hash_of(b) == entry_hash and _is_recipe(b) and _script_path_of(b):
                        try:
                            os.remove(_script_path_of(b))
                        except OSError:
                            pass
                _write_blocks(path, kept)
                removed += 1
    if removed:                                       # log dedup removals (a lint action)
        _log("-", "remove", "dedup", entry_hash, f"removed from {removed} file(s)")
    return f"removed [{entry_hash}] from {removed} file(s)" if removed else f"no entry [{entry_hash}]"

@tool("library_set_core")
def library_set_core(language: str, kind: str, core_hashes: str) -> str:
    """Set CORE membership for a language. `kind` is "pitfall" or "recipe";
    `core_hashes` is a comma-separated list of the [HASH]es that should be in CORE.
    This realises BOTH promotion (regular->CORE) and demotion (CORE->regular) in one
    step and enforces the fixed cap (12 pitfalls / 5 recipes per language; least-seen
    dropped if over). Plugin/environment-specific pitfalls are never kept in CORE."""
    kind = "recipe" if "recip" in (kind or "").lower() else "pitfall"
    language = language or "Groovy"
    core_path = _core_pitfall_page(language) if kind == "pitfall" else _core_recipe_page(language)
    reg_path = _pitfall_page(language) if kind == "pitfall" else _recipe_page(language)
    maxn = CORE_MAX if kind == "pitfall" else CORE_RECIPE_MAX
    want = {h.strip() for h in re.split(r"[,\s]+", core_hashes or "") if h.strip()}
    with _LOCK:
        pool = {_hash_of(b): b for b in _blocks(core_path) + _blocks(reg_path)}
        keep = [h for h in want if h in pool]
        if kind == "pitfall":
            keep = [h for h in keep if _scope_of(pool[h]) != "plugin"]
        keep = sorted(keep, key=lambda h: _seen(pool[h]), reverse=True)[:maxn]
        keepset = set(keep)
        _write_blocks(core_path, [pool[h] for h in keep])
        _write_blocks(reg_path, [b for h, b in pool.items() if h not in keepset])
    _log(language, "core", kind, "-", f"set to {len(keep)}: {', '.join(keep) or '(none)'}")
    return f"CORE {kind}s for {language} set to {len(keep)} entr(y/ies): {', '.join(keep) or '(none)'}"


# --------------------------------------------------------------------------- #
# DISPATCH — fire the background Librarian on a verified-green run. Never blocks.
# --------------------------------------------------------------------------- #
def _script_description(directory: str, filename: str) -> str:
    """Best-effort human description of a just-run script, read from the project's
    script_dictionary.json; "" if unavailable. Used as the recipe description hint and
    to seed the similarity ranking of the normal-run snapshot."""
    try:
        import json
        with open(os.path.join(directory, "script_dictionary.json"), encoding="utf-8") as f:
            return (json.load(f).get(filename) or {}).get("description", "")
    except Exception:
        return ""

def on_success(directory: str, filename: str, execute_output: str) -> None:
    """Called by execute_script after EVERY run. On a verified-green run with
    something to learn, fire the background Librarian — the task never waits on it."""
    if not _run_succeeded(execute_output):
        return
    language = _EXT.get(os.path.splitext(filename)[1].lower())
    if not language:
        return
    full = os.path.join(directory, filename)
    pending = _PENDING.pop(os.path.abspath(full), None)
    try:
        code = open(full, encoding="utf-8").read()
    except OSError:
        code = ""
    recipe_ok = bool(code.strip()) and not _recipe_exists(language, _hash(code))
    if not recipe_ok and not pending:
        return                                       # nothing new to learn
    n = _bump_runcount()                             # two-tier lint cadence (bounded context)
    mode = ("full" if n % LINT_FULL_EVERY == 0
            else "recent" if n % LINT_RECENT_EVERY == 0 else None)
    if mode:                                          # make lint passes observable in log.md
        _log(language, "lint", mode, f"n={n}", "dispatch")
    desc = _script_description(directory, filename)
    threading.Thread(target=_librarian_bg, daemon=True,
                     args=(language, full, recipe_ok, desc, pending, mode)).start()

def _snapshot(language: str, cand_tokens: set = None) -> str:
    """Compact, BOUNDED snapshot for the Librarian (never lists the whole library — at
    most `n` lines per section). When `cand_tokens` is given (a normal run filing a new
    entry), regular entries are ranked by SIMILARITY to that new candidate (token
    overlap), so the entries most likely to be its duplicate are the ones shown — not
    just the most-seen. Falls back to most-seen ordering when there is no candidate or
    no overlap, so it degrades gracefully."""
    def one(b):
        # Compact line: pitfall -> the rule; recipe -> name + a SHORT description
        # (enough to spot duplicates without bloating the prompt).
        lines = [ln.strip(" -") for ln in _body(b).splitlines() if ln.strip()]
        head = lines[0] if lines else ""
        if _is_recipe(b):
            name = head.split("  [inputs:")[0].strip()
            desc = next((ln for ln in lines[1:] if not ln.startswith("SCRIPT:")), "")
            head = f"{name} — {desc[:90]}" if desc else name
        return f"  [{_hash_of(b)} seen:{_seen(b)}] {head[:130]}"
    def key(b):
        return (len(cand_tokens & _match_tokens(b)), _seen(b)) if cand_tokens else (_seen(b),)
    def fmt(blocks, n=15):
        return "\n".join(one(b) for b in sorted(blocks, key=key, reverse=True)[:n]) or "  (none)"
    tag = " (most similar to the new candidate first)" if cand_tokens else ""
    return (
        f"LIBRARY SNAPSHOT (language={language})\n"
        f"CORE PITFALLS (cap {CORE_MAX}):\n{fmt(_blocks(_core_pitfall_page(language)))}\n"
        f"REGULAR PITFALLS{tag}:\n{fmt(_blocks(_pitfall_page(language)))}\n"
        f"CORE RECIPES (cap {CORE_RECIPE_MAX}):\n{fmt(_blocks(_core_recipe_page(language)))}\n"
        f"REGULAR RECIPES{tag}:\n{fmt(_blocks(_recipe_page(language)))}"
    )

def _full_line(b) -> str:
    """Full-description line for a lint pass: pitfall -> the FULL rule; recipe ->
    name + FULL description, so the Librarian can judge semantic equivalence."""
    if _is_recipe(b):
        lines = [ln.strip(" -") for ln in _body(b).splitlines()
                 if ln.strip() and not ln.strip().startswith("SCRIPT:")]
        txt = " — ".join(lines[:2])
    else:
        txt = " ".join(ln.strip(" -") for ln in _body(b).splitlines() if ln.strip())
    return f"  [{_hash_of(b)} seen:{_seen(b)}] {txt}"

def _sig(b) -> str:
    """Lexical-similarity signature: near-duplicate entries share most match tokens,
    so sorting by this string clusters them adjacently (so they land in one shard)."""
    return " ".join(sorted(_match_tokens(b)))

def _lint_shard(language: str, mode: str):
    """Pick a BOUNDED (<= LINT_BUDGET) set of regular entries for the Librarian to
    dedup. 'recent' -> the newest entries (append order). 'full' -> the next
    similarity-sorted shard from a persisted, wrapping cursor (full coverage over
    successive passes). Returns (pitfall_blocks, recipe_blocks)."""
    reg_pit = _blocks(_pitfall_page(language))
    reg_rec = _blocks(_recipe_page(language))
    if mode == "recent":
        return reg_pit[-LINT_RECENT_N:], reg_rec[-LINT_RECENT_N:]
    pool = sorted(reg_pit + reg_rec, key=_sig)            # cluster near-dups together
    if not pool:
        return [], []
    cur = _lint_cursor(language) % len(pool)
    take = min(LINT_BUDGET, len(pool))
    shard = [pool[(cur + i) % len(pool)] for i in range(take)]
    _set_lint_cursor(language, (cur + take) % len(pool))
    return ([b for b in shard if not _is_recipe(b)],
            [b for b in shard if _is_recipe(b)])

def _lint_snapshot(language: str, mode: str) -> str:
    """CORE (full, for rebalance) + a bounded shard of the regular library (for dedup)."""
    pit, rec = _lint_shard(language, mode)
    def sect(label, blocks):
        return f"{label}:\n" + ("\n".join(_full_line(b) for b in blocks) or "  (none)")
    scope = "newest entries" if mode == "recent" else "rotating full-coverage shard"
    return "\n".join((
        f"LIBRARY ({language}) — {scope} for dedup; CORE shown in full for rebalance",
        sect(f"CORE PITFALLS (cap {CORE_MAX})", _blocks(_core_pitfall_page(language))),
        sect("REGULAR PITFALLS (this shard)", pit),
        sect(f"CORE RECIPES (cap {CORE_RECIPE_MAX})", _blocks(_core_recipe_page(language))),
        sect("REGULAR RECIPES (this shard)", rec),
    ))

def _librarian_bg(language, full, recipe_ok, desc, pending, mode) -> None:
    """Background worker (runs in the daemon thread on_success spawns). Builds the
    Librarian's prompt — a bounded snapshot (similarity-targeted on a normal run; a
    dedup shard on a lint run) plus the new recipe/pitfall candidate(s) and the
    mode-specific instructions — then invokes librarian_agent, which mutates the wiki
    only through the library_* tools. If that agent is unavailable, falls back to a
    deterministic direct save so a lesson/recipe is never lost. Swallows exceptions:
    this is off the hot path and must never surface to the task."""
    lint = mode in ("recent", "full")
    if lint:
        snapshot = _lint_snapshot(language, mode)
    else:
        # Normal run: rank the (bounded) snapshot by similarity to the NEW candidate,
        # so likely duplicates surface even when the library is huge.
        cand = [desc or ""]
        if recipe_ok:
            try:
                cand.append("\n".join(open(full, encoding="utf-8").read().splitlines()[:18]))
            except OSError:
                pass
        if pending:
            cand += [pending.get("rule", ""), pending.get("class_involved", "")]
        snapshot = _snapshot(language, _tokens(*cand) or None)
    parts = [f"A script just ran GREEN (verified). Maintain the {language} learned-memory "
             f"wiki, following the learned_memory skill. Act ONLY through the library_* "
             f"tools.", "", snapshot, ""]
    if recipe_ok:
        head = "\n".join(open(full, encoding="utf-8").read().splitlines()[:18])
        parts += [f"NEW RECIPE CANDIDATE (verified working script):\n  source_path: {full}\n"
                  f"  description hint: {desc or '(none)'}\n  first lines:\n{head}", ""]
    if pending:
        snip = "\n".join((pending.get("working_code") or "").splitlines()[:8])
        parts += [f"NEW PITFALL CANDIDATE (the fix that produced this green run):\n"
                  f"  rule: {pending['rule']}\n  error_type: {pending.get('error_type')} "
                  f"class: {pending.get('class_involved')}\n  working snippet:\n{snip}", ""]
    if lint:
        parts.append(
            "DEDUP/REBALANCE RUN. DO: (1) file each NEW candidate above that is genuinely "
            "novel (skip true duplicates), giving it `keywords` (5-8 search aliases). "
            "(2) DEDUP within the shard shown above (it is sorted so similar entries are "
            "adjacent): near-duplicate recipes (same operation/workflow) or pitfalls (same "
            "root cause + fix) -> KEEP the clearest/most-seen one and library_remove the "
            "redundant others, preferring the more robust variant. (3) REBALANCE CORE for "
            "pitfalls and recipes with library_set_core: promote the most broadly-reusable, "
            "high-value entries and demote stale/narrow ones, within the caps. Only act on "
            "entries shown above.")
    else:
        parts.append(
            "DO: file each NEW candidate above that is genuinely novel (skip a true "
            "duplicate of an existing entry), and give it `keywords` — 5-8 search aliases "
            "(synonyms/paraphrases + plugin/class/method names) a future, differently-"
            "worded task would use to find it. Do NOT audit/remove existing entries or "
            "rebalance CORE this run; only set core=True when a new entry is clearly, "
            "broadly reusable.")
    try:
        from ..agents import librarian_agent
    except Exception:
        librarian_agent = None
    if librarian_agent is None:                      # resilient fallback: never lose data
        if recipe_ok:
            library_add_recipe.invoke({"language": language, "name": (desc or "recipe")[:60],
                                       "description": desc or "", "inputs": "",
                                       "source_path": full, "core": False})
        if pending:
            library_add_pitfall.invoke({"language": language, "rule": pending["rule"],
                                        "snippet": pending.get("working_code", ""),
                                        "error_type": pending.get("error_type", "Logic"),
                                        "class_involved": pending.get("class_involved", "")})
        return
    try:
        librarian_agent.invoke({"messages": [{"role": "user", "content": "\n".join(parts)}]})
    except Exception:
        pass
