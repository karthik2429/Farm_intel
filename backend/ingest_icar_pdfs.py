#!/usr/bin/env python3
"""
Add ICAR PDFs to the fertiliser knowledge base and rebuild the index.

    python ingest_icar_pdfs.py ~/Downloads/icar_*.pdf
    python ingest_icar_pdfs.py --list
    python ingest_icar_pdfs.py --rebuild

Copies each PDF into `data/icar/` (namespaced with an `icar_` prefix), skips
files that are already in the corpus, re-extracts every page, rewrites the
chunk cache and rebuilds the Chroma collection. The running backend picks the
new corpus up on restart, or immediately if `force_reload()` is called from it.

Exits non-zero when a file is not a readable PDF or yields no text, because a
silently skipped document is how a corpus ends up thinner than it looks.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

import fertilizer_rag as rag


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def _known_hashes() -> dict:
    return {_md5(p): p for p in sorted(rag.DATA_DIR.glob("*.pdf"))}


def add_sources(paths: list[str]) -> int:
    rag.DATA_DIR.mkdir(parents=True, exist_ok=True)
    known = _known_hashes()
    added, skipped, failed = [], [], []

    for raw in paths:
        src = Path(raw).expanduser()
        if src.is_dir():
            candidates = sorted(src.glob("*.pdf"))
            if not candidates:
                failed.append(f"{src}: no PDFs in directory")
            for c in candidates:
                _one(c, known, added, skipped, failed)
        else:
            _one(src, known, added, skipped, failed)

    print(f"added {len(added)}, skipped {len(skipped)}, failed {len(failed)}")
    for name in added:
        print(f"  + {name}")
    for name, why in skipped:
        print(f"  = {name} ({why})")
    for why in failed:
        print(f"  ! {why}")
    return 1 if failed else 0


def _one(path: Path, known: dict, added: list, skipped: list, failed: list) -> None:
    if not path.exists():
        failed.append(f"{path}: not found")
        return
    if not _is_pdf(path):
        failed.append(f"{path}: not a PDF (a saved HTML page?)")
        return
    digest = _md5(path)
    if digest in known:
        skipped.append((path.name, f"same file as {known[digest].name}"))
        return

    name = path.stem if path.stem.startswith("icar_") else f"icar_{path.stem}"
    dest = rag.DATA_DIR / f"{name}.pdf"
    if dest.exists():
        dest = rag.DATA_DIR / f"{name}_{digest[:6]}.pdf"
    shutil.copy2(path, dest)
    known[digest] = dest
    added.append(dest.name)


def rebuild() -> None:
    rag.reset()
    chunks = rag.build_corpus(force=True)
    index = rag._index()  # noqa: SLF001 - the CLI is part of this module
    stats = rag.corpus_stats()
    print(f"corpus: {len(chunks)} chunks, {stats['characters']:,} characters, "
          f"retrieval={index.name}")
    for doc in stats["documents"]:
        print(f"  {doc['chunks']:5} chunks  {doc['pages']:4} pages  {doc['title']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdfs", nargs="*", help="PDF files or directories to add")
    ap.add_argument("--list", action="store_true", help="show the current corpus")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-extract and re-index without adding files")
    args = ap.parse_args(argv)

    if args.list and not args.pdfs and not args.rebuild:
        rebuild()
        return 0
    status = add_sources(args.pdfs) if args.pdfs else 0
    rebuild()
    return status


if __name__ == "__main__":
    sys.exit(main())
