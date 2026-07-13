"""RAG retrieval over the static documentation collection (BioimageAnalysisDocs).

The agent's *learning* memory — verified pitfalls and reusable recipes — now lives
in `learned_memory.py` (a file-based, shareable markdown wiki). This module is the
read-only documentation retriever only.
"""
import os

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .vector_stores import is_rag_available

__all__ = ["rag_retrieve_docs"]

openrouter_key = os.getenv("OPEN_ROUTER_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")
if openrouter_key:
    _api_key, _base_url, _model = openrouter_key, "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"
elif openai_key:
    _api_key, _base_url, _model = openai_key, None, "gpt-4o-mini"
else:
    _api_key, _base_url, _model = None, None, "gpt-4o-mini"


def get_expanded_queries(query: str) -> list[str]:
    """Generate 3-4 query variations to improve documentation recall."""
    if _api_key is None:
        return [query]
    from ..agents import shared_tracker
    llm = ChatOpenAI(model=_model, api_key=_api_key, base_url=_base_url,
                     temperature=0., callbacks=[shared_tracker])
    prompt = ChatPromptTemplate.from_template(
        "You are an ImageJ/Fiji expert. Generate 3 search query variations for: {question}\n"
        "Focus on technical API terms, alternative function names, and common library methods.\n"
        "Output only the queries, one per line."
    )
    variants = (prompt | llm | StrOutputParser()).invoke({"question": query}).strip().split("\n")
    return list(set([query] + [v.strip("- ").strip() for v in variants]))


@tool("rag_retrieve")
def rag_retrieve_docs(query: str) -> list:
    """Retrieve relevant context from the documentation RAG (hybrid search + query expansion)."""
    if not is_rag_available():
        return [{"content": "RAG system is not configured. No documents available.",
                 "source": None, "score": 0}]
    from ..rag.RAG import hybrid_search_with_rrf, apply_rrf, DOCS_COLLECTION_NAME
    ranked_lists = [
        hybrid_search_with_rrf(q, collection_name=DOCS_COLLECTION_NAME, limit=5)
        for q in get_expanded_queries(query)
    ]
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
