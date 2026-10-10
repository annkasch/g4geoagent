"""Turn PDF papers into text files, one per paper, with page markers.

    python -I experiments/pdf_to_text.py <folder with PDFs> <output folder>
"""

import sys
from pathlib import Path

import fitz   # pymupdf

source, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for pdf in sorted(source.glob("*.pdf")):
    with fitz.open(pdf) as document:
        pages = [page.get_text() for page in document]
    text = "\n".join(f"[page {i}]\n{page}" for i, page in enumerate(pages, 1))
    (out / f"{pdf.stem}.txt").write_text(text)
    print(f"{pdf.name:14s} {len(pages):3d} pages {len(text.split()):6d} words")
