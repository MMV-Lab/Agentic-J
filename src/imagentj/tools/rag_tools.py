import os
from langchain.tools import tool
from langchain_core.documents import Document
from .vector_stores import get_vec_store_mistakes, is_rag_available
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


gpt_key = os.getenv("OPENAI_API_KEY")
__all__ = ['rag_retrieve_docs', 'rag_retrieve_mistakes', 'save_coding_experience']


# Initialize a fast model for expansion
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=gpt_key)

def get_expanded_queries(query: str) -> list[str]:
    """Generates 3-4 variations of the query to improve retrieval."""
    prompt = ChatPromptTemplate.from_template(
        "You are an ImageJ/Fiji expert. Generate 3 search query variations for: {question}\n"
        "Focus on technical API terms, alternative function names, and common library methods.\n"
        "Output only the queries, one per line."
    )
    chain = prompt | llm | StrOutputParser()
    variants = chain.invoke({"question": query}).strip().split("\n")
    # Clean and return unique queries including the original
    return list(set([query] + [v.strip("- ").strip() for v in variants]))



@tool("rag_retrieve")
def rag_retrieve_docs(query: str) -> list:
    """
    Retrieve relevant context from the document RAG using Hybrid Search + Query Expansion.
    """
    if not is_rag_available():
       return is_rag_available()

    from ..rag.RAG import hybrid_search_with_rrf, apply_rrf, DOCS_COLLECTION_NAME

    # 1. Expand the query
    queries = get_expanded_queries(query)

    all_points = []
    # 2. Search for each variant
    for q in queries:
        points = hybrid_search_with_rrf(q, collection_name=DOCS_COLLECTION_NAME, limit=5)
        all_points.extend(points)

    # 3. Final RRF re-ranking of all combined results
    final_results = apply_rrf(all_points, k=60)[:8]

    return [
        {
            "content": p.payload.get("page_content"),
            "source": p.payload.get("metadata", {}).get("source"),
            "page": p.payload.get("metadata", {}).get("page"),
            "score": p.score
        }
        for p in final_results
    ]

@tool("rag_retrieve_mistakes")
def rag_retrieve_mistakes(query: str) -> list:
    """
    Retrieve relevant context from coding errors and solutions RAG using Query Expansion.
    """
    if not is_rag_available():
        return [{"content": "RAG system is not configured. No coding experiences available.", "source": None, "score": 0}]

    from ..rag.RAG import hybrid_search_with_rrf, apply_rrf, MISTAKES_COLLECTION_NAME

    queries = get_expanded_queries(query)
    all_points = []

    for q in queries:
        points = hybrid_search_with_rrf(q, collection_name=MISTAKES_COLLECTION_NAME, limit=5)
        all_points.extend(points)

    final_results = apply_rrf(all_points, k=60)[:5]

    return [
        {
            "content": p.payload.get("page_content"),
            "source": p.payload.get("metadata", {}).get("source"),
            "score": p.score
        }
        for p in final_results
    ]


@tool("save_coding_experience")
def save_coding_experience(language: str, error_description: str, failed_code: str, working_code: str, class_involved: str, error_type: str) -> str:
    """
    Saves a successful fix to the persistent Memory RAG.
    Use this after the debugger fixes a script to prevent the error from happening again.

    Args:   

    language: Programming language of the code (e.g., "Groovy", "Python").
    error_description: A brief description of the error encountered.
    failed_code: The original code snippet that caused the error.
    working_code: The corrected code snippet that resolves the error.
    class_involved: The main class or plugin involved in the error (e.g., "ImagePlus", "TrackMate").
    error_type: The type of error (e.g., "MissingMethod", "Logic"), ALWAYS one word.
    """
    vec_store_mistakes = get_vec_store_mistakes()
    if vec_store_mistakes is None:
        return "RAG system is not configured. Experience could not be saved (no vector store available)."

    content = f"""
    LANGUAGE: {language}
    PROBLEM: {error_description}
    FAILED CODE: {failed_code}
    WORKING SOLUTION:
    {working_code}
    CLASS INVOLVED: {class_involved}
    """

    doc = Document(
        page_content=content,
        metadata={
            "language": language,
            "error type": error_type,
            "class": class_involved,
        }
    )

    vec_store_mistakes.add_documents([doc])
    return "Experience saved successfully. I will remember this for future tasks."