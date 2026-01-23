import os 

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "langsmith api key here"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"] = "project-name-here"
os.environ["LANGSMITH_WORKSPACE_ID"] = "workspace-id-here"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "true"

gpt_key = "API_KEY_HERE"