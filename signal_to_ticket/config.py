import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Crusoe (optional, configure if you have a working key) ───────────────────
CRUSOE_BASE_URL = os.getenv("CRUSOE_BASE_URL", "https://api.inference.crusoecloud.com/v1/")
CRUSOE_API_KEY = os.getenv("CRUSOE_API_KEY", "")
CRUSOE_MODEL = os.getenv("CRUSOE_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

# ── Vultr Serverless Inference ────────────────────────────────────────────────
VULTR_BASE_URL = os.getenv("VULTR_BASE_URL", "https://api.vultrinference.com/v1/")
VULTR_API_KEY = os.getenv("VULTR_API_KEY", "")
# VultronRetriever models — used as re-ranker via chat endpoint
VULTR_RERANK_MODEL = os.getenv("VULTR_RERANK_MODEL", "vultr/VultronRetrieverPrime-Qwen3.5-8B")
# Standard LLM on Vultr — used as primary agent brain
VULTR_LLM_MODEL = os.getenv("VULTR_LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash")

# ── Unified LLM config (what the agent actually uses) ────────────────────────
# Set LLM_PROVIDER=crusoe to switch to Crusoe once you have a valid key.
# Default: Vultr (confirmed working)
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "vultr").lower()

if _LLM_PROVIDER == "crusoe" and CRUSOE_API_KEY:
    LLM_BASE_URL = CRUSOE_BASE_URL
    LLM_API_KEY = CRUSOE_API_KEY
    LLM_MODEL = CRUSOE_MODEL
else:
    LLM_BASE_URL = VULTR_BASE_URL
    LLM_API_KEY = VULTR_API_KEY
    LLM_MODEL = VULTR_LLM_MODEL

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY", "")

DATA_DIR = Path(__file__).parent.parent / "data"
CHROMA_PATH = DATA_DIR / "chroma_db"
MANDATE_PATH = DATA_DIR / "mandate.json"
DEMO_EVENTS_PATH = DATA_DIR / "demo_events.json"
SEED_ANALOGUES_PATH = DATA_DIR / "seed_analogues.json"

EDGAR_USER_AGENT = "Signal-to-Ticket Hackathon Agent zcranking@gmail.com"

PORTFOLIO_VALUE = 5_000_000
MAX_POSITION_VALUE = 500_000
