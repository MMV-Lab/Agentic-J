import os
import json
from pathlib import Path
import pymupdf4llm
import pymupdf
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .utils import walk, sanitize_filename
from imagentj.rag.loaders import get_smart_splitter, load_and_split_ipynb
from .vector_stores import vec_store_docs
import threading
from pathlib import Path
from qdrant_client import models
from ..qdrant_client_singleton import get_qdrant_client
from config.rag_config import QDRANT_DATA_PATH, DOCS_COLLECTION_NAME

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "../../scripts/saved_scripts")

# Limits for CPU-optimized performance
MAX_CONTEXT_CHARS = 15000  # ~3,000 to 4,000 tokens
MAX_CONTEXT_PDF_PAGES = 3  # Small enough for immediate reading

def shadow_ingest_upgrade(file_path: str, vector_store):
    """
    Background worker that replaces fast chunks with high-quality Docling chunks.
    """
    try:
        print(f"🚀 [Shadow] Starting high-quality re-index: {file_path}")
        
        # 1. High-Quality Parsing (The slow part)
        from imagentj.rag.loaders import get_docling_converter
        from langchain_docling import DoclingLoader
        from langchain_docling.loader import ExportType
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        converter = get_docling_converter()
        loader = DoclingLoader(
            file_path=file_path, 
            converter=converter, 
            export_type=ExportType.DOC_CHUNKS
        )
        
        # Docling does its own smart chunking, but we use safety splitter
        safety_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        raw_chunks = loader.load()
        high_quality_splits = safety_splitter.split_documents(raw_chunks)
        
        # Ensure metadata includes the source so we can swap them
        for chunk in high_quality_splits:
            chunk.metadata["source"] = file_path
            chunk.metadata["ingestion_quality"] = "high"

        # 2. Delete the old "fast" chunks
        # We use the Qdrant client directly to wipe points matching this source
        client = get_qdrant_client(path=QDRANT_DATA_PATH)
        client.delete(
            collection_name=DOCS_COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.source",
                        match=models.MatchValue(value=file_path),
                    ),
                    models.FieldCondition(
                        key="metadata.ingestion_quality",
                        match=models.MatchValue(value="fast"),
                    ),
                ]
            ),
        )

        # 3. Insert the "high" quality chunks
        vector_store.add_documents(high_quality_splits)
        print(f"✅ [Shadow] Upgrade complete for: {file_path}")

    except Exception as e:
        print(f"❌ [Shadow] Upgrade failed for {file_path}: {e}")


@tool("inspect_folder_tree")
def inspect_folder_tree(
    path: str,
    recursive: bool = True,
    max_depth: int = 5
) -> str:
    """
    Inspects a folder and returns its subfolder structure and file names.
    Does NOT read file contents.

    Args:
        path: Absolute or relative path to the root folder.
        recursive: Whether to recurse into subfolders.
        max_depth: Maximum depth to traverse (root = depth 0).

    Returns:
        A JSON-like string describing the folder tree.
    """

    root = os.path.abspath(os.path.expanduser(path))

    if not os.path.exists(root):
        return f"ERROR: Path does not exist: {root}"

    if not os.path.isdir(root):
        return f"ERROR: Path is not a directory: {root}"

    tree = walk(root, depth=0, max_depth=max_depth, recursive=recursive)

    # Return as a string so it fits the same pattern as your other tools
    import json
    return json.dumps(tree, indent=2)


