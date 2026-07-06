# Roadmap: from demo to a real event-driven strategy

Signal-to-Ticket, as it stands, is a **signal-to-decision demo**: it shows the
full reasoning chain from filing to ticket, gated by a realistic mandate. It is
not yet a **backtestable trading strategy** — that gap is real, specific, and
worth being honest about before putting any capital behind it.

The phases below are ordered by dependency, not by difficulty. Phase 1 is the
one to do first regardless of how far you get on the others, because every
later phase assumes its answer is yes.

## Phase 1 — Validate the core thesis (do this first)

Everything downstream assumes: *"the median historical price reaction of
similar past filing events predicts the reaction to a new one."* This has
never been tested against real, out-of-sample data — the current 50-event
seed set was hand-curated to be diverse and demo-friendly, not to prove
anything statistically.

**Steps:**
1. Pull a real historical 8-K corpus from EDGAR's full-text search API
   (`efts.sec.gov/LATEST/search-index?q=...&forms=8-K`) — free, no key,
   thousands of filings available.
2. Label event type programmatically (regex on Item numbers) or with the
   existing classifier — but at scale, not one at a time.
3. For each filing, pull the actual 1-day/5-day/20-day price reaction (a
   `yfinance` batch job against filing dates).
4. Split into train/test by time (not randomly — you're testing a forecasting
   claim, so a future analogue can't inform a past prediction).
5. For each test-set event, retrieve its nearest analogues from the
   train-set-only index and check: does the analogue-implied median return
   actually correlate with the realized return? Report a correlation
   coefficient and a simple long/short backtest (buy predicted-positive
   events, measure aggregate return net of a flat cost assumption).

**What "done" looks like:** a number. Either the analogue thesis has
statistically meaningful predictive power (accept and move to Phase 2) or it
doesn't (which is also a valid, useful finding — pivot the feature set, e.g.
weight by sector/market-cap similarity in addition to event type, before
investing further).

## Phase 2 — Real-time filing ingestion

Right now the agent runs on a manual button click. A strategy needs to react
within minutes of a filing hitting EDGAR, not whenever someone opens the app.

- Poll `data.sec.gov/submissions/CIK{cik}.json` per watched ticker (or use
  EDGAR's real-time RSS/Atom feed for all new filings) every 1-5 minutes
  during market hours.
- Track the last-seen accession number per ticker to detect genuinely new
  filings rather than re-processing the same one.
- Consider EDGAR's rate limits (10 req/sec, requires a descriptive
  `User-Agent`) — a watcher polling hundreds of tickers needs batching, not a
  loop of individual requests.
- Decide what happens after-hours: 8-Ks often drop pre-market or post-close;
  the strategy needs a rule for whether it acts at the next open, waits for a
  liquidity window, or has a same-session execution path at all.

## Phase 3 — Portfolio-aware sizing

The Kelly sizer currently treats every trade as if it's the only position in
the fund. `mandate.json` already defines sector caps and a max-correlated-
positions guideline, but nothing enforces them against *actual* live exposure.

- Track a running portfolio state: open positions, sector weights, total
  deployed capital.
- Before sizing a new trade, check it against current sector weight + the new
  position's contribution — reject or scale down if it would breach a cap.
- Add a correlation check for the "max 3 correlated positions" soft
  guideline — even a crude sector-based proxy is better than nothing.

## Phase 4 — Execution realism

The backtest in Phase 1 and the live ticket generation both currently assume
you can transact at the filing-day close with no friction. Real fills look
worse:

- **Slippage model**: 8-Ks that drop after-hours or pre-market can gap 5-20%
  before the next executable price — the entry price needs to reflect the
  *next available* price, not the filing-day close.
- **Transaction costs**: even a flat basis-point assumption is better than
  zero. At the position sizes in `mandate.json` (up to $500K), market impact
  is a real consideration, not a rounding error.
- **Liquidity filter**: `mandate.json` already has `min_avg_daily_volume_usd`
  — actually enforce it against real volume data, not just as an unused field.

## Phase 5 — Paper trading

Before risking capital, wire ticket output into a paper-trading broker.

- Alpaca's paper trading API is free and has a clean REST interface — a
  natural first integration since the ticket already contains direction,
  shares, entry, stop, and target.
- Run the full pipeline (Phase 2's live watcher → Phase 3's sizing → Phase 4's
  execution assumptions) against real-time filings for at least several weeks.
  A month that includes at least one full earnings season is a meaningful
  minimum — event-driven strategies are lumpy, and a quiet week tells you
  little.
- Track realized vs. predicted returns per trade. This closes the loop back to
  Phase 1: does live paper performance match what the backtest predicted, or
  is there a live/backtest gap (usually slippage, staleness, or a subtly
  wrong assumption) that needs fixing before real capital is at risk?

## What NOT to do prematurely

- Don't add leverage, options, or short-selling — the mandate is long-only by
  design, and event-driven strategies with a directional edge don't need
  derivatives to express that edge.
- Don't scale the analogue set or event-type coverage before Phase 1 proves
  the current approach works at all — more data doesn't fix a broken premise.
- Don't build a fancy execution/order-routing layer before Phase 5's paper
  trading tells you whether the strategy is worth executing in the first
  place.

## Current phase: **Phase 1, not started**

The analogue dataset (`data/seed_analogues.json`) is 50 hand-picked events
across sectors — good for demoing pipeline behavior, not sized or sampled for
a statistical test. Phase 1 is the next concrete piece of work if this project
continues past the showcase stage.
