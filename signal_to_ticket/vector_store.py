"""
Vector store: ChromaDB for persistence + local sentence-transformers for embeddings.

VultronRetriever models (vultr/VultronRetriever*) are not served at the standard
/embeddings endpoint — they're re-ranker/LLM models only. We use sentence-transformers
locally for embedding and ChromaDB for ANN search, which is fast and reliable.
"""
from __future__ import annotations
import chromadb
from .config import CHROMA_PATH

_collection = None
_local_model = None


def _get_collection():
    global _collection
    if _collection is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_or_create_collection(
            name="event_analogues",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def embed(text: str) -> list[float]:
    """Embed text using local sentence-transformers (all-MiniLM-L6-v2)."""
    return _local_embed(text)


def _local_embed(text: str) -> list[float]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_model.encode(text).tolist()


def upsert_analogue(event_id: str, text: str, metadata: dict) -> None:
    col = _get_collection()
    embedding = embed(text)
    # ChromaDB metadata values must be str/int/float/bool
    safe_meta = {k: (str(v) if not isinstance(v, (str, int, float, bool)) else v)
                 for k, v in metadata.items()}
    col.upsert(ids=[event_id], embeddings=[embedding], documents=[text], metadatas=[safe_meta])


def query_analogues(query_text: str, event_type: str = "", n_results: int = 5) -> list[dict]:
    col = _get_collection()
    total = col.count()
    if total == 0:
        return []

    embedding = embed(query_text)
    n = min(n_results, total)

    kwargs: dict = dict(
        query_embeddings=[embedding],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    if event_type and event_type != "other":
        kwargs["where"] = {"event_type": {"$eq": event_type}}

    try:
        results = col.query(**kwargs)
    except Exception:
        kwargs.pop("where", None)
        results = col.query(**kwargs)

    analogues = []
    for i, meta in enumerate(results["metadatas"][0]):
        analogues.append({
            "event_id": results["ids"][0][i],
            "similarity": round(1 - results["distances"][0][i], 4),
            "metadata": meta,
            "text": results["documents"][0][i],
        })
    return analogues


def collection_count() -> int:
    return _get_collection().count()
