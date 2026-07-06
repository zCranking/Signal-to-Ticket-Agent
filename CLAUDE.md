# CLAUDE.md

Project context for AI coding assistants working in this repo.

## What this is

An event-driven trade agent. An SEC 8-K filing goes in; an 8-step pipeline
classifies the event, retrieves historical analogues, sizes a position
(half-Kelly + HV20), gates against a fund mandate, checks fact freshness, and
emits a structured trade ticket — or kills the trade with a rule citation.

## Architecture

| Step | Module | What it does |
|------|--------|-------------|
| 1 | `signal_to_ticket/edgar.py` | Fetch 8-K text from SEC EDGAR (or accept pre-loaded demo text) |
| 2 | `signal_to_ticket/classifier.py` | LLM tool use → event type, headline, key_facts, sentiment |
| 3 | `signal_to_ticket/retrieval.py::retrieval_1_analogues` | Vector search: top-5 analogues by cosine similarity |
| 4 | `signal_to_ticket/retrieval.py::retrieval_2_mandate` | Load mandate.json + instant restricted-list pre-check |
| 5 | `signal_to_ticket/sizer.py` | HV20, p_win from analogue hit rate, half-Kelly size |
| 6 | `signal_to_ticket/compliance.py` | LLM compliance gate: PASS or KILL with mandate excerpt |
| 7 | `signal_to_ticket/retrieval.py::retrieval_3_freshness` | LLM verifies key_facts against latest 10-Q/10-K |
| 8 | `signal_to_ticket/ticket.py` | LLM generates ticket: thesis, confidence, citations |

`signal_to_ticket/agent.py` orchestrates all steps and streams progress via an
`on_step(name, status, data)` callback that `app.py` (Streamlit) renders live.
Steps 4 and 6 are the compliance gate — a KILL at either point short-circuits
the pipeline with `status: "KILLED"`.

## LLM configuration

`config.py` computes `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` at import time
from `LLM_PROVIDER` (`vultr` default, `crusoe` alternate). **All LLM modules
import only these three unified vars** — never provider-specific ones.

Conventions every LLM call in this repo follows:

- `tool_choice="required"` (specific-function form is not reliably honored by
  all vLLM deployments)
- A JSON-block fallback parser when `tool_calls` comes back `None`
- `max_tokens` ≥ 200 (the model spends tokens before emitting the tool call;
  too-low budgets fail silently)

Embeddings are always local (`sentence-transformers`, `all-MiniLM-L6-v2`) —
there is no embedding API dependency, and Vultr's VultronRetriever models are
chat-format re-rankers with no `/embeddings` endpoint.

## Demo mode

`data/demo_events.json` holds pre-loaded filings. `app.py` injects the text via
a `_pre_loaded_text` key on the filing dict passed to `run_agent`; `agent.py`
checks that key before calling EDGAR. Do not monkey-patch `edgar` functions —
`agent.py` imports them directly, so patches on the module don't take effect.

## Setup and invariants

- Seed ChromaDB before first run: `python seed.py` (idempotent upsert)
- EDGAR requires a `User-Agent` header with contact info (`EDGAR_USER_AGENT` in `.env`)
- `.env` holds real keys and is gitignored — never commit it, never print it
- `data/chroma_db/` is generated and gitignored
- ChromaDB metadata values must be scalar; dicts (peer reactions) are stored as JSON strings

## Tests

`python -m pytest tests/ -v` — the suite mocks LLM clients and embeddings, so
it needs no keys, no network, and no model downloads. Keep it that way.
