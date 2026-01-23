from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import DirectoryLoader, TextLoader, NotebookLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
import multiprocessing

from langchain_docling.loader import ExportType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

def get_docling_converter():
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

    
    return converter

def get_smart_splitter(extension: str):
    # Default settings for CPU speed & memory
    params = {"chunk_size": 1200, "chunk_overlap": 200}
    
    if extension == ".py":
        return RecursiveCharacterTextSplitter.from_language(
            language=Language.PYTHON, **params
        )
    elif extension in [".md", ".markdown"]:
        return RecursiveCharacterTextSplitter.from_language(
            language=Language.MARKDOWN, **params
        )
    elif extension in [".js", ".ts"]:
        return RecursiveCharacterTextSplitter.from_language(
            language=Language.JS, **params
        )
    # For .txt and others, use standard recursive splitting which respects paragraphs (\n\n)
    return RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""], **params
    )

def load_and_split_ipynb(file_path: str):

    print("Loading Jupyter Notebook documents from folder:", file_path)

    loader = NotebookLoader(
        file_path, 
        include_outputs=False, 
        remove_newline=True
    )
    
    documents = loader.load()
    
    splitter = get_smart_splitter(".md")

    return splitter.split_documents(documents)






