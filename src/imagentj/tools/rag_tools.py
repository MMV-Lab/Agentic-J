"""
RAG retrieval and persistence tools for the agent.

Three collections back the agent's "learning" loop:

  docs (BioimageAnalysisDocs):       static reference documentation
  mistakes (codingerrors_and_solutions): symptom → rule pairs from past failures
  recipes (code_recipes):            verified working scripts as adaptable templates

Design notes that motivate the implementation:

  1. The mistake document EMBEDS only the symptom + the one-line rule. Code is
     stored in metadata, not in page_content, so the embedding is dominated by
     the *natural-language symptom* the agent will query with later — not by
     boilerplate Groovy tokens.

  2. Filters (`language`, `error_type`) are honoured at retrieval time so a
     Python pandas lesson is never surfaced for a Groovy ImageJ query.

  3. A score threshold is applied. When nothing clears it, retrieval returns an
     explicit "no relevant prior experience" message instead of low-quality
     top-of-noise results.

  4. Pre-save dedup: if a near-duplicate already exists in the collection, we
     increment a `times_seen` counter on the existing point instead of inserting
     a new one. Prevents memory bloat from repeated fixes.

  5. Recipes are presented to the coder as REFERENCE templates. The retrieval
     wrapper injects an explicit "ADAPT, DON'T COPY" framing so the model
     applies its own reasoning to the new task.
"""
import os
from typing import Optional, List, Dict, Any
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from qdrant_client.http import models as qmodels

from .vector_stores import (
    get_vec_store_mistakes,
    get_vec_store_recipes,
    is_rag_available,
)


__all__ = [
    'rag_retrieve_docs', 'rag_retrieve_mistakes', 'rag_retrieve_recipes',
    'save_coding_experience', 'save_recipe',
    # Internal helpers exposed for testing & for auto-injection wrappers
    '_retrieve_mistakes_raw', '_retrieve_recipes_raw',
    '_save_coding_experience_raw', '_save_recipe_raw',
    '_build_metadata_filter', '_find_dedup_candidate',
]

openrouter_key = os.getenv("OPEN_ROUTER_API_KEY")
openai_key     = os.getenv("OPENAI_API_KEY")

if openrouter_key:
    _api_key  = openrouter_key
    _base_url = "https://openrouter.ai/api/v1"
    _model    = "openai/gpt-4o-mini"
elif openai_key:
    _api_key  = openai_key
    _base_url = None
    _model    = "gpt-4o-mini"
else:
    # Tests / RAG-disabled environments may import this module without keys.
    _api_key = None
    _base_url = None
    _model = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Query expansion — kept for the docs collection only
# ---------------------------------------------------------------------------

def get_expanded_queries(query: str) -> list[str]:
    """Generates 3-4 variations of the query to improve retrieval (docs only)."""
    if _api_key is None:
        return [query]

    from ..agents import shared_tracker

    llm_nano = ChatOpenAI(
        model=_model,
        api_key=_api_key,
        base_url=_base_url,
        temperature=0.,
        verbose=True,
        callbacks=[shared_tracker],
    )

    prompt = ChatPromptTemplate.from_template(
        "You are an ImageJ/Fiji expert. Generate 3 search query variations for: {question}\n"
        "Focus on technical API terms, alternative function names, and common library methods.\n"
        "Output only the queries, one per line."
    )
    chain = prompt | llm_nano | StrOutputParser()
    variants = chain.invoke({"question": query}).strip().split("\n")
    return list(set([query] + [v.strip("- ").strip() for v in variants]))


# ---------------------------------------------------------------------------
# Filter helper
# ---------------------------------------------------------------------------

def _build_metadata_filter(**kwargs) -> Optional[qmodels.Filter]:
    """Build a Qdrant Filter from non-None metadata kwargs.

    Stored documents put their metadata under `metadata.<key>` (LangChain Qdrant
    convention), so the field path is prefixed accordingly.
    """
    must = []
    for key, value in kwargs.items():
        if value is None or value == "":
            continue
        must.append(
            qmodels.FieldCondition(
                key=f"metadata.{key}",
                match=qmodels.MatchValue(value=value),
            )
        )
    if not must:
        return None
    return qmodels.Filter(must=must)


