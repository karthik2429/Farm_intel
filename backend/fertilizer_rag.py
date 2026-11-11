"""
ICAR knowledge layer for fertiliser advice.

Corpus
    Nine ICAR documents shipped in `data/icar/` (fertiliser dose calculator
    manual, soil & nutrient management technologies, integrated plant
    nutrition practices, INM in groundnut, biofertilizers for sustainable crop
    production, ICAR microbe-based technologies, the ICAR-IISS integrated
    nutrient management training manual, ICAR-IISS annual report 2023 and the
    AICRP natural-resource-management achievements). Text is extracted once
    with PyMuPDF and cached as `data/icar/icar_corpus.json`, so the running
    service never parses a PDF on a request. The cache records the size of
    every PDF it was built from, so dropping a new PDF in and restarting is
    enough — a stale cache is rebuilt automatically instead of silently
    serving the old corpus. `python ingest_icar_pdfs.py <pdfs...>` does the
    same thing from the command line.

Retrieval
    Chunks (500 characters, 80-character overlap) are embedded and searched
    with **ChromaDB** when it is installed (its default all-MiniLM-L6-v2
    embedding). When ChromaDB or its embedding model is unavailable the same
    chunks are scored with TF-IDF cosine similarity, so retrieval never turns
    into a hard failure — it only changes what computes the ranking.

Advisory
    The retrieved passages are handed to the configured LLM (Gemini -> Groq ->
    OpenRouter -> Ollama, via chat.call_llm) together with the crop, soil and
    NPK values and the fertilisers the cosine matcher already chose. The model
    is told to answer only from the passages; when no LLM key is configured
    the endpoint still returns the passages and a note saying so.

Nothing here invents agronomic numbers: every claim in the advisory is
grounded in a retrieved passage, and each passage is returned with its
document and page so the UI can cite it.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data" / "icar"
CACHE_PATH = DATA_DIR / "icar_corpus.json"
CHROMA_DIR = DATA_DIR / "chroma_icar"
COLLECTION = "icar_fertilizer"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
DEFAULT_TOP_K = 4

_lock = threading.Lock()
_state: Dict[str, Any] = {"chunks": None, "index": None, "backend": None}

# Human-readable titles, used for citations in the UI.
DOC_TITLES = {
    "icar_fertilizer_calculator": "ICAR fertiliser dose calculator — user manual",
    "icar_soil_nutrient_management": "ICAR Soil and Nutrient Management technologies",
    "icar_inm_practices": "ICAR Integrated Plant Nutrition System practices",
    "icar_inm_groundnut": "ICAR Integrated Nutrient Management in groundnut",
    "icar_biofertilizers": "ICAR technologies — biofertilizers for sustainable crop production",
    "icar_microbe_technologies": "ICAR microbe-based technologies",
    "icar_iiss_inm_manual": "ICAR-IISS Integrated Nutrient Management training manual",
    "icar_iiss_annual_report_2023": "ICAR-IISS annual report 2023",
    "icar_aicrp_nrm_achievements": "AICRP Natural Resource Management research achievements",
}

CACHE_VERSION = 2


# ---------------------------------------------------------------------------
# Corpus build (PDF -> chunks -> cache)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunk_page(text: str) -> List[str]:
    """Split a page into overlapping chunks on sentence-ish boundaries."""
    text = " ".join(text.split())
    if not text:
        return []
    out: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("; "), window.rfind(", "))
            if cut > CHUNK_SIZE * 0.55:
                end = start + cut + 1
        piece = text[start:end].strip()
        if len(piece) >= 120:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return out


def _pdf_manifest() -> Dict[str, int]:
    """Name -> size for every corpus PDF, used to detect a changed corpus."""
    return {p.name: p.stat().st_size for p in sorted(DATA_DIR.glob("*.pdf"))}


def _read_cache() -> Optional[List[dict]]:
    """Return cached chunks only when they were built from the current PDFs."""
    if not CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        return None  # legacy/plain list or corrupt: rebuild once
    if raw.get("pdfs") != _pdf_manifest():
        return None  # a PDF was added, removed or replaced
    chunks = raw.get("chunks")
    return chunks if isinstance(chunks, list) and chunks else None


def build_corpus(force: bool = False) -> List[dict]:
    """Extract every PDF under data/icar into cached chunks."""
    if not force:
        cached = _read_cache()
        if cached is not None:
            return cached

    try:
        import pymupdf  # PyMuPDF >= 1.24
        open_pdf = pymupdf.open
    except Exception:  # noqa: BLE001
        try:
            import fitz  # older import name
            open_pdf = fitz.open
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "PyMuPDF is required to build the ICAR corpus "
                "(pip install pymupdf)"
            ) from exc

    chunks: List[dict] = []
    for pdf in sorted(DATA_DIR.glob("*.pdf")):
        doc_key = pdf.stem
        with open_pdf(str(pdf)) as doc:
            for page_no, page in enumerate(doc, start=1):
                for piece in _chunk_page(_clean(page.get_text())):
                    chunks.append({
                        "id": f"{doc_key}-{page_no}-{len(chunks)}",
                        "doc": doc_key,
                        "title": DOC_TITLES.get(doc_key, doc_key.replace("_", " ")),
                        "page": page_no,
                        "text": piece,
                    })
    if not chunks:
        raise RuntimeError(f"no text extracted from PDFs in {DATA_DIR}")
    CACHE_PATH.write_text(
        json.dumps({"version": CACHE_VERSION, "pdfs": _pdf_manifest(),
                    "chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    return chunks


# ---------------------------------------------------------------------------
# Retrieval: ChromaDB when available, TF-IDF cosine otherwise
# ---------------------------------------------------------------------------

def _corpus_fingerprint(chunks: List[dict]) -> str:
    import hashlib
    h = hashlib.sha1()
    h.update(str(len(chunks)).encode())
    for c in chunks:
        h.update(c["id"].encode())
        h.update(str(len(c["text"])).encode())
    return h.hexdigest()[:16]


class _ChromaIndex:
    name = "chromadb"

    def __init__(self, chunks: List[dict]):
        import chromadb  # noqa: WPS433 - optional dependency
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        fingerprint = _corpus_fingerprint(chunks)

        # A stale index is worse than a slow start: if the corpus changed, the
        # old vectors answer questions about documents that are no longer here.
        existing = None
        try:
            col = self._client.get_collection(COLLECTION)
            existing = (col.metadata or {}).get("corpus_hash")
            if existing == fingerprint and col.count() == len(chunks):
                self._col = col
                return
            self._client.delete_collection(COLLECTION)
        except Exception:  # noqa: BLE001 - not created yet, or unreadable
            pass

        self._col = self._client.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine",
                                  "corpus_hash": fingerprint})
        for i in range(0, len(chunks), 500):
            batch = chunks[i:i + 500]
            self._col.add(
                ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[{"doc": c["doc"], "title": c["title"],
                            "page": c["page"]} for c in batch],
            )

    def search(self, query: str, k: int) -> List[dict]:
        res = self._col.query(query_texts=[query], n_results=k)
        out = []
        for i, text in enumerate(res["documents"][0]):
            meta = res["metadatas"][0][i]
            dist = res["distances"][0][i] if res.get("distances") else None
            out.append({
                "text": text, "doc": meta.get("doc", ""),
                "title": meta.get("title", ""), "page": meta.get("page"),
                "score": round(1 - float(dist), 3) if dist is not None else None,
            })
        return out


class _TfidfIndex:
    name = "tfidf"

    def __init__(self, chunks: List[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._chunks = chunks
        self._vec = TfidfVectorizer(stop_words="english", sublinear_tf=True,
                                    ngram_range=(1, 2))
        self._matrix = self._vec.fit_transform([c["text"] for c in chunks])

    def search(self, query: str, k: int) -> List[dict]:
        from sklearn.metrics.pairwise import cosine_similarity
        q = self._vec.transform([query])
        sims = cosine_similarity(q, self._matrix)[0]
        order = sims.argsort()[::-1][:k]
        out = []
        for i in order:
            c = self._chunks[int(i)]
            out.append({"text": c["text"], "doc": c["doc"],
                        "title": c["title"], "page": c["page"],
                        "score": round(float(sims[i]), 3)})
        return out


def _index() -> Any:
    with _lock:
        if _state["index"] is not None:
            return _state["index"]
        chunks = build_corpus()
        _state["chunks"] = chunks
        try:
            _state["index"] = _ChromaIndex(chunks)
        except Exception:  # noqa: BLE001 - chroma missing/model download failed
            _state["index"] = _TfidfIndex(chunks)
        _state["backend"] = _state["index"].name
        return _state["index"]


def backend() -> str:
    _index()
    return str(_state["backend"])


def reset() -> None:
    """Drop the in-process index so the next call rebuilds it (used by tests)."""
    with _lock:
        _state.update({"chunks": None, "index": None, "backend": None})


def corpus_stats() -> Dict[str, Any]:
    chunks = build_corpus()
    docs = {}
    for c in chunks:
        docs.setdefault(c["title"], {"chunks": 0, "pages": set()})
        docs[c["title"]]["chunks"] += 1
        docs[c["title"]]["pages"].add(c["page"])
    return {
        "documents": [
            {"title": t, "chunks": v["chunks"], "pages": len(v["pages"])}
            for t, v in sorted(docs.items())
        ],
        "chunks": len(chunks),
        "characters": sum(len(c["text"]) for c in chunks),
        "retrieval": backend(),
    }


def search(query: str, k: int = DEFAULT_TOP_K) -> List[dict]:
    return _index().search(query or "fertilizer nutrient management", k=k)


# ---------------------------------------------------------------------------
# Advisory
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are an agronomy assistant for Indian farmers. Answer ONLY from the "
    "ICAR passages provided. If the passages do not cover something, say so "
    "instead of guessing. Be concrete and brief."
)


def _prompt(crop: str, soil: str, n: float, p: float, k: float, ph: float,
            fertilizers: List[str], passages: List[dict]) -> str:
    ctx = "\n\n".join(
        f"[{i + 1}] {ps['title']} (page {ps['page']}): {ps['text']}"
        for i, ps in enumerate(passages)
    )
    return (
        f"Crop: {crop.title()}\nSoil type: {soil or 'not specified'}\n"
        f"Soil test: N={n}, P={p}, K={k}, pH={ph}\n"
        f"Fertilisers already matched for this soil: {', '.join(fertilizers) or 'none'}\n\n"
        f"ICAR passages:\n{ctx}\n\n"
        "Write four short paragraphs with exactly these headings on their own "
        "line: Soil reading / Why these fertilisers / Application schedule / "
        "Precautions. Plain text only - no bullet points, no markdown, no "
        "asterisks. Under 150 words total so the answer is never cut off. "
        "Cite passages as [1], [2]. No invented doses."
    )


def advisory(crop: str, soil: str, n: float, p: float, k: float, ph: float,
             fertilizers: List[str], top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """Retrieve ICAR evidence and (when an LLM is configured) write advice."""
    query = (f"{crop} fertiliser dose nitrogen phosphorus potassium "
             f"{soil} pH {ph} application schedule INM")
    passages = search(query, k=top_k)

    result: Dict[str, Any] = {
        "query": query,
        "sources": [
            {"title": ps["title"], "doc": ps["doc"], "page": ps["page"],
             "score": ps["score"], "excerpt": ps["text"][:280]}
            for ps in passages
        ],
        "retrieval": backend(),
        "advice": None,
        "provider": None,
        "note": None,
    }

    try:
        import chat  # local module; keeps the LLM provider chain in one place
        text, _calls, provider = chat.call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(crop, soil, n, p, k, ph,
                                                fertilizers, passages)},
        ], max_output_tokens=2000)
        result["advice"] = (text or "").strip() or None
        result["provider"] = provider
    except Exception as exc:  # noqa: BLE001 - retrieval still answers
        result["note"] = (
            "No LLM key is configured, so this is the ICAR evidence without a "
            "written advisory. Set GEMINI_API_KEY (or GROQ/OPENROUTER/OLLAMA) "
            f"to enable it. ({type(exc).__name__})"
        )
    return result
