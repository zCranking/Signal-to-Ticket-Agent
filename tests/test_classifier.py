import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from signal_to_ticket import classifier


def _fake_response(tool_arguments: dict = None, content: str = None):
    """Build the minimal OpenAI response shape the classifier reads."""
    tool_calls = None
    if tool_arguments is not None:
        tool_calls = [
            SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(tool_arguments)))
        ]
    message = SimpleNamespace(tool_calls=tool_calls, content=content)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice])


CLASSIFICATION = {
    "event_type": "earnings_beat",
    "headline": "Revenue beat consensus by 6%",
    "key_facts": ["Revenue $35.1B vs $33.1B est"],
    "sentiment": "bullish",
    "sector_relevance": "Technology",
}


def _patch_client(monkeypatch, response):
    client = MagicMock()
    client.chat.completions.create.return_value = response
    monkeypatch.setattr(classifier, "get_llm_client", lambda: client)
    return client


def test_classify_via_tool_call(monkeypatch):
    _patch_client(monkeypatch, _fake_response(tool_arguments=CLASSIFICATION))
    result = classifier.classify_event("filing text", "NVDA", "2024-11-20")
    assert result["event_type"] == "earnings_beat"
    assert result["ticker"] == "NVDA"
    assert result["filing_date"] == "2024-11-20"


def test_classify_via_json_content_fallback(monkeypatch):
    # Some vLLM deployments ignore tool_choice and return JSON in content
    content = f"Here is the classification:\n{json.dumps(CLASSIFICATION)}"
    _patch_client(monkeypatch, _fake_response(content=content))
    result = classifier.classify_event("filing text", "NVDA", "2024-11-20")
    assert result["event_type"] == "earnings_beat"


def test_classify_raises_when_no_json(monkeypatch):
    _patch_client(monkeypatch, _fake_response(content="I cannot classify this."))
    try:
        classifier.classify_event("filing text", "NVDA", "2024-11-20")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_relevant_excerpt_slices_from_item_marker():
    text = "COVER PAGE BOILERPLATE " * 50 + "Item 2.02 Results of Operations. Revenue was up."
    excerpt = classifier._relevant_excerpt(text, max_chars=100)
    assert excerpt.startswith("Item 2.02")


def test_relevant_excerpt_falls_back_to_head():
    text = "No markers here, just prose. " * 300
    excerpt = classifier._relevant_excerpt(text, max_chars=100)
    assert excerpt == text[:100]
