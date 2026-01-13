from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loaders import load_pdfs_into_RAG, load_txt_into_RAG, load_ipynb_into_RAG


path_to_folder = r"C:\Users\lukas.johanns\Downloads\knowledge_database\knowledge_database"

path_to_RAG = "./qdrant_data"

colection_name = "BioimageAnalysisDocs"

chunk_size = 1000
overlap_size = 200


def init_vector_store(path_to_RAG: str, collection_name: str):

    client = QdrantClient(
        path= path_to_RAG   # <- persistent directory
    )

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

def get_file_types(folder_path):
    file_types = set()
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            file_type = os.path.splitext(filename)[1]
            file_types.add(file_type)
    return file_types




def load_into_RAG(path_to_folder: str, vector_store: QdrantVectorStore):

    print("Loading documents from folder:", path_to_folder)

    filetypes = get_file_types(path_to_folder)

    if ".ipynb" in filetypes:

        documents_ipynb = load_ipynb_into_RAG(path_to_folder)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, add_start_index=True)
        all_splits = text_splitter.split_documents(documents_ipynb)
        document_ids = vector_store.add_documents(all_splits)

    if ".txt" in filetypes or \
       ".md" in filetypes or \
       ".rst" in filetypes or \
       ".py" in filetypes or \
       ".js" in filetypes or \
       ".cpp" in filetypes or \
       ".java" in filetypes:
        documents_txt = load_txt_into_RAG(path_to_folder)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, add_start_index=True)
        all_splits = text_splitter.split_documents(documents_txt)
        document_ids = vector_store.add_documents(all_splits)   

    if ".pdf" in filetypes:

        documents_pdf = load_pdfs_into_RAG(path_to_folder)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, add_start_index=True)
        all_splits = text_splitter.split_documents(documents_pdf)
        document_ids = vector_store.add_documents(all_splits)

if __name__ == "__main__":

    vector_store = init_vector_store(path_to_RAG, colection_name)

    load_into_RAG(path_to_folder, vector_store)