"""
Seed ChromaDB with historical event analogues.
Run once before demo: python seed.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from signal_to_ticket.vector_store import upsert_analogue, collection_count
from signal_to_ticket.config import SEED_ANALOGUES_PATH


def seed():
    with open(SEED_ANALOGUES_PATH) as f:
        analogues = json.load(f)

    print(f"Seeding {len(analogues)} historical analogues into ChromaDB...")

    for i, event in enumerate(analogues):
        text = (
            f"{event['ticker']} {event['event_type']} on {event['event_date']}: "
            f"{event['headline']} "
            f"Sector: {event['sector']}. "
            f"1d reaction: {event['price_reaction_1d']:+.1%}, "
            f"5d reaction: {event['price_reaction_5d']:+.1%}, "
            f"20d reaction: {event['price_reaction_20d']:+.1%}."
        )

        metadata = {
            "ticker": event["ticker"],
            "event_type": event["event_type"],
            "event_date": event["event_date"],
            "sector": event["sector"],
            "headline": event["headline"],
            "price_reaction_1d": event["price_reaction_1d"],
            "price_reaction_5d": event["price_reaction_5d"],
            "price_reaction_20d": event["price_reaction_20d"],
        }

        upsert_analogue(event["event_id"], text, metadata)
        print(f"  [{i+1}/{len(analogues)}] {event['ticker']} {event['event_type']} ({event['event_date']})")

    total = collection_count()
    print(f"\nDone. ChromaDB now contains {total} analogues.")


if __name__ == "__main__":
    seed()
