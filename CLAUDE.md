# Signal-to-Ticket Agent — CLAUDE.md

This file is loaded automatically by Claude Code. Read it before touching any file.

## What this project is

An event-driven quant trade agent for a hackathon. When a SEC 8-K filing drops (earnings, guidance revision, material event), the agent runs an 8-step pipeline and either emits a structured trade ticket memo or kills the idea at the compliance gate.

## File structure

```
Signal-to-Ticket-Agent/
├── signal_to_ticket/        # Core agent package
│   ├── config.py            # All env vars and constants — read this first
│   ├── edgar.py             # SEC EDGAR API: fetch 8-Ks, parse filing text
│   ├── classifier.py        # Step 2: LLM classifies event type via tool use
│   ├── vector_store.py      # ChromaDB wrapper + sentence-transformers embeddings
│   ├── retrieval.py         # Steps 3/4/7: three structured retrievals
│   ├── compliance.py        # Step 6: LLM compliance gate vs mandate.json
│   ├── sizer.py             # Step 5: Kelly criterion + HV20 position sizing
│   ├── ticket.py            # Step 8: LLM trade ticket memo with citation trail
│   └── agent.py             # Orchestration: runs all 8 steps with callbacks
├── data/
│   ├── mandate.json         # Synthetic investment mandate (hard rules, sector caps)
│   ├── demo_events.json     # 3 pre-loaded 8-K events for reliable demo presentation
│   ├── seed_analogues.json  # 20 historical events with price reactions for seeding
│   └── chroma_db/           # ChromaDB persistent store (gitignored, created by seed.py)
├── app.py                   # Streamlit UI — the demo frontend
├── seed.py                  # One-time setup: loads seed_analogues.json into ChromaDB
├── .env                     # Real API keys (gitignored — never commit)
├── .env.example             # Template with placeholder values
├── .gitignore               # Excludes .env, chroma_db/, __pycache__
└── requirements.txt         # Python dependencies
```

## LLM architecture

**Primary LLM**: Vultr Serverless Inference — `deepseek-ai/DeepSeek-V4-Flash`
- Endpoint: `https://api.vultrinference.com/v1/`
- Confirmed working: tool use / function calling supported
- Set via `LLM_PROVIDER=vultr` in `.env`

**Optional LLM**: Crusoe Managed Inference — `meta-llama/Llama-3.3-70B-Instruct`
- Set `LLM_PROVIDER=crusoe` if Crusoe key is valid

**Embeddings**: Local `sentence-transformers` (`all-MiniLM-L6-v2`)
- VultronRetriever models (`vultr/VultronRetriever*`) do NOT have an `/embeddings` endpoint — they are chat-format re-ranker LLMs only. Do not attempt to use them for embeddings.

**config.py** computes `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` at import time based on `LLM_PROVIDER`. All LLM modules import these three unified vars — never `CRUSOE_*` directly.

## The 8-step pipeline (agent.py)

| Step | Module | What it does |
|------|--------|-------------|
| 1 | `edgar.py` | Fetch 8-K text from SEC EDGAR (or use pre-loaded demo text) |
| 2 | `classifier.py` | LLM tool use → event type, headline, key_facts, sentiment |
| 3 | `retrieval.py::retrieval_1_analogues` | Vector search: top-5 historical analogues by cosine similarity |
| 4 | `retrieval.py::retrieval_2_mandate` | Load mandate.json, instant restricted-list pre-check |
| 5 | `sizer.py` | Compute HV20, p_win from analogues, half-Kelly position size |
| 6 | `compliance.py` | LLM compliance gate: PASS or KILL with mandate excerpt |
| 7 | `retrieval.py::retrieval_3_freshness` | LLM verifies key_facts against recent 10-Q/10-K |
| 8 | `ticket.py` | LLM generates full trade ticket: thesis, confidence, citations |

Steps 4/6 form the compliance gate — if triggered at either point, the pipeline returns `status: KILLED` immediately and no ticket is emitted.

## Demo mode

`data/demo_events.json` contains 3 pre-loaded events (NVDA earnings beat, AMD guidance cut, AMZN earnings beat). In demo mode, `app.py` monkey-patches `edgar.fetch_filing_text` to return the pre-loaded text, bypassing the live EDGAR call. This guarantees a reliable demo even without internet access.

## Key constraints

- ChromaDB must be seeded before the app runs: `python seed.py`
- `max_tokens` in LLM calls must be ≥ 200 or tool use fails (DeepSeek emits the tool call after thinking, which takes tokens)
- EDGAR requests need a `User-Agent` header with email — set in `config.py`
- ChromaDB 1.x is installed; if API changes, check `col.query()` parameter names

## .env required keys

```
LLM_PROVIDER=vultr
VULTR_API_KEY=<your key>
VULTR_BASE_URL=https://api.vultrinference.com/v1/
VULTR_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Optional:
```
VULTR_RERANK_MODEL=vultr/VultronRetrieverPrime-Qwen3.5-8B
CRUSOE_API_KEY=<if switching provider>
GRADIUM_API_KEY=<for TTS stretch goal>
```

## Hackathon context

- Event: RAISE 2026, judging July 5 2026
- Judging: Demo 50%, Impact 25%, Creativity 15%, Pitch 10%
- Partners integrated: Vultr (LLM inference), SEC EDGAR (data)
- Crusoe: signed up but key not validated yet
- Gradium TTS: stretch goal — read trade ticket aloud during demo
