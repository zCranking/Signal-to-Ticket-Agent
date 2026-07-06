"""Compliance gate: checks trade thesis against investment mandate via LLM."""
import json
import re

from openai import OpenAI

from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, MANDATE_PATH

_TOOL = {
    "type": "function",
    "function": {
        "name": "compliance_decision",
        "description": "Evaluate a proposed trade against the investment mandate rules",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["PASS", "KILL"],
                    "description": "KILL if any hard rule is violated, PASS otherwise",
                },
                "violations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hard rule violations (empty list if PASS)",
                },
                "warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Soft guideline concerns that don't block the trade",
                },
                "mandate_excerpt": {
                    "type": "string",
                    "description": "The specific mandate rule text cited in the decision",
                },
            },
            "required": ["decision", "violations", "warnings", "mandate_excerpt"],
        },
    },
}


def load_mandate() -> dict:
    with open(MANDATE_PATH) as f:
        return json.load(f)


def quick_restricted_check(ticker: str) -> tuple[bool, str]:
    """Fast in-memory check before LLM call. Returns (is_restricted, reason)."""
    mandate = load_mandate()
    restricted = [t.upper() for t in mandate.get("hard_rules", {}).get("restricted_tickers", [])]
    if ticker.upper() in restricted:
        return True, f"{ticker} is on the restricted ticker list"
    return False, ""


def check_compliance(
    ticker: str,
    sector: str,
    thesis: str,
    position_value: float,
) -> dict:
    mandate = load_mandate()
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    prompt = (
        "You are a compliance officer at a long-only equity fund. "
        "Review this proposed trade against the investment mandate and flag any violations.\n\n"
        f"INVESTMENT MANDATE:\n{json.dumps(mandate, indent=2)}\n\n"
        f"PROPOSED TRADE:\n"
        f"- Ticker: {ticker}\n"
        f"- Sector: {sector}\n"
        f"- Thesis: {thesis}\n"
        f"- Estimated position value: ${position_value:,.0f}\n\n"
        "Check ALL hard rules: restricted tickers, max position size, market cap floor, "
        "sector caps, leverage/derivatives restrictions. "
        "Return KILL only for hard rule violations. Return PASS with warnings for soft guideline concerns."
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[_TOOL],
        tool_choice="required",
        temperature=0.0,
        max_tokens=768,
    )

    tc = response.choices[0].message.tool_calls
    if tc:
        return json.loads(tc[0].function.arguments)
    # Fallback for vLLM deployments that return arguments as plain content.
    content = response.choices[0].message.content or ""
    match = re.search(r'\{[\s\S]*\}', content)
    if not match:
        raise ValueError(f"Compliance gate returned no tool call. content={content[:200]!r}")
    return json.loads(match.group())
