"""
Smart document loaders for RAG ingestion.

Each file type gets the chunking strategy that respects its structure:

  PDF   → Docling DocumentConverter → HybridChunker → contextualize()
          Layout-aware, heading-enriched, table-aware. Selective OCR.

  MD    → Docling DocumentConverter (InputFormat.MD) → HybridChunker
          Heading-aware structural chunking instead of blind char splitting.

  TXT   → Read as markdown → Docling → HybridChunker
          Paragraph-aware chunking.

  PY    → Python ast module → split by function/class → prepend context
          Keeps complete functions/classes as units, never cuts mid-function.

  JAVA/GROOVY → Regex structural split by class/method boundaries
          Practical middle-ground without tree-sitter dependency.

  IPYNB → Cell-aware markdown conversion → Docling HybridChunker
          Preserves notebook structure: markdown cells become headings,
          code cells stay in fenced blocks under their narrative context.

  JS/TS → Language-aware RecursiveCharacterTextSplitter (fallback)

NOTE: tiktoken (used for chunk sizing) is LOCAL — no API key needed.
      API keys are only used in rag.py for actual embedding calls via OpenRouter.
"""

import ast
import json
import re
import multiprocessing
import tiktoken

from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.chunking import HybridChunker

from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.serializer.markdown import (
    MarkdownParams,
    MarkdownTableSerializer,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_MAX_TOKENS = 512
TIKTOKEN_MODEL = "text-embedding-3-large"

# For code files: max lines per chunk before we force-split a large function
CODE_MAX_LINES = 80


# ---------------------------------------------------------------------------
# Markdown table serializer for Docling
# ---------------------------------------------------------------------------

class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    """Serialize tables as compact Markdown instead of default triplet notation."""

    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
            params=MarkdownParams(
                compact_tables=True,
                image_placeholder="",
            ),
        )


# ---------------------------------------------------------------------------
# Shared: Tokenizer & Chunker
# ---------------------------------------------------------------------------

def get_hybrid_chunker(max_tokens: int = CHUNK_MAX_TOKENS) -> HybridChunker:
    """
    HybridChunker aligned to text-embedding-3-large tokenizer.
    tiktoken is local — no API key needed.

    The HybridChunker:
      1. Starts from Docling's hierarchical (layout-aware) document structure
      2. Splits oversized chunks respecting token limits
      3. Merges undersized peer chunks that share the same section headings
      4. Repeats table headers in each chunk so every chunk is self-contained
    """
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.encoding_for_model(TIKTOKEN_MODEL),
        max_tokens=max_tokens,
    )
    return HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        repeat_table_header=True,
        serializer_provider=MarkdownTableSerializerProvider(),
    )


# ---------------------------------------------------------------------------
# Shared: Document Converter (multi-format)
# ---------------------------------------------------------------------------

def get_docling_converter() -> DocumentConverter:
    """
    Docling DocumentConverter for PDF, Markdown, and HTML.

    - do_ocr=True:  Selective OCR — only OCRs page regions where native text
                    extraction fails. Negligible overhead on digital PDFs,
                    essential safety net for scanned pages.
    - device='auto': Auto-detects best accelerator (CUDA > MPS > CPU).
                    No need to manually toggle use_gpu.
    """
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True                # Selective OCR — only where needed
    pipeline_options.do_table_structure = True     # Table structure recognition

    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=multiprocessing.cpu_count(),
        device="auto",                            # Auto: CUDA > MPS > CPU
    )

    converter = DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.MD,
            InputFormat.HTML,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend,
            ),
        },
    )
    return converter


# ---------------------------------------------------------------------------
# Helper: Docling → LangChain Documents
# ---------------------------------------------------------------------------

def _docling_chunks_to_langchain(
    chunks: list,
    chunker: HybridChunker,
    source_path: str,
) -> list[Document]:
    """
    Convert Docling chunks to LangChain Documents using contextualize().

    contextualize() prepends section headings/captions to each chunk,
    giving the embedding model structural context. e.g.:
        "User Guide\n3.1 Installation\nRun pip install ..."
    """
    lc_docs = []
    for chunk in chunks:
        enriched_text = chunker.contextualize(chunk=chunk)

        metadata = {"source": source_path}

        if hasattr(chunk, "meta") and chunk.meta is not None:
            meta_dict = chunk.meta.export_json_dict()

            if "headings" in meta_dict:
                metadata["headings"] = meta_dict["headings"]

            if "doc_items" in meta_dict:
                pages = set()
                for item in meta_dict["doc_items"]:
                    for prov in item.get("prov", []):
                        if "page_no" in prov:
                            pages.add(prov["page_no"])
                if pages:
                    metadata["page_numbers"] = sorted(pages)

            metadata["raw_chunk_text"] = chunk.text

        lc_docs.append(Document(page_content=enriched_text, metadata=metadata))

    return lc_docs


