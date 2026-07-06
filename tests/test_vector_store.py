import hashlib

from signal_to_ticket.vector_store import EventVectorStore


def _fake_embed(text: str) -> list[float]:
    """Deterministic 32-dim pseudo-embedding — avoids downloading the real model."""
    digest = hashlib.sha256(text.encode()).digest()
    return [b / 255.0 for b in digest]


def _make_store(tmp_path) -> EventVectorStore:
    store = EventVectorStore(tmp_path / "chroma")
    store.embed = _fake_embed
    return store


def test_upsert_and_count(tmp_path):
    store = _make_store(tmp_path)
    assert store.count() == 0
    store.upsert("evt1", "NVDA earnings beat", {"ticker": "NVDA", "event_type": "earnings_beat"})
    assert store.count() == 1


def test_query_round_trip(tmp_path):
    store = _make_store(tmp_path)
    store.upsert("evt1", "NVDA earnings beat", {"ticker": "NVDA", "event_type": "earnings_beat"})
    store.upsert("evt2", "AMD guidance cut", {"ticker": "AMD", "event_type": "guidance_cut"})

    results = store.query("NVDA earnings beat", event_type="earnings_beat")
    assert len(results) == 1
    assert results[0]["metadata"]["ticker"] == "NVDA"
    assert results[0]["similarity"] == 1.0  # identical text, identical embedding


def test_query_empty_store(tmp_path):
    store = _make_store(tmp_path)
    assert store.query("anything") == []


def test_metadata_scalars_survive_and_dicts_stringify(tmp_path):
    store = _make_store(tmp_path)
    store.upsert("evt1", "text", {
        "ticker": "NVDA",
        "price_reaction_5d": 0.15,
        "peers": {"AMD": 0.03},  # non-scalar -> stringified
    })
    result = store.query("text")[0]
    assert result["metadata"]["price_reaction_5d"] == 0.15
    assert isinstance(result["metadata"]["peers"], str)
