import os
import re
import multiprocessing
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend


_ARRAY_STORE_SUFFIXES = (".zarr", ".n5")


def _is_array_store(dir_path: str) -> bool:
    """Return whether a directory is a chunked array store.

    Zarr/N5 internals are implementation details, not a useful project overview.
    A single microscopy store can contain tens of thousands of chunk directories,
    so expanding one in a tool response can exceed the model API's per-message
    limit even when every individual directory contains very few files.
    """
    return os.path.basename(dir_path).lower().endswith(_ARRAY_STORE_SUFFIXES)


def walk(
    dir_path: str,
    depth: int,
    max_depth: int = 5,
    recursive: bool = True,
    max_files_per_dir: int = 10,
    max_dirs_per_dir: int = 50,
    max_total_entries: int = 500,
    expand_array_stores: bool = False,
    _budget: dict | None = None,
) -> dict:
    """Build a bounded directory tree.

    The limits apply while traversing, rather than after constructing the full
    tree.  This matters for chunked image stores: one failed BigStitcher run
    produced 16,384 top-level Zarr directories and an 11 MB tool result.
    """
    if _budget is None:
        _budget = {"remaining": max(0, int(max_total_entries))}

    node = {
        "name": os.path.basename(dir_path) or dir_path,
        "type": "directory",
        "children": []
    }

    if not expand_array_stores and _is_array_store(dir_path):
        node["type"] = "array_store"
        node["children_omitted"] = True
        node["reason"] = "chunked array-store internals are hidden by default"
        return node

    if depth >= max_depth:
        node["max_depth_reached"] = True
        return node
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError as exc:
        node["children"].append({
            "name": f"<{type(exc).__name__}: {exc}>",
            "type": "error",
        })
        return node

    directories = []
    files = []
    for entry in entries:
        full_path = os.path.join(dir_path, entry)
        if os.path.isdir(full_path):
            directories.append(entry)
        elif os.path.isfile(full_path):
            files.append(entry)

    visible_dirs = directories[:max(0, max_dirs_per_dir)]
    emitted_dirs = 0
    for entry in visible_dirs:
        if _budget["remaining"] <= 0:
            break
        _budget["remaining"] -= 1
        emitted_dirs += 1
        full_path = os.path.join(dir_path, entry)
        if recursive:
            node["children"].append(walk(
                full_path,
                depth + 1,
                max_depth,
                recursive,
                max_files_per_dir,
                max_dirs_per_dir,
                max_total_entries,
                expand_array_stores,
                _budget,
            ))
        else:
            child_type = (
                "array_store"
                if not expand_array_stores and _is_array_store(full_path)
                else "directory"
            )
            node["children"].append({"name": entry, "type": child_type})

    omitted_dirs = len(directories) - emitted_dirs
    if omitted_dirs > 0:
        node["omitted_directories"] = omitted_dirs

    visible_files = files[:max(0, max_files_per_dir)]
    emitted_files = 0
    for filename in visible_files:
        if _budget["remaining"] <= 0:
            break
        _budget["remaining"] -= 1
        emitted_files += 1
        node["children"].append({"name": filename, "type": "file"})

    omitted_files = len(files) - emitted_files
    if omitted_files > 0:
        node["omitted_files"] = omitted_files

    if _budget["remaining"] <= 0 and (omitted_dirs > 0 or omitted_files > 0):
        node["entry_budget_exhausted"] = True

    return node

def sanitize_filename(name: str) -> str:
    """Converts a script name into a valid filename."""
    # Remove invalid characters, replace spaces with underscores
    clean = re.sub(r'[<>:"/\\|?*]', '', name)
    return clean.replace(' ', '_')


# cat -n style: right-aligned line number, a TAB, then the line. The TAB is the
# delimiter _LINE_NUM_RE keys on when stripping, so a numbered read can be pasted
# straight back into edit_script without the prefix ever reaching the file.
def add_line_numbers(content: str) -> str:
    """Prefix every line with a 1-based line number (for display/reference only)."""
    lines = content.split('\n')
    width = max(6, len(str(len(lines))))
    return '\n'.join(f"{i:{width}d}\t{ln}" for i, ln in enumerate(lines, 1))


_LINE_NUM_RE = re.compile(r'^\s*\d+\t')


def strip_line_numbers(text: str) -> str:
    """Inverse of add_line_numbers, applied defensively to text a model may have copied
    from a numbered read. All-or-nothing: only strips when EVERY line carries a
    `<spaces><digits><TAB>` prefix (blank lines tolerated), so real source that merely
    starts with a digit is never touched. Returns text unchanged if it isn't numbered."""
    if not text:
        return text
    lines = text.split('\n')
    out = []
    for ln in lines:
        m = _LINE_NUM_RE.match(ln)
        if m:
            out.append(ln[m.end():])
        elif ln == '':
            out.append(ln)          # blank / trailing line — tolerate
        else:
            return text             # a non-numbered line ⇒ not a numbered block
    return '\n'.join(out)




def load_and_chunk_with_docling(file_path: str):
    """
    Performs layout-aware 'Smart Chunking' on PDFs without OCR.
    Designed for maximum CPU speed.
    """
    # 1. Setup high-speed CPU options
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False  # Critical for CPU speed
    pipeline_options.do_table_structure = True  # Allows smart table chunking

    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=multiprocessing.cpu_count(),
        device=AcceleratorDevice.CPU
    )

    # 2. Use the fast backend
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )

    # 3. Use DoclingLoader with Smart Chunking enabled
    # ExportType.DOC_CHUNKS is what performs the "Smart Layout" ingestion
    loader = DoclingLoader(
        file_path=file_path,
        converter=converter,
        export_type=ExportType.DOC_CHUNKS
    )

    return loader.load()
