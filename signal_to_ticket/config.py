import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CRUSOE_BASE_URL = os.getenv("CRUSOE_BASE_URL", "https://api.inference.crusoecloud.com/v1/")
CRUSOE_API_KEY = os.getenv("CRUSOE_API_KEY", "")
CRUSOE_MODEL = os.getenv("CRUSOE_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

VULTR_BASE_URL = os.getenv("VULTR_BASE_URL", "")
VULTR_API_KEY = os.getenv("VULTR_API_KEY", "")
VULTR_EMBED_MODEL = os.getenv("VULTR_EMBED_MODEL", "vultr/vultronretriever-v1")

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY", "")

DATA_DIR = Path(__file__).parent.parent / "data"
CHROMA_PATH = DATA_DIR / "chroma_db"
MANDATE_PATH = DATA_DIR / "mandate.json"
DEMO_EVENTS_PATH = DATA_DIR / "demo_events.json"
SEED_ANALOGUES_PATH = DATA_DIR / "seed_analogues.json"

EDGAR_USER_AGENT = "Signal-to-Ticket Hackathon Agent zcranking@gmail.com"

PORTFOLIO_VALUE = 5_000_000
MAX_POSITION_VALUE = 500_000
