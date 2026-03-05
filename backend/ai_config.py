import os
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise Exception("OPENAI_API_KEY not found in .env")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
TOP_K = 10
