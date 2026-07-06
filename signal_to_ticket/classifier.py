"""Event classifier: classifies 8-K filings via LLM tool use."""
import json
import re

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

# The operative disclosure in an 8-K almost always follows one of these markers.
# Slicing from the marker (rather than the top of the document) keeps XBRL
# headers and cover-page boilerplate out of the prompt.
_SECTION_MARKERS = [
    "Item 2.02",
    "ITEM 2.02",
    "Results of Operations",
    "RESULTS OF OPERATIONS",
    "Financial Results",
    "FINANCIAL RESULTS",
]

_MAX_PROMPT_CHARS = 4500

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


def _relevant_excerpt(filing_text: str, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    """Slice the filing starting at the disclosure section when one can be found."""
    for marker in _SECTION_MARKERS:
        idx = filing_text.find(marker)
        if idx != -1:
            return filing_text[idx:idx + max_chars]
    return filing_text[:max_chars]


def classify_event(filing_text: str, ticker: str, filing_date: str) -> dict:
    client = get_llm_client()

    prompt = (
        f"Analyze this SEC 8-K filing for {ticker} filed on {filing_date}.\n\n"
        f"Filing text:\n{_relevant_excerpt(filing_text)}\n\n"
        "Classify the primary event type, extract key investment-relevant facts with specific "
        "numbers, assess market sentiment, and identify affected sector peers."
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[_TOOL],
        tool_choice="required",
        temperature=0.1,
        max_tokens=1024,
    )

    tc = response.choices[0].message.tool_calls
    if tc:
        result = json.loads(tc[0].function.arguments)
    else:
        # Some vLLM deployments return the arguments as plain content instead of
        # honoring tool_choice. Recover the JSON block rather than failing the run.
        content = response.choices[0].message.content or ""
        match = re.search(r'\{[\s\S]*\}', content)
        if not match:
            raise ValueError(f"Classifier returned no tool call. content={content[:200]!r}")
        result = json.loads(match.group())

    result["ticker"] = ticker
    result["filing_date"] = filing_date
    return result