# ===================================================================
# 1. PDF — Docling layout-aware + HybridChunker
# ===================================================================

def load_and_chunk_pdf(
    file_path: str,
    converter: DocumentConverter = None,
    chunker: HybridChunker = None,
) -> list[Document]:
    """
    PDF → Docling → HybridChunker → contextualize().

    Replaces: DoclingLoader(DOC_CHUNKS) → RecursiveCharacterTextSplitter
    """
    if converter is None:
        converter = get_docling_converter()
    if chunker is None:
        chunker = get_hybrid_chunker()

    result = converter.convert(source=file_path)
    chunks = list(chunker.chunk(dl_doc=result.document))
    return _docling_chunks_to_langchain(chunks, chunker, file_path)


# ===================================================================
# 2. MARKDOWN — Docling heading-aware + HybridChunker
# ===================================================================

def load_and_chunk_markdown(
    file_path: str,
    converter: DocumentConverter = None,
    chunker: HybridChunker = None,
) -> list[Document]:
    """
    Markdown → Docling (InputFormat.MD) → HybridChunker → contextualize().

    Why better than RecursiveCharacterTextSplitter:
    - Chunks respect heading hierarchy (## Section / ### Subsection)
    - contextualize() prepends the heading trail to each chunk
    - Tables in markdown are properly handled
    - merge_peers combines small consecutive paragraphs under same heading
    """
    if converter is None:
        converter = get_docling_converter()
    if chunker is None:
        chunker = get_hybrid_chunker()

    result = converter.convert(source=file_path)
    chunks = list(chunker.chunk(dl_doc=result.document))
    return _docling_chunks_to_langchain(chunks, chunker, file_path)


# ===================================================================
# 3. PLAIN TEXT — Read as markdown → Docling → HybridChunker
# ===================================================================

def load_and_chunk_text(
    file_path: str,
    converter: DocumentConverter = None,
    chunker: HybridChunker = None,
) -> list[Document]:
    """
    Plain text → read as markdown string → Docling → HybridChunker.

    Docling's convert_string() only supports MD and HTML, so we read the
    .txt file and feed it as markdown. Since plain text has no markdown
    markers, Docling treats paragraphs (double newlines) as sections,
    which HybridChunker can merge/split intelligently.
    """
    if converter is None:
        converter = get_docling_converter()
    if chunker is None:
        chunker = get_hybrid_chunker()

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = converter.convert_string(
        content=content,
        format=InputFormat.MD,
        name=Path(file_path).stem,
    )
    chunks = list(chunker.chunk(dl_doc=result.document))
    return _docling_chunks_to_langchain(chunks, chunker, file_path)


# ===================================================================
# 4. PYTHON CODE — AST-aware chunking
# ===================================================================

def _extract_python_context(source: str) -> str:
    """Extract module docstring + imports as a context header."""
    lines = []
    try:
        tree = ast.parse(source)
        # Module docstring
        docstring = ast.get_docstring(tree)
        if docstring:
            lines.append(f'"""{docstring}"""')

        # Import statements
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                segment = ast.get_source_segment(source, node)
                if segment:
                    lines.append(segment)
    except SyntaxError:
        pass
    return "\n".join(lines)


