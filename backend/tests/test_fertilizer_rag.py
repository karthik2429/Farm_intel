"""
Guards for the ICAR fertiliser knowledge layer.

What these hold the module to:
  1. The corpus really contains the ICAR documents, and it is chunked (not one
     blob per PDF); every shipped PDF has a readable citation title.
  1b. A PDF added or replaced on disk invalidates the cache instead of being
     silently ignored.
  2. Every retrieved passage carries a document title and a page, so the UI can
     cite it instead of showing anonymous text.
  3. Retrieval works without an LLM: with no key the endpoint still returns the
     evidence and says why the written advisory is missing.
  4. `/fertilizer/recommend` always returns the deterministic cosine/rule
     answer; the ICAR layer is additive and can never break the page.

Run from the repo root:
    ./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fertilizer_rag  # noqa: E402


def test_corpus_contains_the_icar_documents():
    stats = fertilizer_rag.corpus_stats()
    assert stats["chunks"] > 1_000, "a corpus this small cannot ground an answer"
    assert len(stats["documents"]) >= 9, "every shipped ICAR PDF must be indexed"
    assert stats["characters"] > 1_000_000
    assert all(d["pages"] > 1 for d in stats["documents"])


def test_every_pdf_has_a_citation_title():
    """No document may fall back to its filename as the citation."""
    names = {p.stem for p in fertilizer_rag.DATA_DIR.glob("*.pdf")}
    missing = names - set(fertilizer_rag.DOC_TITLES)
    assert not missing, f"add a DOC_TITLES entry for {sorted(missing)}"


def test_stale_cache_is_detected(monkeypatch):
    """A new or replaced PDF must rebuild, not serve yesterday's corpus."""
    assert fertilizer_rag._read_cache(), "the shipped cache must be current"
    real = fertilizer_rag._pdf_manifest
    manifest = dict(real())
    manifest["icar_added_after_cache.pdf"] = 1234
    monkeypatch.setattr(fertilizer_rag, "_pdf_manifest", lambda: manifest)
    assert fertilizer_rag._read_cache() is None


def test_search_returns_cited_hits():
    hits = fertilizer_rag.search("urea dose for rice nitrogen", k=3)
    assert len(hits) == 3
    for hit in hits:
        assert hit["title"], "every passage needs a document title"
        assert hit["page"], "every passage needs a page for the citation"
        assert len(hit["text"]) > 100


def test_advisory_without_an_llm_still_returns_evidence(monkeypatch):
    import chat

    def no_provider(*_a, **_k):
        raise RuntimeError("No LLM provider configured")

    monkeypatch.setattr(chat, "call_llm", no_provider)
    res = fertilizer_rag.advisory("Rice", "Loamy Soil", 25, 20, 15, 6.5, ["Urea"])
    assert res["advice"] is None
    assert res["note"], "the missing advisory must be explained, not hidden"
    assert res["sources"], "retrieval must still answer when the LLM cannot"
    assert all(s["page"] for s in res["sources"])


def test_endpoint_attaches_icar_context(client, monkeypatch):
    """The cosmetic match stays, and the ICAR evidence is added to the payload."""
    monkeypatch.setattr(
        fertilizer_rag, "advisory",
        lambda *a, **k: {
            "sources": [{"title": "ICAR test doc", "doc": "test", "page": 3,
                         "score": 0.4, "excerpt": "urea supplies nitrogen"}],
            "advice": "Apply urea in two splits.",
            "provider": "test", "note": None, "retrieval": "chromadb",
        },
    )
    body = client.post("/fertilizer/recommend", json={
        "crop": "Rice", "soil": "Loamy Soil",
        "N": 25, "P": 20, "K": 15, "PH": 6.5,
    }).json()
    assert body["recommended_fertilizers"], "the matcher must still answer"
    assert body["icar_advice"] == "Apply urea in two splits."
    assert body["icar_context"][0]["page"] == 3


def test_icar_endpoint_reports_corpus(client):
    body = client.get("/fertilizer/icar", params={"q": "potassium", "k": 2}).json()
    assert body["corpus"]["chunks"] > 200
    assert len(body["hits"]) == 2


def test_corpus_cache_is_json_and_addressable():
    """The cache is what the running service reads; it must stay plain JSON."""
    raw = json.loads(fertilizer_rag.CACHE_PATH.read_text(encoding="utf-8"))
    assert raw["version"] == fertilizer_rag.CACHE_VERSION
    assert raw["pdfs"], "the cache must record which PDFs it was built from"
    chunks = raw["chunks"]
    assert chunks and {"id", "doc", "title", "page", "text"} <= set(chunks[0])
    assert len({c["id"] for c in chunks}) == len(chunks), "chunk ids must be unique"