def _find_dedup_candidate(vec_store, collection_name: str, text: str,
                          qfilter: Optional[qmodels.Filter] = None,
                          threshold: float = 0.92,
                          limit: int = 3):
    """Return the top dense-cosine match if it clears `threshold`, else None.

    Dense-only (no RRF, no sparse): the collection is configured with
    `Distance.COSINE`, so the score on each ScoredPoint IS cosine similarity
    in [-1, 1]. RRF scores from `hybrid_search_with_rrf` are rank-derived,
    NOT similarity, and cannot be compared against a cosine threshold.
    """
    from ..rag.RAG import DENSE_VECTOR_NAME

    try:
        dense_vec = vec_store.embeddings.embed_query(text)
        result = vec_store.client.query_points(
            collection_name=collection_name,
            query=dense_vec,
            using=DENSE_VECTOR_NAME,
            query_filter=qfilter,
            limit=limit,
            with_payload=True,
        )
        candidates = result.points
    except Exception:
        return None

    for cand in candidates:
        score = getattr(cand, "score", None)
        if score is not None and score >= threshold:
            return cand
    return None


# ---------------------------------------------------------------------------
# Docs retrieval (uses query expansion + per-query rank RRF)
# ---------------------------------------------------------------------------

@tool("rag_retrieve")
def rag_retrieve_docs(query: str) -> list:
    """
    Retrieve relevant context from the document RAG using Hybrid Search + Query Expansion.
    """
    if not is_rag_available():
        return [{"content": "RAG system is not configured. No documents available.", "source": None, "score": 0}]

    from ..rag.RAG import hybrid_search_with_rrf, apply_rrf, DOCS_COLLECTION_NAME

    queries = get_expanded_queries(query)

    # Per-query ranked lists, fused via RRF (ranks are tracked PER query, not
    # globally — this is the bug fix vs the old implementation).
    ranked_lists = []
    for q in queries:
        points = hybrid_search_with_rrf(q, collection_name=DOCS_COLLECTION_NAME, limit=5)
        ranked_lists.append(points)

    final_results = apply_rrf(ranked_lists, k=60)[:8]

    return [
        {
            "content": p.payload.get("page_content"),
            "source": p.payload.get("metadata", {}).get("source"),
            "page": p.payload.get("metadata", {}).get("page"),
            "score": getattr(p, "score", None),
        }
        for p in final_results
    ]


# ---------------------------------------------------------------------------
# Mistakes — internal helper + tool
# ---------------------------------------------------------------------------

def _format_mistake(point) -> Dict[str, Any]:
    md = point.payload.get("metadata", {}) or {}
    return {
        "rule": point.payload.get("page_content"),  # short, embeddable
        "language": md.get("language"),
        "error_type": md.get("error_type"),
        "class_involved": md.get("class_involved"),
        "failed_code": md.get("failed_code"),
        "working_code": md.get("working_code"),
        "times_seen": md.get("times_seen", 1),
        "score": getattr(point, "score", None),
    }


