# Architecture

How Signal-to-Ticket turns an SEC filing into (or refuses to issue) a trade
ticket.

## The shape of the problem

An 8-K is an unscheduled disclosure — earnings, guidance changes, M&A,
leadership changes, material events. The information is public the moment it
hits EDGAR, but it arrives as inline-XBRL HTML wrapped in SGML headers, and the
signal (a guidance number, a dividend suspension) is buried in boilerplate. The
market typically reprices within hours. The design goal here is a pipeline
where every stage either adds evidence for a trade or provides a reason to
refuse one.

## Pipeline walkthrough

### 1. Fetch (`edgar.py`)

Ticker → CIK via SEC's `company_tickers.json`, then the submissions API for
recent 8-K metadata, then the primary document from the Archives. Extraction
strips script/style/XBRL blocks, decodes entities, and skips the cover page by
jumping to the first `Item N.NN` marker — the classifier sees disclosure text,
not filing metadata. EDGAR requires a `User-Agent` with contact info and polite
pacing; both are handled here.

Demo events bypass the network entirely: the filing dict carries a
`_pre_loaded_text` key and everything downstream is identical.

### 2. Classify (`classifier.py`)

One LLM call with a function schema: event type (from a fixed enum), a
headline, 3–5 key facts with numbers, sentiment, and sector relevance. Input is
sliced starting at the `Item 2.02` / "Results of Operations" marker when
present, capped at 4,500 chars — tool-use quality degrades on long inputs well
before the context limit does. A `neutral`/`other` classification ends the run:
no signal, no trade.

### 3. Analogues (`retrieval.py` + `vector_store.py`)

The query string (`event_type + sector + headline`) is embedded locally and
searched against a ChromaDB collection of 50 historical filing events, each
carrying measured 1-day/5-day/20-day price reactions and peer moves. Results
are filtered to the same event type when possible. The medians of the retrieved
reactions become the expected-return anchor, and the fraction of positive
5-day outcomes becomes the win-rate estimate.

This is the epistemic core of the system: the expected return is not an LLM
opinion, it's the measured behavior of similar past events.

### 4. Mandate pre-check (`retrieval.py`)

`mandate.json` is loaded and the restricted ticker/sector lists are checked in
code. Exact set membership doesn't need a model — and a KILL here costs
nothing and cannot hallucinate.

### 5. Size (`sizer.py`)

Half-Kelly: `f* = (p·b − q) / b`, halved, where `b` is the analogue-median
expected return and `p` the analogue hit rate. The result is multiplied by
`clamp(0.20 / HV20, 0.4, 1.0)` — positions shrink when 20-day realized vol
exceeds a 20% annualized baseline, and never scale up in quiet tape. Output is
capped at the mandate's per-position limit. Price history comes from yfinance
and is cached per ticker so spot price and HV20 share one download.

### 6. Compliance gate (`compliance.py`)

The full mandate JSON and the proposed trade go to the LLM, which must return a
structured PASS/KILL with cited rule text. Hard-rule violations kill the run;
soft-guideline concerns pass through as warnings that depress the final
confidence score. This stage exists because most of a real mandate *isn't*
exact matching — sector caps, market-cap floors, and instrument restrictions
require reading the thesis.

### 7. Freshness (`retrieval.py`)

The most recent 10-Q/10-K is fetched and the LLM verifies each thesis fact
against it, returning FRESH / PARTIAL / STALE per-fact evidence. This catches
the classic event-trading failure: acting on a narrative the company has
already walked back in a later filing. Failures here degrade to `UNKNOWN`
rather than killing the run — freshness is evidence, not a gate.

### 8. Ticket (`ticket.py`)

Everything upstream — classification, analogue stats, compliance warnings,
sizing, freshness — is serialized into one context and the LLM emits the final
structured ticket: direction, thesis, confidence (0–100), risk factors,
stop/target percentages, and a citation trail pointing back at specific filing
lines and analogue events. Deterministic fields (entry price, share count,
dollar stops) are computed in code from the sizing output, not by the model.

## Failure philosophy

Two kinds of steps, two failure modes:

- **Gates** (classify, mandate, compliance, ticket) — a failure ends the run
  with an explicit status and reason.
- **Evidence** (analogues, sizing, freshness) — a failure degrades to a
  conservative fallback (empty analogue set, minimum size, UNKNOWN freshness)
  and the run continues with the degradation visible in the UI and priced into
  the confidence score.

Every LLM call also carries a provider-quirk fallback: `tool_choice="required"`
plus a JSON-block parser for deployments that return arguments in `content`
instead of `tool_calls` (see ADR-002 in [DECISIONS.md](../DECISIONS.md)).

## Known limitations

- The analogue set is curated, small, and not survivorship-bias-free; medians
  over five neighbors are an anchor, not a forecast.
- p_win from five samples is a coarse estimate — the half-Kelly and vol-scalar
  conservatism exists precisely to absorb this.
- Sector-cap compliance is evaluated per-trade without live portfolio
  holdings; a production system would check aggregate exposure.
- The freshness check reads a 3,000-char excerpt of the latest filing, which
  may miss facts disclosed deeper in the document.
