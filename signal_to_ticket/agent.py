"""
Signal-to-Ticket agent orchestration.
Runs the 8-step pipeline: fetch → classify → analogues → mandate → size → comply → fresh → ticket
"""
from __future__ import annotations
from typing import Callable, Optional

from .edgar import get_recent_8k, fetch_filing_text
from .classifier import classify_event
from .retrieval import retrieval_1_analogues, retrieval_2_mandate, retrieval_3_freshness
from .compliance import check_compliance
from .sizer import get_hv20, get_current_price, kelly_size, compute_shares
from .ticket import generate_ticket
from .config import PORTFOLIO_VALUE, MAX_POSITION_VALUE

StepCallback = Callable[[str, str, dict], None]

PIPELINE_STEPS = [
    "fetch_filing",
    "classify_event",
    "retrieval_analogues",
    "retrieval_mandate",
    "size_position",
    "compliance_gate",
    "freshness_check",
    "generate_ticket",
]


def run_agent(
    ticker: str,
    filing: Optional[dict] = None,
    on_step: Optional[StepCallback] = None,
) -> dict:
    """
    Execute the full Signal-to-Ticket pipeline.

    Args:
        ticker: Stock ticker symbol.
        filing: Pre-fetched filing dict (used for demo mode). Fetches latest 8-K if None.
        on_step: Callback(step_name, status, data) for UI streaming.
                 status: "running" | "done" | "warning" | "killed" | "error"

    Returns dict with keys:
        status: "TICKET" | "KILLED" | "SKIPPED" | "ERROR"
        ticket: full ticket dict (only when status == "TICKET")
        reason: explanation string (when not TICKET)
    """

    def emit(name: str, status: str = "running", data: dict = None):
        if on_step:
            on_step(name, status, data or {})

    # ── Step 1: Fetch filing ──────────────────────────────────────────────────
    emit("fetch_filing", "running")
    try:
        if filing is None:
            filings = get_recent_8k(ticker, count=1)
            if not filings:
                emit("fetch_filing", "error", {"reason": f"No 8-K found for {ticker}"})
                return {"status": "ERROR", "reason": f"No 8-K found on EDGAR for {ticker}"}
            filing = filings[0]

        # Demo mode: pre-loaded text is injected via the filing dict to bypass live EDGAR
        if filing.get("_pre_loaded_text"):
            filing_text = filing["_pre_loaded_text"]
        else:
            filing_text = fetch_filing_text(
                filing["cik"], filing["accession"], filing.get("primary_document", "")
            )

        if not filing_text.strip():
            emit("fetch_filing", "error", {"reason": "Filing text empty"})
            return {"status": "ERROR", "reason": "Could not extract text from filing"}

        emit("fetch_filing", "done", {
            "filing_date": filing["filing_date"],
            "items": filing.get("items", ""),
            "chars_extracted": len(filing_text),
        })
    except Exception as e:
        emit("fetch_filing", "error", {"error": str(e)})
        return {"status": "ERROR", "reason": f"EDGAR fetch failed: {e}"}

    # ── Step 2: Classify event ────────────────────────────────────────────────
    emit("classify_event", "running")
    try:
        classification = classify_event(filing_text, ticker, filing["filing_date"])
        emit("classify_event", "done", {
            "event_type": classification["event_type"],
            "headline": classification["headline"],
            "sentiment": classification["sentiment"],
        })
    except Exception as e:
        emit("classify_event", "error", {"error": str(e)})
        return {"status": "ERROR", "reason": f"Classification failed: {e}"}

    if classification["event_type"] == "other" and classification["sentiment"] == "neutral":
        emit("classify_event", "done", {"skipped": True})
        return {"status": "SKIPPED", "reason": "Event is neutral/other — no actionable trade signal"}

    # ── Step 3: Retrieval 1 — Historical analogues ────────────────────────────
    emit("retrieval_analogues", "running")
    try:
        analogues = retrieval_1_analogues(
            classification["event_type"],
            ticker,
            classification["headline"],
            classification.get("sector_relevance", ""),
        )
        emit("retrieval_analogues", "done", {
            "analogues_found": analogues["sample_size"],
            "median_5d": f"{analogues['median_5d']:.1%}",
            "median_1d": f"{analogues['median_1d']:.1%}",
        })
    except Exception as e:
        analogues = {"analogues": [], "median_1d": 0.0, "median_5d": 0.02, "median_20d": 0.03, "sample_size": 0}
        emit("retrieval_analogues", "warning", {"error": str(e), "fallback": "empty analogues"})

    # ── Step 4: Retrieval 2 — Mandate (pre-check) ────────────────────────────
    emit("retrieval_mandate", "running")
    try:
        mandate_data = retrieval_2_mandate(ticker, classification.get("sector_relevance", ""))
        emit("retrieval_mandate", "done", {"pre_check": mandate_data["pre_check"]})
    except Exception as e:
        emit("retrieval_mandate", "error", {"error": str(e)})
        return {"status": "ERROR", "reason": f"Mandate retrieval failed: {e}"}

    if mandate_data["pre_check"] == "RESTRICTED":
        emit("compliance_gate", "killed", {"reason": mandate_data["reason"]})
        return {
            "status": "KILLED",
            "reason": mandate_data["reason"],
            "stage": "mandate_pre_check",
        }

    # ── Step 5: Size position ─────────────────────────────────────────────────
    emit("size_position", "running")
    try:
        current_price = get_current_price(ticker)
        hv20 = get_hv20(ticker)

        positives = sum(1 for a in analogues["analogues"]
                        if float(a["metadata"].get("price_reaction_5d", 0)) > 0)
        total_analogues = max(len(analogues["analogues"]), 1)
        p_win = max(0.40, positives / total_analogues)
        expected_return = max(abs(analogues["median_5d"]), 0.02)

        sizing = kelly_size(p_win, expected_return, hv20, PORTFOLIO_VALUE, MAX_POSITION_VALUE)
        sizing["shares"] = compute_shares(sizing["position_value"], current_price)
        sizing["current_price"] = round(current_price, 2)
        sizing["p_win_estimate"] = round(p_win, 3)

        emit("size_position", "done", {
            "position_value": f"${sizing['position_value']:,.0f}",
            "shares": sizing["shares"],
            "kelly_fraction": f"{sizing['kelly_fraction']:.1%}",
            "hv20": f"{sizing['hv20']:.1%}",
        })
    except Exception as e:
        current_price = 0.0
        sizing = {
            "position_value": 25000, "kelly_fraction": 0.005,
            "hv20": 0.25, "shares": 0, "current_price": 0,
            "vol_scalar": 1.0, "p_win_estimate": 0.5,
        }
        emit("size_position", "warning", {"error": str(e), "fallback": True})

    # ── Step 6: Compliance gate (LLM) ────────────────────────────────────────
    emit("compliance_gate", "running")
    try:
        compliance = check_compliance(
            ticker,
            classification.get("sector_relevance", "Technology"),
            classification["headline"],
            sizing["position_value"],
        )
        emit("compliance_gate", "done", {
            "decision": compliance["decision"],
            "warnings": len(compliance.get("warnings", [])),
        })
    except Exception as e:
        emit("compliance_gate", "error", {"error": str(e)})
        return {"status": "ERROR", "reason": f"Compliance check failed: {e}"}

    if compliance["decision"] == "KILL":
        return {
            "status": "KILLED",
            "reason": "; ".join(compliance.get("violations", ["Mandate violation"])),
            "stage": "compliance_gate",
            "mandate_excerpt": compliance.get("mandate_excerpt", ""),
        }

    # ── Step 7: Retrieval 3 — Freshness check ────────────────────────────────
    emit("freshness_check", "running")
    try:
        freshness = retrieval_3_freshness(
            ticker, filing["cik"], classification.get("key_facts", [])
        )
        emit("freshness_check", "done", {"status": freshness["status"]})
    except Exception as e:
        freshness = {"status": "UNKNOWN", "checks": [], "staleness_reason": str(e)}
        emit("freshness_check", "warning", {"error": str(e)})

    # ── Step 8: Generate trade ticket ────────────────────────────────────────
    emit("generate_ticket", "running")
    try:
        ticket = generate_ticket(
            ticker=ticker,
            event_type=classification["event_type"],
            classification=classification,
            analogues=analogues,
            compliance=compliance,
            sizing=sizing,
            freshness=freshness,
            current_price=sizing.get("current_price", 0),
            filing_date=filing["filing_date"],
            accession=filing["accession"],
        )
        emit("generate_ticket", "done", {
            "direction": ticket["direction"],
            "confidence": ticket["confidence_score"],
        })
    except Exception as e:
        emit("generate_ticket", "error", {"error": str(e)})
        return {"status": "ERROR", "reason": f"Ticket generation failed: {e}"}

    return {"status": "TICKET", "ticket": ticket}