def _retrieve_mistakes_raw(
    query: str,
    language: Optional[str] = None,
    error_type: Optional[str] = None,
    limit: int = 5,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Plain function (not a langchain @tool) usable from auto-injection paths."""
    if not is_rag_available():
        return []

    from ..rag.RAG import hybrid_search_with_rrf, MISTAKES_COLLECTION_NAME
    from config.rag_config import MIN_MISTAKE_SCORE

    if min_score is None:
        min_score = MIN_MISTAKE_SCORE

    qfilter = _build_metadata_filter(language=language, error_type=error_type)

    # Skip query expansion: the natural query for mistakes IS the symptom (the
    # exception class + offending method name). Expanding into "alternative
    # function names" pushes the query AWAY from what's stored.
    points = hybrid_search_with_rrf(
        query,
        collection_name=MISTAKES_COLLECTION_NAME,
        limit=limit,
        query_filter=qfilter,
    )

    results = []
    for p in points:
        score = getattr(p, "score", None)
        if score is not None and score < min_score:
            continue
        results.append(_format_mistake(p))
    return results


@tool("rag_retrieve_mistakes")
def rag_retrieve_mistakes(query: str,
                          language: Optional[str] = None,
                          error_type: Optional[str] = None) -> list:
    """
    Retrieve relevant past coding mistakes (with their fixes) from the agent's
    memory of prior failures.

    Args:
        query:      The error symptom — paste the actual exception line, the
                    method name, or a short natural-language description of
                    the failure mode. Do NOT paraphrase — the symptom string
                    is what's indexed.
        language:   Optional filter ("Groovy" | "Python"). Strongly recommended
                    so a Python pandas lesson is not returned for a Groovy task.
        error_type: Optional filter (e.g. "MissingMethod", "NullPointer",
                    "ClassCast"). One word, matches what `save_coding_experience`
                    used.

    Returns a list of {rule, failed_code, working_code, language, error_type,
    times_seen, score}. If no entry passes the relevance threshold, returns an
    empty list.
    """
    if not is_rag_available():
        return [{"rule": "RAG system is not configured. No coding experiences available.",
                 "score": 0}]
    return _retrieve_mistakes_raw(query, language=language, error_type=error_type)


def _save_coding_experience_raw(
    language: str,
    rule: str,
    failed_code: str,
    working_code: str,
    error_type: str,
    class_involved: str = "",
) -> str:
    """
    Pre-save dedup: search the mistakes collection for a near-duplicate. If one
    exists, increment its `times_seen` counter instead of inserting a new point.
    Otherwise, insert a fresh symptom-only embedding with code stored in metadata.
    """
    vec_store_mistakes = get_vec_store_mistakes()
    if vec_store_mistakes is None:
        return "RAG system is not configured. Experience could not be saved."

    from ..rag.RAG import MISTAKES_COLLECTION_NAME
    from config.rag_config import DEDUP_SIMILARITY_THRESHOLD

    # Dedup check: dense-only cosine search (NOT hybrid RRF — RRF score is
    # rank-derived and small collections give the only candidate score=1.0
    # regardless of similarity).
    qfilter = _build_metadata_filter(language=language, error_type=error_type)
    cand = _find_dedup_candidate(
        vec_store_mistakes,
        MISTAKES_COLLECTION_NAME,
        rule,
        qfilter=qfilter,
        threshold=DEDUP_SIMILARITY_THRESHOLD,
    )
    if cand is not None:
        existing_md = cand.payload.get("metadata", {}) or {}
        new_md = dict(existing_md)
        new_md["times_seen"] = int(new_md.get("times_seen", 1)) + 1
        vec_store_mistakes.client.set_payload(
            collection_name=MISTAKES_COLLECTION_NAME,
            payload={"metadata": new_md},
            points=[cand.id],
        )
        return (f"Near-duplicate found (cosine={cand.score:.3f}); "
                f"incremented times_seen to {new_md['times_seen']}.")

    # 2. Fresh insert. Embed ONLY the rule (symptom + one-line fix). Code lives
    #    in metadata so it doesn't pollute the embedding.
    doc = Document(
        page_content=rule.strip(),
        metadata={
            "language": language,
            "error_type": error_type,
            "class_involved": class_involved,
            "failed_code": failed_code,
            "working_code": working_code,
            "times_seen": 1,
        },
    )
    vec_store_mistakes.add_documents([doc])
    return "Experience saved. The agent will surface this rule for future similar errors."


@tool("save_coding_experience")
def save_coding_experience(language: str,
                           rule: str,
                           failed_code: str,
                           working_code: str,
                           error_type: str,
                           class_involved: str = "") -> str:
    """
    Record a fix to the persistent mistakes memory. Call this after the
    debugger has produced a working version of a previously-failing script.

    Args:
        language:       "Groovy" or "Python".
        rule:           The lesson, written as a short imperative rule that
                        starts with the symptom. Example:
                          "When ImageCalculator is used without explicit
                          'import ij.plugin.ImageCalculator', a MissingProperty
                          error fires. Always import the class explicitly."
                        Keep it under ~40 words. This is what gets EMBEDDED.
        failed_code:    The original failing snippet (stored, not embedded).
        working_code:   The corrected snippet (stored, not embedded).
        error_type:     One word: "MissingMethod" | "NullPointer" | "ClassCast"
                        | "Import" | "Logic" | "Path" | etc. Used as a filter.
        class_involved: Main class (e.g. "ImagePlus", "TrackMate"). Optional.
    """
    return _save_coding_experience_raw(
        language=language,
        rule=rule,
        failed_code=failed_code,
        working_code=working_code,
        error_type=error_type,
        class_involved=class_involved,
    )


# ---------------------------------------------------------------------------
# Recipes — verified working scripts as adaptable templates
# ---------------------------------------------------------------------------

RECIPE_USAGE_NOTE = (
    "These recipes are REFERENCE TEMPLATES from prior verified work. "
    "They are NOT a solution to the current task. Adapt them: image properties, "
    "channel layouts, plugin versions, and parameters may differ. Reason about "
    "the current task on its own merits, then borrow only the parts that fit."
)


def _format_recipe(point) -> Dict[str, Any]:
    md = point.payload.get("metadata", {}) or {}
    return {
        "name": md.get("name"),
        "description": point.payload.get("page_content"),
        "language": md.get("language"),
        "inputs_required": md.get("inputs_required"),
        "code": md.get("code"),
        "times_seen": md.get("times_seen", 1),
        "score": getattr(point, "score", None),
    }


def _retrieve_recipes_raw(
    task: str,
    language: Optional[str] = None,
    limit: int = 3,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Plain function for auto-injection."""
    if not is_rag_available():
        return []

    from ..rag.RAG import hybrid_search_with_rrf, RECIPES_COLLECTION_NAME
    from config.rag_config import MIN_RECIPE_SCORE

    if min_score is None:
        min_score = MIN_RECIPE_SCORE

    qfilter = _build_metadata_filter(language=language)

    points = hybrid_search_with_rrf(
        task,
        collection_name=RECIPES_COLLECTION_NAME,
        limit=limit,
        query_filter=qfilter,
    )

    out = []
    for p in points:
        score = getattr(p, "score", None)
        if score is not None and score < min_score:
            continue
        out.append(_format_recipe(p))
    return out


@tool("rag_retrieve_recipes")
def rag_retrieve_recipes(task: str, language: Optional[str] = None) -> dict:
    """
    Retrieve verified working scripts that match a task description, as
    REFERENCE templates. The returned recipes are starting points — the agent
    must adapt them to the specific task at hand.

    Args:
        task:     Natural-language description of what the script should do.
                  Match against the recipe `description` and `name` fields.
        language: Optional filter ("Groovy" | "Python").

    Returns: {usage_note, recipes: [...]}.
    """
    if not is_rag_available():
        return {"usage_note": RECIPE_USAGE_NOTE,
                "recipes": [],
                "message": "RAG system is not configured."}

    recipes = _retrieve_recipes_raw(task, language=language)
    return {"usage_note": RECIPE_USAGE_NOTE, "recipes": recipes}


def _save_recipe_raw(
    name: str,
    description: str,
    code: str,
    inputs_required: str,
    language: str = "Groovy",
) -> str:
    """Insert (or dedup-merge) a recipe into the recipes collection."""
    vec_store_recipes = get_vec_store_recipes()
    if vec_store_recipes is None:
        return "RAG system is not configured. Recipe could not be saved."

    from ..rag.RAG import RECIPES_COLLECTION_NAME
    from config.rag_config import DEDUP_SIMILARITY_THRESHOLD

    # Dedup against the description (what's embedded). Dense-only cosine —
    # see _find_dedup_candidate for why hybrid RRF is wrong here.
    qfilter = _build_metadata_filter(language=language)
    # Embed the same string we'd embed on insert (name + description) so the
    # dedup vector matches what's stored, not just the description alone.
    dedup_text = f"{name}\n{description}"
    cand = _find_dedup_candidate(
        vec_store_recipes,
        RECIPES_COLLECTION_NAME,
        dedup_text,
        qfilter=qfilter,
        threshold=DEDUP_SIMILARITY_THRESHOLD,
    )
    if cand is not None:
        existing_md = cand.payload.get("metadata", {}) or {}
        new_md = dict(existing_md)
        new_md["times_seen"] = int(new_md.get("times_seen", 1)) + 1
        vec_store_recipes.client.set_payload(
            collection_name=RECIPES_COLLECTION_NAME,
            payload={"metadata": new_md},
            points=[cand.id],
        )
        return (f"Near-duplicate recipe found (cosine={cand.score:.3f}); "
                f"incremented times_seen to {new_md['times_seen']}.")

    # Embed the description (what coders query with) plus the name. The CODE
    # lives in metadata to keep the embedding semantic-language-dominant.
    page_content = f"{name}\n{description}"
    doc = Document(
        page_content=page_content,
        metadata={
            "name": name,
            "language": language,
            "inputs_required": inputs_required,
            "code": code,
            "times_seen": 1,
        },
    )
    vec_store_recipes.add_documents([doc])
    return "Recipe saved. Future tasks matching this description will see it as a template."


@tool("save_recipe")
def save_recipe(name: str,
                description: str,
                code: str,
                inputs_required: str,
                language: str = "Groovy") -> str:
    """
    Record a verified working script into the recipes memory.

    Use only AFTER `execute_script` has confirmed the script ran cleanly AND
    produced the expected outputs. Do not save partial fixes or
    project-specific one-offs.

    Args:
        name:            Short title (e.g. "Nuclei Segmentation via StarDist").
        description:     1-3 sentence summary of what the script does and when
                         to use it. This is what gets EMBEDDED for retrieval.
        code:            The full working script (stored, not embedded).
        inputs_required: What the user must have ready (e.g. "Open a 2D Tiff
                         image with DAPI channel").
        language:        "Groovy" (default) or "Python".
    """
    return _save_recipe_raw(
        name=name,
        description=description,
        code=code,
        inputs_required=inputs_required,
        language=language,
    )