def _split_python_by_ast(file_path: str) -> list[Document]:
    """
    Split Python file by top-level functions and classes.

    Each chunk contains:
    - A context header: file path + module imports (so the embedding model
      knows what the function depends on)
    - The complete function/class source code

    Large functions exceeding CODE_MAX_LINES are split with
    RecursiveCharacterTextSplitter as a fallback.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    source_lines = source.splitlines(keepends=True)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback: unparseable Python → character-based splitting
        return _fallback_code_split(file_path, source, Language.PYTHON)

    # Build context header
    rel_path = Path(file_path).name
    context = _extract_python_context(source)
    header = f"# File: {rel_path}\n{context}".strip()

    # Collect top-level definitions with their line ranges
    definitions = []
    top_level_nodes = [
        n for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    for node in top_level_nodes:
        start = node.lineno - 1   # 0-indexed
        end = node.end_lineno     # exclusive
        chunk_source = "".join(source_lines[start:end])
        definitions.append((node.name, chunk_source))

    # Collect module-level code that's NOT imports or definitions
    # (e.g., constants, config, if __name__ == "__main__")
    defined_lines = set()
    for node in ast.iter_child_nodes(tree):
        if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Import, ast.ImportFrom)):
                for ln in range(node.lineno - 1, node.end_lineno):
                    defined_lines.add(ln)

    module_code_lines = []
    for i, line in enumerate(source_lines):
        if i not in defined_lines and line.strip():
            module_code_lines.append(line)
    module_code = "".join(module_code_lines).strip()

    documents = []

    # Module-level code chunk (if substantial)
    if module_code and len(module_code.splitlines()) > 3:
        documents.append(Document(
            page_content=f"{header}\n\n# Module-level code\n{module_code}",
            metadata={"source": file_path, "chunk_type": "module_level"},
        ))

    # Function/class chunks
    safety_splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.PYTHON, chunk_size=1200, chunk_overlap=200
    )

    for name, chunk_source in definitions:
        full_chunk = f"{header}\n\n{chunk_source}"

        if len(chunk_source.splitlines()) > CODE_MAX_LINES:
            # Large function/class → sub-split but keep header context
            sub_docs = safety_splitter.create_documents(
                [chunk_source],
                metadatas=[{"source": file_path, "chunk_type": "code",
                            "definition": name}],
            )
            for doc in sub_docs:
                doc.page_content = f"{header}\n\n{doc.page_content}"
            documents.extend(sub_docs)
        else:
            documents.append(Document(
                page_content=full_chunk,
                metadata={"source": file_path, "chunk_type": "code",
                           "definition": name},
            ))

    # Edge case: file with no top-level definitions (script)
    if not definitions and not documents:
        return _fallback_code_split(file_path, source, Language.PYTHON)

    return documents


# ===================================================================
# 5. JAVA / GROOVY — Regex structural splitting
# ===================================================================

_JAVA_SPLIT_PATTERN = re.compile(
    r"^(?=\s*(?:public|private|protected|static|final|abstract|synchronized|native|"
    r"default|class|interface|enum|record|def)\s)",
    re.MULTILINE,
)


def _split_java_groovy(file_path: str) -> list[Document]:
    """
    Split Java/Groovy files at class/method boundaries.

    Each chunk gets a header with the file path and package/import context.
    Falls back to RecursiveCharacterTextSplitter if no structural
    boundaries are found.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    rel_path = Path(file_path).name

    # Extract package + imports as context header
    header_lines = [f"// File: {rel_path}"]
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("package ") or stripped.startswith("import "):
            header_lines.append(stripped)
        elif stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
            break
    header = "\n".join(header_lines)

    # Split at structural boundaries
    parts = _JAVA_SPLIT_PATTERN.split(source)
    chunks = [p.strip() for p in parts if p.strip() and len(p.strip().splitlines()) > 2]

    if len(chunks) <= 1:
        return _fallback_code_split(file_path, source, Language.JAVA)

    documents = []
    safety_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=200
    )

    for chunk in chunks:
        full_chunk = f"{header}\n\n{chunk}"
        if len(chunk.splitlines()) > CODE_MAX_LINES:
            sub_docs = safety_splitter.create_documents(
                [chunk],
                metadatas=[{"source": file_path, "chunk_type": "code"}],
            )
            for doc in sub_docs:
                doc.page_content = f"{header}\n\n{doc.page_content}"
            documents.extend(sub_docs)
        else:
            documents.append(Document(
                page_content=full_chunk,
                metadata={"source": file_path, "chunk_type": "code"},
            ))

    return documents


# ===================================================================
# 6. JUPYTER NOTEBOOKS — Cell-aware → Markdown → Docling
# ===================================================================

