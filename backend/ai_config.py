import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    import warnings
    warnings.warn(
        "OPENAI_API_KEY not set — AI features will fail when invoked. Add it to your .env file.",
        stacklevel=2,
    )

MODELS = {
    "llm": {
        "name": "gpt-4o-mini",
        "provider": "openai",
        "temperature": 0.1,
        "max_tokens": 1500,
    },
    "embeddings": {
        "name": "text-embedding-3-small",
        "provider": "openai",
        "dimension": 1536,
    },
}

# Chunking settings for policy documents
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 100    # overlap between chunks for context continuity
TOP_K_RETRIEVAL = 10   # how many chunks to retrieve initially
TOP_K_RERANK = 5       # how many chunks to keep after reranking
