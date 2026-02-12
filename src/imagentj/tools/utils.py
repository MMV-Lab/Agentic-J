import os
import re
import multiprocessing
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend


def walk(dir_path: str, depth: int, max_depth: int = 5, recursive: bool = True) -> dict:
    node = {
        "name": os.path.basename(dir_path) or dir_path,
        "type": "directory",
        "children": []
    }

    if depth >= max_depth:
        return node

    try:
        entries = sorted(os.listdir(dir_path))
    except PermissionError:
        node["children"].append({
            "name": "<permission denied>",
            "type": "error"
        })
        return node

    for entry in entries:
        full_path = os.path.join(dir_path, entry)

        if os.path.isdir(full_path):
            if recursive:
                node["children"].append(walk(full_path, depth + 1))
            else:
                node["children"].append({
                    "name": entry,
                    "type": "directory"
                })

        elif os.path.isfile(full_path):
            node["children"].append({
                "name": entry,
                "type": "file"
            })

    return node


def sanitize_filename(name: str) -> str:
    """Converts a script name into a valid filename."""
    # Remove invalid characters, replace spaces with underscores
    clean = re.sub(r'[<>:"/\\|?*]', '', name)
    return clean.replace(' ', '_')




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