def load_and_chunk_notebook(
    file_path: str,
    converter: DocumentConverter = None,
    chunker: HybridChunker = None,
) -> list[Document]:
    """
    Notebook → cell-aware markdown → Docling → HybridChunker.

    Strategy:
    - Markdown cells become regular markdown text (headings preserved)
    - Code cells become fenced code blocks under their narrative context
    - This preserves the natural structure: explanation → code → explanation

    The resulting markdown is fed to Docling which understands the heading
    hierarchy, then HybridChunker + contextualize() creates properly
    bounded, heading-enriched chunks.
    """
    if converter is None:
        converter = get_docling_converter()
    if chunker is None:
        chunker = get_hybrid_chunker()

    with open(file_path, "r", encoding="utf-8") as f:
        notebook = json.load(f)

    cells = notebook.get("cells", [])

    # Detect kernel language for fenced code blocks
    kernel_lang = (
        notebook.get("metadata", {})
        .get("kernelspec", {})
        .get("language", "python")
    )

    # Convert cells to structured markdown
    md_parts = []
    for cell in cells:
        cell_type = cell.get("cell_type", "")
        source_lines = cell.get("source", [])
        source_text = "".join(source_lines).strip()

        if not source_text:
            continue

        if cell_type == "markdown":
            md_parts.append(source_text)
        elif cell_type == "code":
            md_parts.append(f"```{kernel_lang}\n{source_text}\n```")
        elif cell_type == "raw":
            md_parts.append(f"```\n{source_text}\n```")

    combined_md = "\n\n".join(md_parts)

    if not combined_md.strip():
        return []

    # Feed through Docling's markdown parser + HybridChunker
    result = converter.convert_string(
        content=combined_md,
        format=InputFormat.MD,
        name=Path(file_path).stem,
    )

    chunks = list(chunker.chunk(dl_doc=result.document))
    docs = _docling_chunks_to_langchain(chunks, chunker, file_path)

    for doc in docs:
        doc.metadata["chunk_type"] = "notebook"

    return docs


# ===================================================================
# Fallback: Language-aware character splitting
# ===================================================================

def _fallback_code_split(
    file_path: str,
    source: str,
    language: Language,
) -> list[Document]:
    """
    Fallback for code files that can't be structurally parsed.
    Uses LangChain's language-aware RecursiveCharacterTextSplitter.
    """
    splitter = RecursiveCharacterTextSplitter.from_language(
        language=language, chunk_size=1200, chunk_overlap=200
    )
    docs = splitter.create_documents(
        [source],
        metadatas=[{"source": file_path, "chunk_type": "code"}],
    )
    rel_path = Path(file_path).name
    for doc in docs:
        doc.page_content = f"# File: {rel_path}\n\n{doc.page_content}"
    return docs


# ===================================================================
# Public API: route file to the right chunker
# ===================================================================

def load_and_chunk_file(
    file_path: str,
    converter: DocumentConverter = None,
    chunker: HybridChunker = None,
) -> list[Document]:
    """
    Smart router: pick the best chunking strategy based on file extension.
    Use this as the single entry point in your ingestion loop.
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        return load_and_chunk_pdf(file_path, converter, chunker)

    elif ext in (".md", ".markdown"):
        return load_and_chunk_markdown(file_path, converter, chunker)

    elif ext == ".txt":
        return load_and_chunk_text(file_path, converter, chunker)

    elif ext == ".py":
        return _split_python_by_ast(file_path)

    elif ext in (".java", ".groovy"):
        return _split_java_groovy(file_path)

    elif ext == ".ipynb":
        return load_and_chunk_notebook(file_path, converter, chunker)

    elif ext in (".js", ".ts"):
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        return _fallback_code_split(file_path, source, Language.JS)

    else:
        # Unknown extension → treat as plain text
        return load_and_chunk_text(file_path, converter, chunker)


# ===================================================================
# Backward-compatible exports (used by existing code)
# ===================================================================

def get_smart_splitter(extension: str) -> RecursiveCharacterTextSplitter:
    """Legacy: language-aware text splitter. Prefer load_and_chunk_file()."""
    params = {"chunk_size": 1200, "chunk_overlap": 200}
    language_map = {
        ".py": Language.PYTHON,
        ".md": Language.MARKDOWN,
        ".markdown": Language.MARKDOWN,
        ".js": Language.JS,
        ".ts": Language.JS,
        ".java": Language.JAVA,
    }
    lang = language_map.get(extension)
    if lang:
        return RecursiveCharacterTextSplitter.from_language(language=lang, **params)
    return RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""], **params
    )


def load_and_split_ipynb(file_path: str) -> list[Document]:
    """Legacy wrapper. Prefer load_and_chunk_file()."""
    return load_and_chunk_notebook(file_path)
