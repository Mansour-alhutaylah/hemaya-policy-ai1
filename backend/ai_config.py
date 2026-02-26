import os
from dotenv import load_dotenv

load_dotenv()

# HuggingFace API token (free at huggingface.co/settings/tokens)
HF_API_TOKEN = os.getenv("HF_API_TOKEN")

# Model endpoints (HuggingFace Inference API)
MODELS = {
    "llm": {
        "name": "Qwen/Qwen2.5-3B-Instruct",
        "endpoint": "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-3B-Instruct",
        "type": "text-generation",
        "max_new_tokens": 512,
        "temperature": 0.1,  # Low temp = deterministic compliance judgments
    },
    "embeddings": {
        "name": "BAAI/bge-base-en-v1.5",
        "endpoint": "https://api-inference.huggingface.co/models/BAAI/bge-base-en-v1.5",
        "type": "feature-extraction",
        "dimension": 768,  # BGE-base outputs 768-dimensional vectors
    },
    "reranker": {
        "name": "BAAI/bge-reranker-v2-m3",
        "endpoint": "https://api-inference.huggingface.co/models/BAAI/bge-reranker-v2-m3",
        "type": "text-classification",
    },
}

# Chunking settings for policy documents
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 100    # overlap between chunks for context continuity
TOP_K_RETRIEVAL = 10   # how many chunks to retrieve initially
TOP_K_RERANK = 3       # how many chunks to keep after reranking
