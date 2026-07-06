"""Vector store: ChromaDB persistence with local sentence-transformer embeddings."""
from __future__ import annotations

from pathlib import Path

import chromadb

from .config import CHROMA_PATH


class EventVectorStore:
    """ANN search over historical event analogues.

    Embeddings run locally (all-MiniLM-L6-v2) — no API dependency, and at this
    corpus size the model loads once and queries are effectively instant.
    """

    def __init__(self, path: Path):
        self._path = path
        self._collection = None
        self._model = None

    @property
    def collection(self):
        if self._collection is None:
            self._path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self._path))
            # Cosine distance is invariant to embedding magnitude, which matters
            # because event descriptions vary widely in length; L2 would
            # systematically penalize the short ones.
            self._collection = client.get_or_create_collection(
                name="event_analogues",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model.encode(text).tolist()

    def upsert(self, event_id: str, text: str, metadata: dict) -> None:
        # ChromaDB metadata values must be str/int/float/bool
        safe_meta = {
            k: (str(v) if not isinstance(v, (str, int, float, bool)) else v)
            for k, v in metadata.items()
        }
        self.collection.upsert(
            ids=[event_id],
            embeddings=[self.embed(text)],
            documents=[text],
            metadatas=[safe_meta],
        )

    def query(self, query_text: str, event_type: str = "", n_results: int = 5) -> list[dict]:
        total = self.collection.count()
        if total == 0:
            return []

        kwargs: dict = dict(
            query_embeddings=[self.embed(query_text)],
            n_results=min(n_results, total),
            include=["documents", "metadatas", "distances"],
        )
        if event_type and event_type != "other":
            kwargs["where"] = {"event_type": {"$eq": event_type}}

        try:
            results = self.collection.query(**kwargs)
        except Exception:
            # An unseeded event_type produces an empty filter set; retry unfiltered
            # so the caller still gets nearest neighbors to reason with.
            kwargs.pop("where", None)
            results = self.collection.query(**kwargs)

        return [
            {
                "event_id": results["ids"][0][i],
                "similarity": round(1 - results["distances"][0][i], 4),
                "metadata": meta,
                "text": results["documents"][0][i],
            }
            for i, meta in enumerate(results["metadatas"][0])
        ]

    def count(self) -> int:
        return self.collection.count()


_store = EventVectorStore(CHROMA_PATH)


# Module-level API used by the rest of the package
def embed(text: str) -> list[float]:
    return _store.embed(text)


def upsert_analogue(event_id: str, text: str, metadata: dict) -> None:
    _store.upsert(event_id, text, metadata)


def query_analogues(query_text: str, event_type: str = "", n_results: int = 5) -> list[dict]:
    return _store.query(query_text, event_type=event_type, n_results=n_results)


def collection_count() -> int:
    return _store.count()
