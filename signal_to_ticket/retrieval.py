"""Three structured retrievals: analogues → mandate → freshness."""
import json
import statistics
from .vector_store import query_analogues
from .config import MANDATE_PATH


def retrieval_1_analogues(event_type: str, ticker: str, headline: str, sector: str) -> dict:
    """Retrieval 1: historical analogues of same event class with price reactions."""
    query = f"{event_type} {sector} {headline}"
    analogues = query_analogues(query, event_type=event_type, n_results=5)

    if not analogues:
        return {
            "analogues": [],
            "median_1d": 0.0,
            "median_5d": 0.0,
            "median_20d": 0.0,
            "sample_size": 0,
        }

    r1d = [float(a["metadata"].get("price_reaction_1d", 0)) for a in analogues]
    r5d = [float(a["metadata"].get("price_reaction_5d", 0)) for a in analogues]
    r20d = [float(a["metadata"].get("price_reaction_20d", 0)) for a in analogues]

    return {
        "analogues": analogues,
        "median_1d": statistics.median(r1d),
        "median_5d": statistics.median(r5d),
        "median_20d": statistics.median(r20d),
        "sample_size": len(analogues),
    }


def retrieval_2_mandate(ticker: str, sector: str) -> dict:
    """Retrieval 2: governing docs — returns mandate + instant restricted-list pre-check."""
    with open(MANDATE_PATH) as f:
        mandate = json.load(f)

    restricted = [t.upper() for t in mandate.get("hard_rules", {}).get("restricted_tickers", [])]
    restricted_sectors = [s.lower() for s in mandate.get("hard_rules", {}).get("restricted_sectors", [])]

    if ticker.upper() in restricted:
        return {
            "mandate": mandate,
            "pre_check": "RESTRICTED",
            "reason": f"{ticker} appears on the fund restricted ticker list",
        }

    if sector.lower() in restricted_sectors:
        return {
            "mandate": mandate,
            "pre_check": "RESTRICTED",
            "reason": f"Sector '{sector}' is restricted under the investment mandate",
        }

    return {"mandate": mandate, "pre_check": "OK"}


def retrieval_3_freshness(ticker: str, cik: str, key_facts: list[str]) -> dict:
    """Retrieval 3: most recent 10-Q/10-K to verify thesis facts aren't stale."""
    from .edgar import get_recent_filing_text
    from openai import OpenAI
    from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

    filing_text = get_recent_filing_text(cik, form_types=["10-Q", "10-K"])
    if not filing_text:
        return {"status": "UNKNOWN", "checks": [], "staleness_reason": "Could not retrieve recent filing"}

    tool = {
        "type": "function",
        "function": {
            "name": "freshness_check",
            "description": "Verify each thesis fact against the company's most recent SEC filing",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["FRESH", "STALE", "PARTIAL"],
                        "description": "FRESH if all facts confirmed, STALE if contradicted, PARTIAL if mixed",
                    },
                    "checks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fact": {"type": "string"},
                                "confirmed": {"type": "boolean"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["fact", "confirmed", "evidence"],
                        },
                    },
                    "staleness_reason": {
                        "type": "string",
                        "description": "Explain why thesis is stale (empty if FRESH)",
                    },
                },
                "required": ["status", "checks"],
            },
        },
    }

    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    prompt = (
        f"Verify whether these investment thesis facts for {ticker} are consistent "
        "with the company's most recent SEC filing.\n\n"
        f"THESIS FACTS:\n{json.dumps(key_facts, indent=2)}\n\n"
        f"RECENT FILING EXCERPT:\n{filing_text[:3000]}\n\n"
        "For each fact, determine if the filing confirms or contradicts it. "
        "Mark status as STALE if any key fact is contradicted."
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": "freshness_check"}},
        temperature=0.0,
        max_tokens=768,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)
