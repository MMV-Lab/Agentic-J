from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import DirectoryLoader, TextLoader, NotebookLoader


def load_pdfs_into_RAG(path_to_folder: str):

    print("Loading PDF documents from folder:", path_to_folder)

    loader = DirectoryLoader(path_to_folder, 
                         glob= "**/*.pdf",
                         loader_cls=PyMuPDF4LLMLoader,
                        exclude=[
                        "**/.ipynb_checkpoints/**",
                        ],
                        show_progress=True)

    documents = loader.load()

    return documents

def load_txt_into_RAG(path_to_folder: str):


    print("Loading TXT documents from folder:", path_to_folder)

    loader = DirectoryLoader(path_to_folder, 
                         glob=["**/*.txt",
                               "**/*.md",
                               "**/*.rst",
                               "**/*.py",
                               "**/*.js",
                               "**/*.cpp",
                               "**/*.java",
                               ],
                         separators=["\nclass ", "\ndef ", "\n\n", "\n"]
                         loader_cls=TextLoader,
                         loader_kwargs={
                        "encoding": "utf-8",
                         },
    
                        show_progress=True)

    documents = loader.load()

    return documents


def load_ipynb_into_RAG(path_to_folder: str):


    print("Loading Jupyter Notebook documents from folder:", path_to_folder)

    loader = DirectoryLoader(path_to_folder, 
                         glob= "**/*.ipynb",
                         loader_cls=NotebookLoader,
                         loader_kwargs={
                        "include_outputs": False,
                        "max_output_length": 0,
                        "remove_newline": True,
                         },
                         exclude=[
                        "**/.ipynb_checkpoints/**",
                        ],
                        show_progress=True)
    
    documents = loader.load()

    return documents