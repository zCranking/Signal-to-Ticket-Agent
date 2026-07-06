# CLAUDE.md

Project context for AI coding assistants working in this repo. Read this first
on a new device or a fresh session — it's written so you can pick up the
project cold with no prior conversation.

## What this is

An event-driven trade agent. An SEC 8-K filing goes in; an 8-step pipeline
classifies the event, retrieves historical analogues, sizes a position
(half-Kelly + HV20), gates against a fund mandate, checks fact freshness, and
emits a structured trade ticket — or kills the trade with a rule citation.

This started as a hackathon project and is being maintained as a GitHub
portfolio piece. Code quality, documentation, and presentation matter as much
as functionality here — see "Standards for this repo" below.

## Architecture

| Step | Module | What it does |
|------|--------|-------------|
| 1 | `signal_to_ticket/edgar.py` | Fetch 8-K text from SEC EDGAR (or accept pre-loaded demo text) |
| 2 | `signal_to_ticket/classifier.py` | LLM tool use → event type, headline, key_facts, sentiment |
| 3 | `signal_to_ticket/retrieval.py::retrieval_1_analogues` | Vector search: top-5 analogues by cosine similarity |
| 4 | `signal_to_ticket/retrieval.py::retrieval_2_mandate` | Load mandate.json + instant restricted-list pre-check (no LLM) |
| 5 | `signal_to_ticket/sizer.py` | HV20, p_win from analogue hit rate, half-Kelly size |
| 6 | `signal_to_ticket/compliance.py` | LLM compliance gate: PASS or KILL with mandate excerpt |
| 7 | `signal_to_ticket/retrieval.py::retrieval_3_freshness` | LLM verifies key_facts against latest 10-Q/10-K |
| 8 | `signal_to_ticket/ticket.py` | LLM generates ticket: thesis, confidence, citations |

`signal_to_ticket/agent.py` orchestrates all steps and streams progress via an
`on_step(name, status, data)` callback that `app.py` (Streamlit) renders live,
including per-step elapsed time.

**Steps 4 and 6 are two separate compliance checks, not one** — this trips
people up, so it's worth being explicit:
- Step 4 is a free, instant, deterministic set-membership check (is this ticker
  or sector on the restricted list?). A KILL here happens in `retrieval_mandate`
  and short-circuits before sizing or the LLM ever runs.
- Step 6 is the LLM reading the full mandate against the proposed trade for
  things that need judgment — sector caps, position limits, rule interpretation.

If you're debugging "why did this get killed without an LLM call," check
`result["stage"]` — `"mandate_pre_check"` means step 4, `"compliance_gate"`
means step 6.

## LLM configuration

`config.py` computes `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` at import time
from `LLM_PROVIDER` (`vultr` default, `crusoe` alternate). **All LLM modules
import only these three unified vars** — never provider-specific ones.

Conventions every LLM call in this repo follows:

- `tool_choice="required"` (the specific-function form,
  `{"type": "function", "function": {"name": ...}}`, is not reliably honored by
  all vLLM deployments on complex schemas)
- A JSON-block fallback parser when `tool_calls` comes back `None` (regex
  `\{[\s\S]*\}` over `message.content`)
- `max_tokens` ≥ 200 (the model spends tokens before emitting the tool call;
  too-low budgets fail silently with no tool call and no error)

