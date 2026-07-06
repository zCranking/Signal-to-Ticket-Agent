# Decision Log

Short records of the non-obvious technical choices, in the spirit of ADRs.

---

## ADR-001 — Local embeddings over an embedding API

**Context.** The retrieval step needs to embed one query and search ~50
analogue documents. Vultr's VultronRetriever models looked like a natural fit,
but they are served only at `/chat/completions` — they're re-ranker/chat
models, and `/v1/embeddings` returns 404 for them.

**Decision.** Embed locally with `sentence-transformers` (`all-MiniLM-L6-v2`)
and use ChromaDB for ANN search.

**Consequences.** Zero network dependency in the retrieval path, ~ms query
latency after model warmup, and one fewer API key. The model download (~90MB)
happens once at first run. At corpus sizes several orders of magnitude larger
this choice should be revisited.

---

## ADR-002 — `tool_choice="required"` plus a JSON fallback parser

**Context.** Forcing a specific function via
`tool_choice={"type": "function", "function": {"name": ...}}` was not reliably
honored by the vLLM deployment serving DeepSeek-V4-Flash — on complex schemas
(nested object arrays) the model returned the JSON in `content` and
`tool_calls` came back `None`, crashing steps 7 and 8.

**Decision.** Every LLM call uses `tool_choice="required"` and, when
`tool_calls` is `None`, falls back to extracting the first `{...}` block from
the raw content.

**Consequences.** Provider quirks degrade gracefully instead of failing the
run. The fallback parse is regex-based and permissive by design; schema
validation happens implicitly downstream when fields are read.

---

## ADR-003 — Half-Kelly with an HV20 volatility scalar

**Context.** Full Kelly maximizes long-run geometric growth, but the input
win-rate here is estimated from a handful of retrieved analogues — exactly the
setting where full Kelly's sensitivity to estimation error is most punishing.

**Decision.** Size at half the Kelly fraction, then multiply by
`clamp(0.20 / HV20, 0.4, 1.0)` so positions shrink when 20-day realized vol
runs above a 20% annualized baseline. Never scale up in quiet markets, and cap
at the mandate's per-position dollar limit.

**Consequences.** Retains most of Kelly's growth property at a fraction of the
drawdown risk; sizing is conservative by construction, which suits an agent
that acts on single-filing signals.

---

## ADR-004 — Pre-loaded demo filings instead of live EDGAR in demos

**Context.** EDGAR enforces rate limits and occasionally serves slow or
reordered responses. A demo that depends on live fetches will eventually fail
in front of an audience.

**Decision.** Ship curated filing texts in `data/demo_events.json` and pass
them through the same pipeline entry point via a `_pre_loaded_text` key on the
filing dict — the agent logic is identical either way; only step 1's fetch is
bypassed. (An earlier approach that monkey-patched the `edgar` module didn't
work: `agent.py` imports the function directly, so module patches never take
effect. The data-driven injection replaced it.)

**Consequences.** Deterministic demos, and the "Live ticker" mode still
exercises the real EDGAR path.

---

## ADR-005 — Instant pre-check before the LLM compliance gate

**Context.** Restricted-ticker and restricted-sector matching is exact set
membership. Routing it through an LLM adds latency, cost, and a nonzero chance
of a wrong answer on the easiest rule in the book.

**Decision.** Check the restricted lists in code (step 4) and short-circuit to
KILL before any sizing or LLM compliance work happens. The LLM gate (step 6)
handles what genuinely needs judgment: sector caps, position limits, and rule
interpretation against a free-text thesis.

**Consequences.** The most common kill path costs ~0ms and can't hallucinate.