@tool("save_reusable_script")
def save_reusable_script(name: str, code: str, description: str, inputs_required: str) -> str:
    """
    Saves a working script to the permanent user library folder.
    Creates two files: a .groovy file for the code and a .json file for metadata.

    Args:
        name: A short, descriptive title (e.g., "Nuclei Segmentation via StarDist").
        code: The complete, executable Groovy or Java code.
        description: A summary of what the script does.
        inputs_required: Instructions for the user (e.g., "Open a 2D Tiff image").
    """

    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)

    safe_name = sanitize_filename(name)

    # 1. Save the code file
    code_path = os.path.join(SCRIPTS_DIR, f"{safe_name}.groovy")
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)

    # 2. Save the metadata file
    meta_path = os.path.join(SCRIPTS_DIR, f"{safe_name}.json")
    metadata = {
        "name": name,
        "description": description,
        "inputs": inputs_required,
        "language": "groovy",
        "script_file": f"{safe_name}.groovy"
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    return f"Script saved successfully as '{safe_name}.groovy' in the '{SCRIPTS_DIR}' folder."


@tool("smart_file_reader")
def smart_file_reader(file_path: str):
    """
    Analyzes and ingests a file through the provided path to expand the agent's knowledge base at runtime.

    Use this tool when a user provides a new file (PDF, TXT, PY, IPYNB) and asks
    questions that require information contained within that specific file.

    Logic:
    - Small files (<15KB or <3 pages): Returns 'context' type. You must prepend
      this content to your prompt immediately for 100% accuracy.
    - Large files: Returns 'rag' type. The file is indexed into the Qdrant store.
      You should then perform a similarity search to answer questions.

    Args:
        file_path (str): The absolute path to the uploaded file.
        vector_store (QdrantVectorStore): The active vector database instance.

    Returns:
        dict: A dictionary containing:
            - 'type': ('context' or 'rag')
            - 'content': The text if type is 'context'
            - 'message': A status update if type is 'rag'
    """
    file_path = os.path.abspath(os.path.expanduser(file_path))

    if not os.path.exists(file_path):
        return {
            "type": "error",
            "message": f"File does not exist: {file_path}"
        }

    if not os.path.isfile(file_path):
        return {
            "type": "error",
            "message": f"Path is not a file: {file_path}"
        }
    ext = Path(file_path).suffix.lower()
    file_size = os.path.getsize(file_path) # in bytes

    print(f"Analyzing {file_path} ({file_size / 1024:.2f} KB)")

    # --- CATEGORY 1: Plain Text & Code ---
    if ext in [".txt", ".py", ".md", ".js"]:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if len(content) < MAX_CONTEXT_CHARS:
            print("Action: Injecting directly into Context (Fastest)")
            return {"type": "context", "content": content}
        else:
            print("Action: Large file detected. Indexing into RAG...")
            splitter = get_smart_splitter(ext)
            splits = splitter.create_documents([content], metadatas=[{"source": file_path}])
            vec_store_docs.add_documents(splits)
            return {"type": "rag", "message": "File indexed in RAG."}

    # --- CATEGORY 2: PDFs (The slow part) ---
    elif ext == ".pdf":
        # Use PyMuPDF4LLM for runtime speed (NOT Docling)
        
        # Check page count first
        doc = pymupdf.open(file_path)
        page_count = len(doc)
        doc.close()

        if page_count <= MAX_CONTEXT_PDF_PAGES:
            md_text = pymupdf4llm.to_markdown(file_path)
            return {"type": "context", "content": md_text}
        
        else:
            # --- PHASE 1: FAST INGESTION ---
            print(f"Action: Fast-indexing {page_count} pages for immediate use...")
            md_text = pymupdf4llm.to_markdown(file_path)
            
            splitter = RecursiveCharacterTextSplitter.from_language(
                language="markdown", chunk_size=1000, chunk_overlap=150
            )
            # Mark these as 'fast' so the shadow process can find them
            fast_splits = splitter.create_documents(
                [md_text], 
                metadatas=[{"source": file_path, "ingestion_quality": "fast"}]
            )
            vec_store_docs.add_documents(fast_splits)

            # --- PHASE 2: TRIGGER SHADOW UPGRADE ---
            # We don't 'await' or wait for this; it runs on another thread.
            thread = threading.Thread(
                target=shadow_ingest_upgrade, 
                args=(file_path, vec_store_docs)
            )
            thread.daemon = True # Thread dies if main process exits
            thread.start()

            return {
                "type": "rag", 
                "message": f"Document '{Path(file_path).name}' is ready for questions."
                           f"I'm optimizing the search quality in the background."
            }

    # --- CATEGORY 3: Notebooks ---
    elif ext == ".ipynb":
        with open(file_path, 'r', encoding='utf-8') as f:
            nb_data = json.load(f)

        clean_content = []
        for cell in nb_data.get('cells', []):
            if cell['cell_type'] in ['markdown', 'code']:
                source = "".join(cell['source'])
                clean_content.append(f"[{cell['cell_type'].upper()}]\n{source}")

        full_text = "\n\n".join(clean_content)
        if len(full_text) < MAX_CONTEXT_CHARS:
            return {"type": "context", "content": full_text}
        else:
            splits = load_and_split_ipynb(file_path)
            vec_store_docs.add_documents(splits)
            return {"type": "rag", "message": "Notebook indexed."}

    return {"type": "error", "message": "Unsupported file type."}