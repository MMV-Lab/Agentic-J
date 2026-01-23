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

## Running

- CLI version: `python run.py`
- GUI version: `python gui_runner.py`

## Troubleshooting

- If conda activation fails, ensure the environment is created: `conda env create -f environment.yml`
- Yellow underlines in code: 
  - Ensure VS Code is using the correct Python interpreter (select the conda environment)
  - Install dependencies via `pip install -r requirements.txt` (if available) or ensure all packages from environment.yml are installed
- For import errors, verify the src/ path is correctly added to Python path

## Project Structure

- `src/imagentj/`: Main package
- `scripts/`: Saved scripts
- `data/`: Data storage
- `src/config/`: Configuration files" 
