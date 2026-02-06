import os

os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_API_KEY", "your-langsmith-api-key-here")
os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
os.environ.setdefault("LANGSMITH_PROJECT", "your-project-name-here")
os.environ.setdefault("LANGSMITH_WORKSPACE_ID", "your-workspace-id-here")
os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "true")

gpt_key = os.environ.get("OPENAI_API_KEY", "your-openai-api-key-here")
