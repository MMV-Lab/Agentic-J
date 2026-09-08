import os
import json
from pathlib import Path
import pymupdf4llm
import pymupdf
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .utils import walk, sanitize_filename, add_line_numbers
from imagentj.rag.loaders import get_smart_splitter, load_and_split_ipynb
from .vector_stores import get_vec_store_docs, is_rag_available
import threading
from pathlib import Path
import os
import shutil
from typing import Optional
import subprocess
from pathlib import Path
from imagentj.imagej_context import get_ij
import importlib.metadata 
import sys
import platform


# Limits for CPU-optimized performance
MAX_CONTEXT_CHARS = 30000  # ~6,000 to 8,000 tokens
MAX_CONTEXT_PDF_PAGES = 3  # Small enough for immediate reading

def shadow_ingest_upgrade(file_path: str, vector_store, file_hash: str):
    """
    Background worker that replaces fast chunks with high-quality Docling chunks.
    """
    try:
        print(f"[Shadow] Starting high-quality re-index: {file_path}")

        from imagentj.rag.loaders import get_docling_converter
        from langchain_docling import DoclingLoader
        from langchain_docling.loader import ExportType
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from qdrant_client import models
        from ..qdrant_client_singleton import get_qdrant_client
        from config.rag_config import QDRANT_DATA_PATH, DOCS_COLLECTION_NAME

        converter = get_docling_converter()
        loader = DoclingLoader(
            file_path=file_path,
            converter=converter,
            export_type=ExportType.DOC_CHUNKS
        )

        safety_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        raw_chunks = loader.load()
        high_quality_splits = safety_splitter.split_documents(raw_chunks)

        for chunk in high_quality_splits:
            chunk.metadata["source"] = file_path
            chunk.metadata["ingestion_quality"] = "high"
            chunk.metadata["file_hash"] = file_hash

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

        vector_store.add_documents(high_quality_splits)
        print(f"[Shadow] Upgrade complete for: {file_path}")

    except Exception as e:
        print(f"[Shadow] Upgrade failed for {file_path}: {e}")


@tool("inspect_folder_tree")
def inspect_folder_tree(
    path: str,
    recursive: bool = True,
    max_depth: int = 5,
    max_files_per_dir: int = 10,
    max_dirs_per_dir: int = 50,
    max_total_entries: int = 500,
    max_output_chars: int = 50_000,
    expand_array_stores: bool = False,
) -> str:
    """
    Inspects a folder and returns its subfolder structure and file names.
    Does NOT read file contents.
    Args:
        path: Absolute or relative path to the root folder.
        recursive: Whether to recurse into subfolders.
        max_depth: Maximum depth to traverse (root = depth 0).
        max_files_per_dir: Maximum number of files to list per directory before truncating.
        max_dirs_per_dir: Maximum number of subdirectories to list per directory.
        max_total_entries: Maximum total file/directory entries in the returned tree.
        max_output_chars: Hard character limit for the serialized result.
        expand_array_stores: Whether to recurse into .zarr/.n5 chunk stores. Off by default.
    Returns:
        A JSON-like string describing the folder tree.
    """
    root = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(root):
        return f"ERROR: Path does not exist: {root}"
    if not os.path.isdir(root):
        return f"ERROR: Path is not a directory: {root}"
    # Clamp model-controlled values to keep this inspection tool safe even when a
    # caller requests an accidentally enormous traversal.
    max_depth = max(0, min(int(max_depth), 20))
    max_files_per_dir = max(0, min(int(max_files_per_dir), 1_000))
    max_dirs_per_dir = max(0, min(int(max_dirs_per_dir), 1_000))
    max_total_entries = max(1, min(int(max_total_entries), 10_000))
    max_output_chars = max(2_000, min(int(max_output_chars), 100_000))

    tree = walk(
        root,
        depth=0,
        max_depth=max_depth,
        recursive=recursive,
        max_files_per_dir=max_files_per_dir,
        max_dirs_per_dir=max_dirs_per_dir,
        max_total_entries=max_total_entries,
        expand_array_stores=expand_array_stores,
    )
    serialized = json.dumps(tree, indent=2, ensure_ascii=False)
    if len(serialized) <= max_output_chars:
        return serialized

    # Keep the response valid JSON if unusually long names still push a bounded
    # tree over the character budget. The preview is intentionally a JSON string,
    # not a syntactically broken prefix masquerading as the full tree.
    preview = serialized[:max_output_chars]
    payload = {
        "type": "truncated_folder_tree",
        "root": root,
        "original_chars": len(serialized),
        "max_output_chars": max_output_chars,
        "message": "Narrow the path or lower traversal depth to inspect omitted entries.",
        "preview": preview,
    }
    limited = json.dumps(payload, indent=2, ensure_ascii=False)
    while len(limited) > max_output_chars and preview:
        preview = preview[:max(0, len(preview) - (len(limited) - max_output_chars) - 64)]
        payload["preview"] = preview
        limited = json.dumps(payload, indent=2, ensure_ascii=False)
    return limited[:max_output_chars]


