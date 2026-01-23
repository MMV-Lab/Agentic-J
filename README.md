"# ImageJ Agent (ImagentJ)

An AI-powered agent for ImageJ/Fiji scripting and bioimage analysis.

## Prerequisites

- **Fiji/ImageJ**: Download and install Fiji from https://imagej.net/software/fiji/
- **Conda**: For environment management

## Setup

1. **Install Fiji**:
   - Download Fiji from the official website
   - Note the path to the Fiji installation

2. **Configure Fiji path**:
   - Edit `src/config/imagej_config.py`
   - Update `FIJI_JAVA_HOME` to point to your Fiji's Java home (e.g., `C:\path\to\fiji\java\win64`)

3. **Install the conda environment**:
   ```bash
   conda env create -f environment.yml
   conda activate local_imagent_J
   ```

4. **Configure your API keys**:
   - Copy `src/config/keys_template.py` to `src/config/keys.py`
   - Fill in your API keys (OpenAI, LangSmith, etc.)

5. **Configure RAG system**:
   - Rename `src/config/rag_config_template.py` to  `src/config/rag_config.py` configure document ingestion folders
   - Add paths to folders containing documentation, manuals, or knowledge base files
   - Supported formats: PDF, DOCX, TXT, MD, HTML, and more

6. **Initialize the RAG databases**:
   - Run the RAG initialization script: `python src/imagentj/rag/RAG.py`
   - This will create vector stores and ingest documents from configured folders
   - The system creates two vector stores: one for general bioimage analysis docs and one for coding errors/solutions

## RAG System Configuration

The RAG (Retrieval-Augmented Generation) system enables the agent to search through your documentation and knowledge base for relevant information when answering questions or generating scripts.

### Configuration

Edit `src/config/rag_config.py` to configure:

- **INGESTION_FOLDERS**: List of folder paths containing documents to index
- **QDRANT_DATA_PATH**: Path where vector databases are stored
- **CHUNK_SIZE** and **CHUNK_OVERLAP**: Text chunking parameters for document processing

### Initialization

Run `python src/imagentj/rag/RAG.py` to:
1. Create vector stores for bioimage analysis documentation and coding solutions
2. Process and index all documents from configured folders
3. Enable AI-powered document search capabilities

### Adding New Documents

To add new documents to the knowledge base:
1. Place documents in folders listed in `INGESTION_FOLDERS`
2. Re-run `python src/imagentj/rag/RAG.py` to re-index
3. Or call `ingest_documents()` function programmatically

## Running

- CLI version: `python run.py`
- GUI version: `python gui_runner.py`


## Project Structure

- `src/imagentj/`: Main package
- `scripts/`: Saved scripts
- `data/`: Data storage
- `src/config/`: Configuration files" 
