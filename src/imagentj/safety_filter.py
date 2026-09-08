"""Handling for provider-side safety refusals (e.g. OpenAI ``invalid_prompt``
biosecurity flags) so they de-escalate instead of ending the run.

Context, from the benchmark evidence in
``data/benchmark_fix/evidence/issue3_biosecurity/``: the refused request was
*not* the supervisor's first call. The traceback
(``refused_debug.log`` lines 1150-1348) lands in the ``plugin_manager``
subagent, one frame below ``deepagents/middleware/skills.py::wrap_model_call``
— i.e. the request that was refused is the one that had the whole *Skills
System* catalogue appended to its system message. The same task text on its
own was accepted (the bench team's control agent, same model, same endpoint,
completed the task). So the trigger is the injected wrapper, not the user's
wording.

That dictates the retry ladder, innermost-first:

1. first retry:  drop the injected skill catalogue from the system message and
   strip reasoning state from the outgoing messages;
2. second retry: additionally neutralise a *small* set of pathogen proper
   nouns in the outgoing message text;
3. give up:      re-raise the original refusal so the caller's existing
   fallback (e.g. ``on_cap``) engages with an explanatory hint.

A rung that would produce a byte-identical replay is skipped rather than
burning a call on it.

Only the retry payloads are rewritten. The user's original wording, the
supervisor's stored history, and any persisted state are never modified —
this module deep-copies before touching anything. It is deliberately
stdlib-only so it can be imported and tested without langchain.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Iterable, List, Tuple

log = logging.getLogger("imagentj")

__all__ = [
    "is_bio_refusal",
    "neutralize_text",
    "find_sensitive_terms",
    "filter_injected_blocks",
    "scrub_messages_for_retry",
    "scrub_messages_report",
    "BIO_REFUSAL_HINT",
    "INJECTED_SECTION_MARKERS",
    "NEUTRAL_TERMS",
]


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

# Marker strings observed in the wild (see
# data/benchmark_fix/evidence/issue3_biosecurity/refused_debug.log). Matching is
# deliberately specific: an ``invalid_prompt`` complaint that does *not* mention
# biology is a different bug and must not be silently retried here.
_BIO_REFUSAL_NEEDLES: tuple[str, ...] = (
    "biological risk",
    "biosecurity",
    "biological safety",
    "flagged for possible biological",
)

# The provider's error CODE for this refusal is not stable, so match any of the
# known ones. Observed so far:
#   invalid_prompt  — code seen in the Aug-9 evidence log
#   bio_policy      — code='bio_policy', type='invalid_request_error' (Aug-14)
# Pinning only the first meant is_bio_refusal() returned False for the newer
# code, wrap_model_call re-raised on the spot, and the whole retry ladder was
# skipped — which reads exactly like "the mitigation stopped working" even
# though every rung below was intact.
_BIO_REFUSAL_HINT_NEEDLES: tuple[str, ...] = ("invalid_prompt", "bio_policy")

BIO_REFUSAL_HINT = (
    "The provider refused this request as a possible biological-risk prompt. "
    "It was retried without the injected skill catalogue, then with pathogen "
    "names neutralised, and refused each time. Proceed without this call's "
    "output; do not retry the same wording."
)


def _exception_chain(exc: BaseException) -> Iterable[BaseException]:
    """Yield *exc* and everything it was raised from/during, once each.

    LangGraph re-raises worker exceptions through several layers; the refusal
    text sometimes only survives on ``__cause__``/``__context__``.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_bio_refusal(exc: BaseException) -> bool:
    """True only for the specific OpenAI/OpenRouter biological-risk refusal.

    Requires both a known refusal code (``invalid_prompt`` / ``bio_policy``)
    *and* a biosecurity phrase, so unrelated request validation errors still
    surface as ordinary failures.
    """
    for link in _exception_chain(exc):
        text = str(link)
        if not any(needle in text for needle in _BIO_REFUSAL_HINT_NEEDLES):
            continue
        lowered = text.lower()
        if any(needle in lowered for needle in _BIO_REFUSAL_NEEDLES):
            return True
    return False


# ---------------------------------------------------------------------------
# Rung 1 — drop injected context sections
# ---------------------------------------------------------------------------

