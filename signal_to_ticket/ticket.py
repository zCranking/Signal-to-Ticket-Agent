"""Trade ticket memo generator: emits structured ticket with citation trail."""
import json
import re
from datetime import datetime, timezone
from openai import OpenAI
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_trade_ticket",
        "description": "Emit a structured trade ticket memo with full citation trail",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD"],
                },
                "thesis": {
                    "type": "string",
                    "description": "2-3 sentence investment thesis grounded in filing facts",
                },
                "confidence_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Confidence in the trade 0-100, accounting for analogue quality and freshness",
                },
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3 specific risks to the thesis",
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "Recommended stop loss as decimal (e.g. 0.07 = 7% below entry)",
                },
                "price_target_pct": {
                    "type": "number",
                    "description": "Price target as decimal above entry based on analogue median",
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "excerpt": {"type": "string"},
                        },
                        "required": ["source", "excerpt"],
                    },
                    "description": "Citation trail: specific filing lines and analogue events used in thesis",
                },
            },
            "required": [
                "direction", "thesis", "confidence_score",
                "risk_factors", "stop_loss_pct", "price_target_pct", "citations",
            ],
        },
    },
}


def _parse_peers(raw) -> dict:
    """Peer reactions are stored as a JSON string in ChromaDB metadata."""
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def generate_ticket(
    ticker: str,
    event_type: str,
    classification: dict,
    analogues: dict,
    compliance: dict,
    sizing: dict,
    freshness: dict,
    current_price: float,
    filing_date: str,
    accession: str,
) -> dict:
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    context = {
        "ticker": ticker,
        "event_type": event_type,
        "classification": {
            "headline": classification.get("headline", ""),
            "key_facts": classification.get("key_facts", []),
            "sentiment": classification.get("sentiment", ""),
        },
        "analogues": {
            "sample_size": analogues.get("sample_size", 0),
            "median_1d_return": f"{analogues.get('median_1d', 0):.1%}",
            "median_5d_return": f"{analogues.get('median_5d', 0):.1%}",
            "median_20d_return": f"{analogues.get('median_20d', 0):.1%}",
            "top_analogues": [
                {
                    "event": a["metadata"].get("headline", ""),
                    "ticker": a["metadata"].get("ticker", ""),
                    "date": a["metadata"].get("event_date", ""),
                    "similarity": a.get("similarity", 0),
                    "1d_return": f"{float(a['metadata'].get('price_reaction_1d', 0)):.1%}",
                    "5d_return": f"{float(a['metadata'].get('price_reaction_5d', 0)):.1%}",
                    "peer_reaction_1d": _parse_peers(a["metadata"].get("peer_reaction_1d")),
                }
                for a in analogues.get("analogues", [])[:5]
            ],
        },
        "compliance": {
            "decision": compliance.get("decision", ""),
            "warnings": compliance.get("warnings", []),
        },
        "sizing": {
            "position_value_usd": sizing.get("position_value", 0),
            "kelly_fraction": sizing.get("kelly_fraction", 0),
            "hv20_annualized": sizing.get("hv20", 0),
        },
        "freshness": {
            "status": freshness.get("status", "UNKNOWN"),
            "checks": freshness.get("checks", []),
        },
        "filing_reference": {
            "ticker": ticker,
            "accession": accession,
            "filing_date": filing_date,
        },
    }

    prompt = (
        "You are a senior equity analyst at a quantitative hedge fund. "
        "Generate a structured trade ticket memo based on the analysis below. "
        "Your thesis must cite specific facts from the filing and analogue events. "
        "The confidence score should reflect analogue quality, freshness status, and compliance warnings.\n\n"
        f"ANALYSIS:\n{json.dumps(context, indent=2)}"
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[_TOOL],
        tool_choice="required",
        temperature=0.2,
        max_tokens=2000,
    )

    tc = response.choices[0].message.tool_calls
    if tc:
        llm_out = json.loads(tc[0].function.arguments)
    else:
        # vLLM returned content instead of a tool call — extract the JSON block
        content = response.choices[0].message.content or ""
        match = re.search(r'\{[\s\S]*\}', content)
        if not match:
            raise ValueError(
                f"LLM returned no tool call and no JSON. "
                f"finish_reason={response.choices[0].finish_reason!r} "
                f"content={content[:200]!r}"
            )
        llm_out = json.loads(match.group())

    shares = int(sizing.get("position_value", 0) / current_price) if current_price > 0 else 0
    stop_loss_price = round(current_price * (1 - llm_out.get("stop_loss_pct", 0.07)), 2)
    target_price = round(current_price * (1 + llm_out.get("price_target_pct", 0.08)), 2)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "event_type": event_type,
        "filing_date": filing_date,
        "accession_number": accession,
        "direction": llm_out["direction"],
        "thesis": llm_out["thesis"],
        "confidence_score": llm_out["confidence_score"],
        "entry_price": round(current_price, 2),
        "shares": shares,
        "position_value_usd": round(sizing.get("position_value", 0), 2),
        "stop_loss": stop_loss_price,
        "price_target": target_price,
        "kelly_fraction": sizing.get("kelly_fraction", 0),
        "hv20": sizing.get("hv20", 0),
        "mandate_status": compliance.get("decision", "UNKNOWN"),
        "compliance_warnings": compliance.get("warnings", []),
        "freshness_status": freshness.get("status", "UNKNOWN"),
        "risk_factors": llm_out["risk_factors"],
        "citations": llm_out["citations"],
        "analogue_summary": context["analogues"],
    }
