import os

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "your-langsmith-api-key-here"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"] = "your-project-name-here"
os.environ["LANGSMITH_WORKSPACE_ID"] = "your-workspace-id-here"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "true"

gpt_key = "your-openai-api-key-here"