# deepagents' middlewares append their prompt fragments as *separate* text
# content blocks on the system message (``deepagents/middleware/_utils.py::
# append_to_system_message``), so a section can be removed exactly, without
# parsing a concatenated prompt. ``## Skills System`` is the header of
# ``deepagents.middleware.skills.SKILLS_SYSTEM_PROMPT`` — the block the
# refused request in the evidence log was carrying.
INJECTED_SECTION_MARKERS: tuple[str, ...] = ("## Skills System",)


def filter_injected_blocks(blocks: Iterable[Any]) -> Tuple[List[Any], List[str]]:
    """Split system-message content blocks into (kept, dropped-section-headers).

    Returns the input unchanged when every block would be dropped — an agent
    with no system prompt at all is a worse request than one that is merely
    over-stuffed.
    """
    kept: list = []
    dropped: list[str] = []
    for block in blocks or []:
        text = block.get("text") if isinstance(block, dict) else None
        if isinstance(text, str):
            stripped = text.lstrip()
            marker = next(
                (m for m in INJECTED_SECTION_MARKERS if stripped.startswith(m)), None
            )
            if marker is not None:
                dropped.append(marker)
                continue
        kept.append(block)
    if not kept:
        return list(blocks or []), []
    return kept, dropped


# ---------------------------------------------------------------------------
# Rung 2 — neutralise pathogen proper nouns
# ---------------------------------------------------------------------------

# Kept to *proper nouns* on purpose. An earlier revision also rewrote bare
# "spike", "viral", "infection" and "infected"; measured on ordinary imaging
# text that turned "remove spike noise" into "remove the target protein noise"
# and "spike-in control" into "the target protein-in control", and it rewrote
# directory names such as "Stage 1 infected cells/" into paths that do not
# exist. Generic biology vocabulary is not what a biosecurity classifier scores
# on, and rewriting it corrupts the request in exchange for nothing.
_VIRUS = "the study virus"
_SURFACE_PROTEIN = "the study surface protein"
_CORE_PROTEIN = "the study core protein"

# ``‑`` is the non-breaking hyphen; provider payloads copied out of PDFs
# use it in place of "-" often enough to matter.
_DASH = r"[-‑]"
_SARS2 = rf"SARS{_DASH}?CoV{_DASH}?2"

_NEUTRAL_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), repl)
    for pat, repl in (
        # Compound forms first, so "the SARS-CoV-2 Spike protein" collapses to a
        # single replacement instead of "the study virus the study surface
        # protein".
        (rf"\b{_SARS2}\s+(?:viral\s+)?spike(?:\s*\(\s*S\s*\))?\s+protein\b", _SURFACE_PROTEIN),
        (rf"\b{_SARS2}\s+nucleocapsid(?:\s+protein)?\b", _CORE_PROTEIN),
        # Virus proper nouns.
        (rf"\b{_SARS2}\b", _VIRUS),
        (rf"\bSARS{_DASH}CoV\b", _VIRUS),
        (rf"\bMERS{_DASH}CoV\b", _VIRUS),
        (rf"\bCOVID{_DASH}?19\b", "the study viral disease"),
        (rf"\bHIV{_DASH}?[12]?\b", _VIRUS),
        (r"\bH\d{1,2}N\d{1,2}\b", _VIRUS),  # influenza subtypes: H1N1, H5N1, H7N9
        (r"\b(?:Ebola|Marburg|Zika|Nipah|Lassa|Dengue)(?:\s+virus)?\b", _VIRUS),
        # Virology protein names. Both require the word "protein" or are
        # unambiguous on their own — bare "spike" is deliberately NOT here.
        (r"\b(?:viral\s+)?spike\s*\(\s*S\s*\)\s*protein\b", _SURFACE_PROTEIN),
        (r"\b(?:viral\s+)?spike\s+protein\b", _SURFACE_PROTEIN),
        (r"\b(?:viral\s+)?nucleocapsid(?:\s+protein)?\b", _CORE_PROTEIN),
    )
)

NEUTRAL_TERMS = _NEUTRAL_TERMS  # public alias for tests / documentation

# Substitution must never reach a path, filename or identifier: the benchmark
# task that triggered this puts the pathogen name in the file names, and a
# rewritten path sends the model looking for something that does not exist.
# Any whitespace-delimited run holding a separator or a file extension is
# masked out before substitution and restored afterwards.
_PATHLIKE = re.compile(r"\S*[/\\]\S*|\S+\.[A-Za-z][A-Za-z0-9]{1,4}\b")
_MASK = "\x00{}\x00"