@tool("smart_file_reader")
def smart_file_reader(file_path: str):
    """
    Analyzes and ingests a file through the provided path to expand the agent's knowledge base at runtime.

    Use this tool when a user provides a new file (PDF, TXT, PY, IPYNB, groovy) and asks
    questions that require information contained within that specific file.

    Read a given file at most ONCE. Its content does not change while you work, so a
    second read returns byte-identical output and only wastes a turn. In particular,
    NEVER read back a file you just wrote in order to 'verify' it — the writing tool's
    return value is the confirmation, and re-reading your own output is the classic way
    an agent falls into a save→read→save loop that never terminates.

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

    vec_store_docs = get_vec_store_docs()
    rag_available = vec_store_docs is not None

    # --- CATEGORY 1: Plain Text & Code ---
    if ext in [".txt", ".py", ".md", ".js", ".groovy", ".log"]:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if len(content) < MAX_CONTEXT_CHARS or not rag_available:
            print("Action: Injecting directly into Context (Fastest)")
            if len(content) > MAX_CONTEXT_CHARS:
                content = content[:MAX_CONTEXT_CHARS] + "\n\n[... content truncated (RAG unavailable) ...]"
            # Number code/text lines for reference (display-only prefixes). Not applied to
            # the RAG-indexed branch below — numbering would pollute the embedded chunks.
            return {"type": "context", "content": add_line_numbers(content)}
        else:
            print("Action: Large file detected. Indexing into RAG...")
            splitter = get_smart_splitter(ext)
            splits = splitter.create_documents([content], metadatas=[{"source": file_path}])
            vec_store_docs.add_documents(splits)
            return {"type": "rag", "message": "File indexed in RAG."}

    # --- CATEGORY 2: PDFs (The slow part) ---
    elif ext == ".pdf":
        doc = pymupdf.open(file_path)
        page_count = len(doc)
        doc.close()

        if page_count <= MAX_CONTEXT_PDF_PAGES:
            md_text = pymupdf4llm.to_markdown(file_path)
            return {"type": "context", "content": md_text}

        elif not rag_available:
            # RAG unavailable - return truncated content directly
            md_text = pymupdf4llm.to_markdown(file_path)
            if len(md_text) > MAX_CONTEXT_CHARS:
                md_text = md_text[:MAX_CONTEXT_CHARS] + "\n\n[... content truncated (RAG unavailable) ...]"
            return {"type": "context", "content": md_text}

        else:
            from ..rag.RAG import get_file_hash, is_document_ingested
            from config.rag_config import DOCS_COLLECTION_NAME

            file_hash = get_file_hash(file_path)

            if is_document_ingested(file_hash, vec_store_docs.client, DOCS_COLLECTION_NAME):
                return {"type": "rag", "message": "Document is already fully indexed and optimized."}
            print(f"Action: Fast-indexing {page_count} pages for immediate use...")
            md_text = pymupdf4llm.to_markdown(file_path)

            splitter = RecursiveCharacterTextSplitter.from_language(
                language="markdown", chunk_size=1000, chunk_overlap=150
            )
            fast_splits = splitter.create_documents(
                [md_text],
                metadatas=[{"source": file_path, "file_hash": file_hash, "ingestion_quality": "fast"}]
            )
            vec_store_docs.add_documents(fast_splits)

            thread = threading.Thread(
                target=shadow_ingest_upgrade,
                args=(file_path, vec_store_docs, file_hash)
            )
            thread.daemon = True
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
        if len(full_text) < MAX_CONTEXT_CHARS or not rag_available:
            if len(full_text) > MAX_CONTEXT_CHARS:
                full_text = full_text[:MAX_CONTEXT_CHARS] + "\n\n[... content truncated (RAG unavailable) ...]"
            return {"type": "context", "content": full_text}
        else:
            splits = load_and_split_ipynb(file_path)
            vec_store_docs.add_documents(splits)
            return {"type": "rag", "message": "Notebook indexed."}

    return {"type": "error", "message": "Unsupported file type."}



@tool("mkdir_copy")
def mkdir_copy(action: str, target_path: str, source_path: Optional[str] = None) -> str:
    """
    Manages filesystem operations including creating directories and copying 
    files or entire folders with their contents.
    
    Args:
        action: The operation to perform ('mkdir' or 'copy').
        target_path: The destination path for the folder or file.
        source_path: The original file or folder path (required only for 'copy' action).
        
    Returns:
        A success message or an error description.
    """
    try:
        # Action: Create Directory
        if action == "mkdir":
            os.makedirs(target_path, exist_ok=True)
            return f"Successfully created directory: {target_path}"
        
        # Action: Copy (File or Folder)
        elif action == "copy":
            if not source_path:
                return "Error: source_path is required for copy action."
            
            if not os.path.exists(source_path):
                return f"Error: Source path '{source_path}' does not exist."

            # Check if the source is a directory
            if os.path.isdir(source_path):
                # Copy entire folder and contents
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                return f"Successfully copied directory tree from {source_path} to {target_path}"
            
            else:
                # Copy a single file
                # Ensure the destination parent directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_path, target_path)
                return f"Successfully copied file {source_path} to {target_path}"
        
        else:
            return f"Error: Unknown action '{action}'."

    except Exception as e:
        return f"FileSystem Error: {str(e)}"
    




@tool("setup_analysis_workspace")
def setup_analysis_workspace(project_name: str) -> str:
    """
    Creates a standardized folder tree to manage a new analysis project.
    Initializes directory architecture and logs environment metadata (Fiji & Python versions).
    """
    # 1. Define the base path
    root = Path(f"/app/data/projects/{project_name}")
    
    # 2. Define the subdirectories
    subdirs = [
        "raw_images",
        "processed_images/channels",
        "processed_images/montages",
        "scripts/imagej",
        "scripts/python",
        "data",
        "figures",
        "logs"
    ]
    
    # 3. Create the directories
    for subdir in subdirs:
        (root / subdir).mkdir(parents=True, exist_ok=True)
    
    # 4. Gather Metadata
    py_version = sys.version.split()[0]
    os_info = platform.platform()

    # 2. Capture Specific Package Versions
    # We use a helper to avoid 'ModuleNotFound' errors if a package is missing
    def get_v(package_name):
        try:
            return __import__(package_name).__version__
        except (ImportError, AttributeError):
            return "Not Installed"

    versions = {
        "pandas": get_v("pandas"),
        "numpy": get_v("numpy"),
        "matplotlib": get_v("matplotlib"),
        "seaborn": get_v("seaborn"),
        "scipy": get_v("scipy")
    }

    # Get Fiji/ImageJ Version (Assumes 'ImageJ-linux64' or 'fiji' is in PATH or known location)
    try:
        # Most Fiji installations respond to --version via the executable
        fiji_v = get_ij().getVersion()
    except Exception:
        fiji_v = "Fiji version not found."

    # 5. Write Metadata to a log file
    metadata_path = root / "logs/environment_metadata.log"
    with open(metadata_path, "w") as f:
        f.write(f"Project: {project_name}\n")
        f.write(f"OS: {os_info}\n")
        f.write(f"Python: {py_version}\n")
        f.write(f"Fiji Version: {fiji_v}\n")
        f.write("-" * 30 + "\n")
        f.write("--- Core Libraries ---\n")
        for pkg, ver in versions.items():
            f.write(f"{pkg}: {ver}\n")

    # 6. Return the tree structure
    tree_output = f"""