Embeddings are always local (`sentence-transformers`, `all-MiniLM-L6-v2`) —
there is no embedding API dependency, and Vultr's VultronRetriever models are
chat-format re-rankers with no `/embeddings` endpoint (this was a real dead
end during development — don't re-attempt routing embeddings through Vultr).

## Demo mode

`data/demo_events.json` holds five pre-loaded filings. `app.py` injects the
text via a `_pre_loaded_text` key on the filing dict passed to `run_agent`;
`agent.py` checks that key before calling EDGAR. **Do not monkey-patch `edgar`
functions** — `agent.py` imports them directly (`from .edgar import
fetch_filing_text`), so patches on the module object don't take effect. This
was tried once and silently failed; the data-driven injection replaced it.

The META demo event is deliberately the most instructive one: a strong
bullish earnings beat that still gets killed, because META is on
`mandate.json`'s restricted ticker list. Use it to demo the mandate gate.

## Setup and invariants

- Seed ChromaDB before first run: `python seed.py` (idempotent upsert, 50 analogues)
- EDGAR requires a `User-Agent` header with contact info (`EDGAR_USER_AGENT` in `.env`)
- `.env` holds real keys and is gitignored — never commit it, never print it,
  never echo its contents in a shell command whose output might get logged
- `data/chroma_db/` is generated and gitignored
- ChromaDB metadata values must be scalar; dicts (peer reactions) are stored as
  JSON strings and parsed back out in `ticket.py::_parse_peers`

## Standards for this repo

This is a showcase project, not just a working prototype. When making changes:

- No AI-fingerprint comments ("fixed bug", "we got burned", references to past
  conversations or hackathon context). Comments explain non-obvious *why*, not
  *what* — see the half-Kelly comment in `sizer.py` or the cosine-distance
  comment in `vector_store.py` for the target tone.
- Keep the docs in sync when you change behavior: if you touch the pipeline
  shape, update the table above, `README.md`'s pipeline table, and
  `docs/ARCHITECTURE.md`'s walkthrough. If you make a non-obvious technical
  choice, add an ADR to `DECISIONS.md`.
- Run `python -m pytest tests/ -v` before considering a change done — it mocks
  all LLM/embedding calls, so it needs no keys, no network, no model downloads.
  If it's not passing, nothing else in this list matters.
- UI changes: prefer the existing CSS-based stat-tile pattern in `app.py`
  (`render_stat_grid`) over `st.metric()` in multi-column layouts — Streamlit's
  native metric columns squeeze evenly regardless of content and clip wide
  numbers; a CSS grid with `minmax()` wraps instead.

## Tests

`python -m pytest tests/ -v` — 20 tests across `test_sizer.py`,
`test_classifier.py`, `test_vector_store.py`, `test_edgar.py`. All external
calls (LLM, embeddings, requests) are mocked.

CI runs the same suite on push/PR via `.github/workflows/test.yml`.

## Current status (last updated 2026-07-06)

**Done:**
- Full 8-step pipeline working end-to-end against Vultr (DeepSeek-V4-Flash)
- Code hygiene pass: imports at file tops, no AI-fingerprint comments, class-based
  vector store, `pyproject.toml`, `LICENSE`, tests + CI
- `edgar.py`'s HTML stripper now skips SGML/XBRL headers and jumps to the first
  `Item N.NN` marker instead of feeding the classifier cover-page boilerplate
- Analogue dataset expanded from 20 → 50 historical events across more sectors
  (Healthcare, Consumer, Financials, Energy, Industrials, Real Estate, Utilities)
- Two new demo events: META (restricted-ticker KILL demo) and INTC (guidance
  cut + dividend suspension, -26% event)
- UI: step timing, analogue comparison table, peer-ripple effect chips,
  Plotly confidence gauge, JSON export, run-history tab
- UI numbers fixed: replaced `st.metric()` columns (which squeeze/clip in
  narrow layouts) with a CSS stat-grid that wraps instead of truncating
- Mandate-kill attribution fixed: a restricted-ticker kill now shows on step 4
  (`retrieval_mandate`), not step 6 (`compliance_gate`) — previously both
  showed on the compliance_gate step, which implied the LLM gate ran when it
  never did
- Full doc rewrite: README, ARCHITECTURE, DECISIONS, this file
- **Security: git history scrubbed.** An early commit exposed `.env` with real
  API keys (Vultr, Crusoe, Gradium). History was rewritten with
  `git-filter-repo` to remove `.env` from every commit and force-pushed to
  `origin/main`. A local branch `backup-before-history-rewrite` preserves the
  old history if ever needed — safe to delete once confirmed unnecessary.

**Not yet done / needs follow-up:**
- **Key rotation.** The exposed keys (Vultr, Crusoe, Gradium) were live during
  the exposure window regardless of the history scrub — rotate them if that
  hasn't happened yet. Check with the user before assuming this is done.
- Gradium TTS integration was a stretch goal — never implemented.
- Crusoe as a provider has an unresolved auth issue (403 on the keys tried
  during development) — Vultr is the working default; don't assume Crusoe
  works without testing it first.

**Roadmap (turning this into a real strategy, not just a demo):** see
`ROADMAP.md`. Short version: the analogue-return thesis has never been
backtested against real historical filings — that's the highest-priority next
step, before any live-trading infrastructure work.

## Where to look for more

- `README.md` — user-facing overview, quickstart, design decisions
- `docs/ARCHITECTURE.md` — pipeline walkthrough in depth, failure philosophy
- `DECISIONS.md` — ADRs for the non-obvious technical choices
- `ROADMAP.md` — path from demo to a backtested, paper-tradeable strategy
- `SKILLS.md` — repo-specific workflows (seeding, testing, running, debugging)