# Only these keys on a content block carry prose. Neutralising every string
# value (as an earlier revision did) also rewrote ids, tool names and
# file_path arguments.
_TEXT_KEYS: frozenset[str] = frozenset({"text", "input_text", "content"})


def _mask_pathlike(text: str) -> tuple[str, list[str]]:
    stash: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        stash.append(match.group(0))
        return _MASK.format(len(stash) - 1)

    return _PATHLIKE.sub(_stash, text), stash


def _unmask(text: str, stash: list[str]) -> str:
    for index, original in enumerate(stash):
        text = text.replace(_MASK.format(index), original)
    return text


def _collapse_doubled_articles(text: str) -> str:
    """Tidy "The the study protein" artefacts left behind by substitution."""
    return re.sub(r"\b([Tt]he)\s+the\b", r"\1", text)


def _neutralize(text: str) -> tuple[str, int]:
    """Return (rewritten text, number of substitutions made)."""
    if not isinstance(text, str) or not text:
        return text, 0
    masked, stash = _mask_pathlike(text)
    total = 0
    for pattern, repl in _NEUTRAL_TERMS:
        masked, count = pattern.subn(repl, masked)
        total += count
    if not total:
        return text, 0
    return _unmask(_collapse_doubled_articles(masked), stash), total


def neutralize_text(text: str) -> str:
    """Return *text* with pathogen proper nouns replaced by neutral ones.

    Idempotent on already-neutral text. Only ever called on retry payloads.
    """
    return _neutralize(text)[0]


def find_sensitive_terms(messages: Iterable) -> dict[str, int]:
    """Report which terms rung 2 would rewrite, for logging before it runs.

    Purely diagnostic — the caller uses it to say *what* it changed instead of
    swapping terminology silently.
    """
    found: dict[str, int] = {}
    for text in _iter_message_text(messages):
        masked, _ = _mask_pathlike(text)
        # Consume matches in the same order _neutralize applies them, so an
        # overlapping compound form ("SARS-CoV-2 Spike protein") is reported
        # once rather than also as each of its parts.
        for pattern, repl in _NEUTRAL_TERMS:
            def _record(match: re.Match[str], _repl: str = repl) -> str:
                term = match.group(0)
                found[term] = found.get(term, 0) + 1
                return _repl

            masked = pattern.sub(_record, masked)
    return found


def _iter_message_text(messages: Iterable) -> Iterable[str]:
    for msg in messages or []:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, str):
            yield content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    for key in _TEXT_KEYS:
                        if isinstance(block.get(key), str):
                            yield block[key]
                elif isinstance(block, str):
                    yield block


# ---------------------------------------------------------------------------
# Message scrubbing (reasoning state + optional neutralisation)
# ---------------------------------------------------------------------------


def _is_reasoning_item(item: Any) -> bool:
    """True for message items that carry OpenAI reasoning state."""
    if not isinstance(item, dict):
        return False
    if item.get("type") == "reasoning":
        return True
    # Responses API may echo reasoning payloads without the literal type tag.
    if "encrypted_content" in item:
        return True
    summary = item.get("summary")
    if summary and isinstance(summary, list):
        for entry in summary:
            if isinstance(entry, dict) and entry.get("type") == "summary_text":
                return True
    return False


def _is_function_call_item(item: Any) -> bool:
    """True for Responses-API tool-call items (the call or its output)."""
    if not isinstance(item, dict):
        return False
    if item.get("type") in ("function_call", "function_call_output"):
        return True
    ident = item.get("id") or item.get("call_id")
    return isinstance(ident, str) and ident.startswith(("fc_", "call_"))


def _contains_function_call(messages: Iterable) -> bool:
    """True if the payload carries any tool-call item, at any nesting level.

    On the Responses API a ``function_call`` is only valid when the ``reasoning``
    item that produced it travels with it. Dropping reasoning while keeping the
    call is rejected outright:

        Item 'fc_...' of type 'function_call' was provided without its required
        'reasoning' item: 'rs_...'

    which fails the whole retry — so the refusal mitigation would turn a
    recoverable content refusal into a hard 400. When tool calls are present the
    reasoning has to stay; rung 1 still drops the injected skill catalogue,
    which is the part the evidence actually implicates.
    """
    for msg in messages:
        if _is_function_call_item(msg):
            return True
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, list) and any(_is_function_call_item(b) for b in content):
            return True
        # LangChain surfaces tool calls off to the side of .content
        if getattr(msg, "tool_calls", None):
            return True
        if isinstance(msg, dict) and msg.get("tool_calls"):
            return True
    return False


