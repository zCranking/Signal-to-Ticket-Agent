"""Event classifier: classifies 8-K filings via LLM tool use."""
import json
from openai import OpenAI
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

EVENT_TYPES = [
    "earnings_beat",
    "earnings_miss",
    "guidance_raise",
    "guidance_cut",
    "material_event",
    "restatement",
    "merger_acquisition",
    "leadership_change",
    "other",
]

_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_filing",
        "description": "Classify an SEC 8-K filing and extract key investment facts",
        "parameters": {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "enum": EVENT_TYPES,
                    "description": "Primary event type of this filing",
                },
                "headline": {
                    "type": "string",
                    "description": "One sentence summary of the event (include key numbers)",
                },
                "key_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 specific facts from the filing with numbers/figures",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["bullish", "bearish", "neutral"],
                    "description": "Expected market sentiment direction",
                },
                "sector_relevance": {
                    "type": "string",
                    "description": "Industry/sector and which peers will be affected",
                },
                "items_reported": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "8-K item numbers present (e.g. Item 2.02, Item 7.01)",
                },
            },
            "required": ["event_type", "headline", "key_facts", "sentiment", "sector_relevance"],
        },
    },
}


def get_llm_client() -> OpenAI:
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def classify_event(filing_text: str, ticker: str, filing_date: str) -> dict:
    client = get_llm_client()

    prompt = (
        f"Analyze this SEC 8-K filing for {ticker} filed on {filing_date}.\n\n"
        f"Filing text:\n{filing_text[:4500]}\n\n"
        "Classify the primary event type, extract key investment-relevant facts with specific "
        "numbers, assess market sentiment, and identify affected sector peers."
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[_TOOL],
        tool_choice={"type": "function", "function": {"name": "classify_filing"}},
        temperature=0.1,
        max_tokens=1024,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    result["ticker"] = ticker
    result["filing_date"] = filing_date
    return result
