import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# ---------- ПАПКИ ПРОЕКТА ----------
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
PROFILES_DIR = BASE_DIR / "data" / "profiles"
GRAPH_DIR = BASE_DIR / "data" / "graph"          # <-- добавлено

# Создаём все папки
for d in [DATA_DIR, OUTPUT_DIR, PROFILES_DIR, GRAPH_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------- Параметры чанкинга ----------
MAX_CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200

# ---------- GitHub Models ----------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference/chat/completions"
GITHUB_MODEL = os.getenv("GITHUB_MODEL", "deepseek/deepseek-r1")
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 4000

# ---------- Yandex (резерв) ----------
YC_API_KEY = os.getenv("YC_API_KEY", "")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID", "")
YANDEX_MODEL = os.getenv("YANDEX_MODEL", "deepseek-v4-flash")
YANDEX_API_BASE = "https://ai.api.cloud.yandex.net/v1"

# ---------- Neo4j ----------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ---------- Elasticsearch (опционально) ----------
ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "documents")

# ---------- Web Search ----------
ENABLE_WEB_SEARCH = True
WEB_SEARCH_RESULTS = 10
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")

# ---------- Прочие параметры ----------
MAX_TOKENS_PER_REQUEST = 50000
MAX_CHARS_PER_FRAGMENT = MAX_TOKENS_PER_REQUEST * 4
ASYNC_CONCURRENCY = 8
TRIPLET_TEMPERATURE = 0.3
TRIPLET_MAX_TOKENS = 4000