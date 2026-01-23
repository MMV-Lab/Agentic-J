from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
import os
from langchain_community.document_loaders import TextLoader
from .loaders import get_smart_splitter, get_docling_converter, load_and_split_ipynb
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType
from ...config.keys import keys 

path_to_folder = r"C:\Users\lukas.johanns\Downloads\knowledge_database"

path_to_RAG = "./qdrant_data"

collection_name = "BioimageAnalysisDocs"

chunk_size = 1000
overlap_size = 200


client = client = QdrantClient(
        path= path_to_RAG   # <- persistent directory
    )

def init_vector_store(path_to_RAG: str, collection_name: str):

    

    if not client.collection_exists(collection_name=collection_name):
        print(f"Creating new Qdrant collection: {collection_name}")
        
        #  This creates ./qdrant_data on disk

        client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )

    else:
        print(f"Qdrant collection '{collection_name}' already exists. Adding to existing collection.")


    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
    )

    return vector_store



def load_folder_recursively(path_to_folder: str, vector_store):
    # 1. Warm up the engine once
    converter = get_docling_converter()
    
    # 2. Safety splitter for chunks that exceed embedding limits (e.g., 512 tokens)
    # We use a larger char limit here (~2000) to catch the 528-token outliers
    safety_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

    all_chunks = []
    batch_size = 50 # Adjust based on your RAM

    for root, _, files in os.walk(path_to_folder):
        if any(x in root for x in [".ipynb_checkpoints", "__pycache__", ".git"]):
            continue

        for file in files:
            file_path = os.path.join(root, file)
            ext = Path(file).suffix.lower()

            try:
                # --- PDF Logic (Docling) ---
                if ext == ".pdf":
                    loader = DoclingLoader(file_path=file_path, converter=converter, export_type=ExportType.DOC_CHUNKS)
                    raw_chunks = loader.load()
                    # Apply safety split to avoid the "528 > 512" error
                    final_splits = safety_splitter.split_documents(raw_chunks)
                
                # --- Notebook Logic ---
                elif ext == ".ipynb":
                    final_splits = load_and_split_ipynb(file_path)

                # --- Code/Text Logic ---
                elif ext in [".py", ".md", ".txt", ".js"]:
                    print(f"Loading and splitting file: {file_path}")
                    loader = TextLoader(file_path, encoding="utf-8")
                    splitter = get_smart_splitter(ext)
                    final_splits = splitter.split_documents(loader.load())

                
                else: continue

                all_chunks.extend(final_splits)

                # 3. Batch Upload to Vector Store
                if len(all_chunks) >= batch_size or len(files) < batch_size:
                    print(f"Uploading batch of {len(all_chunks)} chunks to Qdrant...")
                    vector_store.add_documents(all_chunks)
                    all_chunks = [] # Clear memory

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    client.close()


if __name__ == "__main__":
    vector_store = init_vector_store(path_to_RAG, "codingerrors_and_solutions")

    vector_store = init_vector_store(path_to_RAG, collection_name)

    load_folder_recursively(path_to_folder, vector_store)

    client.close()