# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- Paths ---
CORPUS_DIR = BASE_DIR / "data" / "ga4gh_corpus"
CORPUS_CACHE_DIR = CORPUS_DIR / "cache"
TEST_DUL_DIR = BASE_DIR / "data" / "test_duls"
CHROMA_DIR = BASE_DIR / "chroma_db"

# --- ChromaDB ---
CORPUS_COLLECTION = os.getenv("CORPUS_COLLECTION", "ga4gh_corpus")

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# --- LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral:7b-instruct")

# --- Chunking ---
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# --- Retrieval ---
TOP_K = int(os.getenv("TOP_K", "5"))