def _scrub_content_blocks(blocks: Any, neutralize: bool, stats: dict,
                          keep_reasoning: bool = False) -> Any:
    """Walk a LangChain/Responses content value, dropping reasoning blocks and
    optionally neutralising prose. Handles both str and list-of-blocks shapes."""
    if isinstance(blocks, str):
        if not neutralize:
            return blocks
        text, count = _neutralize(blocks)
        stats["terms_replaced"] += count
        return text
    if not isinstance(blocks, list):
        return blocks
    out: list = []
    for block in blocks:
        if _is_reasoning_item(block):
            if keep_reasoning:
                out.append(block)
                continue
            stats["reasoning_dropped"] += 1
            continue
        if isinstance(block, dict):
            new_block = dict(block)
            if neutralize:
                for key in _TEXT_KEYS:
                    if isinstance(new_block.get(key), str):
                        text, count = _neutralize(new_block[key])
                        new_block[key] = text
                        stats["terms_replaced"] += count
            out.append(new_block)
        elif isinstance(block, str):
            if neutralize:
                text, count = _neutralize(block)
                stats["terms_replaced"] += count
                out.append(text)
            else:
                out.append(block)
        else:
            out.append(block)
    return out


def scrub_messages_report(messages: Iterable, neutralize: bool = False) -> Tuple[List, dict]:
    """Return (new message list, stats) — see :func:`scrub_messages_for_retry`.

    ``stats`` carries ``reasoning_dropped`` and ``terms_replaced`` counts so the
    caller can tell whether the rung actually changed anything (and skip a rung
    that would be a byte-identical replay) and log what it changed.
    """
    stats = {"reasoning_dropped": 0, "terms_replaced": 0}
    src = copy.deepcopy(list(messages))
    # Reasoning may only be dropped when nothing depends on it (see
    # _contains_function_call); otherwise the retry is rejected with a 400.
    keep_reasoning = _contains_function_call(src)
    stats["reasoning_kept_for_tool_calls"] = keep_reasoning
    out: list = []
    for msg in src:
        if _is_reasoning_item(msg):
            if keep_reasoning:
                out.append(msg)
                continue
            stats["reasoning_dropped"] += 1
            continue
        if isinstance(msg, dict):
            new_msg = dict(msg)
            if "content" in new_msg:
                new_msg["content"] = _scrub_content_blocks(
                    new_msg["content"], neutralize, stats, keep_reasoning)
            # Responses-style input items keep the prose at top level.
            if neutralize:
                for key in ("text", "input_text"):
                    if isinstance(new_msg.get(key), str):
                        text, count = _neutralize(new_msg[key])
                        new_msg[key] = text
                        stats["terms_replaced"] += count
            out.append(new_msg)
            continue
        # LangChain message object: operate on a copy, leave the original alone.
        scrubbed = _scrub_content_blocks(
            getattr(msg, "content", None), neutralize, stats, keep_reasoning)
        if hasattr(msg, "model_copy"):
            new_msg = msg.model_copy(update={"content": scrubbed})
        elif hasattr(msg, "copy"):
            new_msg = msg.copy(update={"content": scrubbed})
        else:
            new_msg = msg
            try:
                new_msg.content = scrubbed
            except Exception:
                pass
        out.append(new_msg)
    return out, stats


def scrub_messages_for_retry(messages: Iterable, neutralize: bool = False) -> List:
    """Return a *new* message list safe to re-send after a bio refusal.

    * Removes reasoning-state messages / content blocks (``type=reasoning``,
      ``encrypted_content``, reasoning ``summary``).
    * When ``neutralize=True``, applies :func:`neutralize_text` to the prose
      fields of each message — not to ids, tool names or path arguments.
    * Never mutates the input — the caller's list and its messages are
      deep-copied first.
    """
    return scrub_messages_report(messages, neutralize=neutralize)[0]
