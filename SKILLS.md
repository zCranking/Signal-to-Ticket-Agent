# SKILLS.md

Repo-specific playbooks for common tasks. Written for an AI assistant (or a
human) working in this codebase without prior context on this specific repo.
Each skill is a recipe: when to use it, exact commands, what "done" looks like.

## Run the demo

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in VULTR_API_KEY at minimum
python seed.py                # one-time, idempotent — populates ChromaDB
streamlit run app.py
```

Done looks like: browser opens to `localhost:8501`, sidebar shows 5 demo
events, clicking "Run Agent" on any of them streams through all 8 pipeline
steps and ends in either a trade ticket or a KILL banner within ~10-20s
(most of that time is LLM round trips).

If it hangs or errors on step 2 (classify) or later, check `LLM_PROVIDER` and
the corresponding API key in `.env` — that's the most common failure point.

## Re-seed the analogue database

Needed after editing `data/seed_analogues.json`.

```bash
python seed.py
```

This is an upsert keyed by `event_id`, so re-running after adding events is
safe and doesn't duplicate existing ones. To force a full rebuild (e.g. after
changing the embedding model), delete `data/chroma_db/` first — it's
regenerated on next `seed.py` run or app launch.

## Run the test suite

```bash
python -m pytest tests/ -v
```

Every external call (LLM completions, embeddings, `requests.get`) is mocked —
this needs no API keys, no network, and no model download. If a test fails
after a change, that's a real regression, not an environment issue. This is
the single fastest way to validate a change before calling it done.

## Add a new demo event

1. Get real filing text (or write a realistic excerpt) — 400-800 words with
   specific numbers (revenue, EPS, guidance ranges, a CEO/CFO quote) reads far
   more convincingly than vague prose.
2. Add an entry to `data/demo_events.json` with `use_pre_loaded_text: true` and
   the text in `pre_loaded_text`. You need `ticker`, `cik` (zero-padded to 10
   digits — look it up at `sec.gov/cgi-bin/browse-edgar` if unsure),
   `filing_date`, `accession`, `event_type`.
3. No code changes needed — `app.py` reads this file directly into the sidebar
   selector.
4. If you want to demo a KILL, either use a ticker already on
   `mandate.json`'s `restricted_tickers` list, or write a thesis that clearly
   busts a hard rule (position size, sector cap) and let the LLM compliance
   gate (step 6) catch it instead of the instant pre-check (step 4).

## Add a new historical analogue

1. Add an entry to `data/seed_analogues.json` — needs `event_id` (unique,
   `ticker_eventtype_period` convention), `ticker`, `event_type` (must match
   one of the enum values in `classifier.py::EVENT_TYPES`), `event_date`,
   `sector`, `sic`, `headline`, `price_reaction_1d/5d/20d`, `peers_affected`,
   `peer_reaction_1d`.
2. Run `python seed.py` to load it into ChromaDB.
3. Verify retrieval: run the agent against a similar event and check the
   "Analogue Baseline" table includes your new entry with a reasonable
   similarity score.

Real price reactions (not invented ones) matter here — this dataset is the
system's actual evidence base, not decoration. If you don't have the real
number, find it (Yahoo Finance historical data is enough for a single-day
reaction) rather than guessing.

## Debug "LLM returned no tool call"

This means the model returned its answer in `message.content` instead of
`message.tool_calls`, which some vLLM deployments do on complex schemas even
with `tool_choice="required"`. Every LLM-calling module
(`classifier.py`, `compliance.py`, `retrieval.py`, `ticket.py`) already has a
regex fallback that extracts the first `{...}` block from `content` — if
you're seeing this error, the fallback also failed, meaning the model
returned something that isn't parseable JSON at all. Print
`response.choices[0].message.content` and `response.choices[0].finish_reason`
to see what actually came back; usually this means `max_tokens` was too low
(the model got cut off mid-JSON) — check the budget for that call is ≥ 200.

## Debug a step that skips silently

Check `agent.py`'s early-return points:
- Step 2: `event_type == "other" and sentiment == "neutral"` → `SKIPPED`, no
  ticket. This is correct behavior for a genuinely non-actionable filing, not
  a bug — verify the classification is actually wrong before "fixing" it.
- Step 4: `pre_check == "RESTRICTED"` → `KILLED` at `mandate_pre_check`, steps
  5-8 never run. Check `result["stage"]` to distinguish this from a step-6 kill.
- Step 6: `decision == "KILL"` → `KILLED` at `compliance_gate`, step 7-8 never run.

## Switch LLM provider

Everything reads from `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`,
`LLM_MODEL` in `config.py` — never touch provider-specific vars in the LLM
modules themselves. To switch:

```
# .env
LLM_PROVIDER=crusoe
CRUSOE_API_KEY=your_key
```

No code changes needed. Note: as of the last working session, Crusoe had an
unresolved 403 auth issue with the keys tried — verify a Crusoe key actually
authenticates (`curl` a `/v1/models` call) before assuming this path works.

## Check for exposed secrets before pushing

```bash
git log --all --oneline -- .env      # should return nothing
git ls-files | grep -i '^\.env$'     # should return nothing (not tracked)
git status --short                   # review anything staged before committing
```

`.env` was exposed in early history once and the history was rewritten with
`git-filter-repo` to remove it — see `CLAUDE.md`'s "Current status" section.
If you ever see `.env` show up in `git status` as staged, stop and check
`.gitignore` before committing.
