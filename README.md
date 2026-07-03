# Signal-to-Ticket

An event-driven quant trade agent. An 8-K filing drops → the agent classifies it, retrieves historical analogues, gates against the investment mandate, sizes the position with Kelly criterion, and emits a trade ticket with a confidence score and citation trail.

## Setup (do this once)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Minimum required in `.env`:
```
LLM_PROVIDER=vultr
VULTR_API_KEY=your_vultr_key
VULTR_BASE_URL=https://api.vultrinference.com/v1/
VULTR_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

### 3. Seed the vector database
Run once to load 20 historical 8-K events into ChromaDB:
```bash
python seed.py
```

### 4. Launch the app
```bash
streamlit run app.py
```

---

## How it works

The agent runs an 8-step pipeline on each event:

```
8-K Filing
    │
    ▼
Step 1  EDGAR Fetch      — Download filing text from SEC EDGAR
    │
    ▼
Step 2  Classify Event   — LLM: earnings_beat / guidance_raise / merger / etc.
    │
    ▼
Step 3  Retrieval 1      — Vector search: top-5 historical analogues + price reactions
    │
    ▼
Step 4  Retrieval 2      — Load investment mandate, instant restricted-list check
    │
    ▼
Step 5  Size Position    — HV20 volatility + half-Kelly criterion
    │
    ▼
Step 6  Compliance Gate  — LLM vs mandate: PASS → continue, KILL → stop here
    │
    ▼
Step 7  Retrieval 3      — LLM checks recent 10-Q/10-K: are thesis facts still fresh?
    │
    ▼
Step 8  Trade Ticket     — Thesis + confidence score + citation trail
```

## File overview

| File | Purpose |
|------|---------|
| `signal_to_ticket/agent.py` | Main pipeline orchestrator |
| `signal_to_ticket/config.py` | All config and env vars |
| `signal_to_ticket/edgar.py` | SEC EDGAR API client |
| `signal_to_ticket/classifier.py` | Event type classification (LLM tool use) |
| `signal_to_ticket/vector_store.py` | ChromaDB + sentence-transformers |
| `signal_to_ticket/retrieval.py` | Three retrieval functions |
| `signal_to_ticket/compliance.py` | Compliance gate (LLM vs mandate) |
| `signal_to_ticket/sizer.py` | Position sizing (Kelly + HV20) |
| `signal_to_ticket/ticket.py` | Trade ticket generation (LLM) |
| `app.py` | Streamlit demo UI |
| `seed.py` | One-time ChromaDB seed script |
| `data/mandate.json` | Investment mandate rules |
| `data/demo_events.json` | Pre-loaded events for reliable demo |
| `data/seed_analogues.json` | Historical 8-K events with price reactions |

## LLM providers

The active LLM is controlled by `LLM_PROVIDER` in `.env`:

| Provider | Status | Model |
|----------|--------|-------|
| `vultr` (default) | Working | `deepseek-ai/DeepSeek-V4-Flash` |
| `crusoe` | Needs valid key | `meta-llama/Llama-3.3-70B-Instruct` |

Embeddings always use local `sentence-transformers` (no API key needed).

## Switching to Crusoe

Once you have a working Crusoe API key, update `.env`:
```
LLM_PROVIDER=crusoe
CRUSOE_API_KEY=your_working_key
```

## Demo tips

- Use **Demo event** mode in the sidebar for a reliable presentation (pre-loaded filing text, no EDGAR dependency)
- Seed ChromaDB before the demo: `python seed.py`
- NVDA earnings beat is the most impressive demo event — large analogue set, strong price reaction history

## Tech stack

- **LLM**: Vultr Serverless Inference (DeepSeek-V4-Flash)
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2, local)
- **Vector DB**: ChromaDB (persistent, local)
- **Data**: SEC EDGAR API (free, no key)
- **Prices**: yfinance
- **UI**: Streamlit
