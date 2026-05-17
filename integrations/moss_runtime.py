import asyncio
import os
from pathlib import Path

from events import push_event


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "integrations" / "moss" / "moss_seed.json"


def semantic_lookup(query, top_k=3):
    push_event("moss_lookup_started", {"query": query})
    try:
        result = _query_moss(query, top_k)
        push_event(
            "moss_lookup_finished",
            {"query": query, "top_doc": result[0]["id"] if result else None, "count": len(result)},
        )
        return result
    except Exception as error:
        result = _local_lookup(query, top_k)
        push_event(
            "moss_lookup_failed",
            {
                "query": query,
                "error": str(error),
                "fallback_count": len(result),
            },
        )
        return result


def _query_moss(query, top_k):
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME", "concorde-demo")
    if not project_id or not project_key:
        raise RuntimeError("Moss credentials are not configured")

    try:
        from moss import MossClient, QueryOptions
    except Exception as error:
        raise RuntimeError(f"Moss Python SDK unavailable: {error}") from error

    async def run():
        client = MossClient(project_id, project_key)
        await client.load_index(index_name)
        results = await client.query(index_name, query, QueryOptions(top_k=top_k, alpha=0.6))
        return [
            {
                "id": doc.id,
                "text": doc.text,
                "score": getattr(doc, "score", None),
                "metadata": getattr(doc, "metadata", {}) or {},
            }
            for doc in results.docs
        ]

    return asyncio.run(run())


def _local_lookup(query, top_k):
    import json

    with open(SEED_PATH, "r", encoding="utf-8") as handle:
        docs = json.load(handle)
    terms = {term.strip(".,!?").lower() for term in query.split() if len(term) > 2}
    scored = []
    for doc in docs:
        text = f"{doc['id']} {doc['text']} {' '.join(str(v) for v in doc.get('metadata', {}).values())}".lower()
        score = sum(1 for term in terms if term in text)
        scored.append({**doc, "score": score / max(len(terms), 1)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]