Successfully created project structure for: {project_name}
Location: {root}
Metadata logged to: {metadata_path}

{project_name}/
├── raw_images/           # User uploaded files
├── processed_images/     # ImageJ outputs
├── scripts/              # All analysis scripts
├── data/                 # CSV results
├── figures/              # Publication plots
└── logs/                 # Processing logs & environment_metadata.log
"""
    return tree_output


@tool("save_markdown")
def save_markdown(file_path: str, content: str) -> dict:
    """
    Writes a markdown string to a .md file at the specified absolute path.
    Creates any missing parent directories automatically.

    A returned success=True IS the confirmation that the file is on disk with the
    content you supplied. Do NOT read the file back to verify it, and do NOT write
    it a second time — that save→read→save cycle is self-perpetuating and never
    converges. Write once, trust the return value, move on.

    Args:
        file_path (str): Absolute path for the output file, e.g.
                         '/app/data/project_name/QA_Checklist_Report.md'
                         Must end with '.md'.
        content   (str): Full markdown content to write.

    Returns:
        dict with keys:
            - success (bool)
            - path    (str)  absolute path of the written file
            - size    (int)  file size in bytes
            - error   (str)  error message if success is False, else None
    """
    try:
        if not file_path.endswith(".md"):
            return {
                "success": False,
                "path": file_path,
                "size": 0,
                "error": "file_path must end with '.md'",
            }

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        size = os.path.getsize(file_path)
        print(f"[save_markdown] ✅ Saved {size} bytes → {file_path}")

        return {
            "success": True,
            "path": file_path,
            "size": size,
            "error": None,
        }

    except Exception as e:
        print(f"[save_markdown] ❌ Failed to write {file_path}: {e}")
        return {
            "success": False,
            "path": file_path,
            "size": 0,
            "error": str(e),
        }
    
