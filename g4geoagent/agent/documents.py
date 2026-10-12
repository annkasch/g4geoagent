"""Step 1: from a PDF to what the readers get. Tools only, no model.

    python -m g4geoagent.agent.documents <paper.pdf> <output folder>

Writes into the folder:
    <name>.txt      the text, page by page, in reading order. Captions and tables are taken out of the
                    running text and put at the end of their page, marked [caption] and [table].
    figures/        every figure as a picture: stored pictures and figures drawn as lines alike
    figures/all_figures.jsonl   file, page and caption of each figure

Letters that PDF fonts damage are repaired: joined letters (fi, fl) are split, and mathematical letters
that come out as unrelated symbols are put back (200 followed by a Korean sign becomes 200 μ).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

# "Fig. 1." or "Figure 1:" starts a caption; "Fig. 3 presents ..." is a sentence of the text
CAPTION = re.compile(r"^\s*(Fig\.|Figure|FIG\.|Table|TABLE|Tab\.)\s*(\d+)\s*[.:|–—-]")
MIN_FIGURE = (90, 70)          # points: smaller groups of graphics are symbols and rules
JOIN = 10                      # points: graphics closer than this belong to one figure


def clean(text):
    """Repair letters that the PDF's fonts damaged."""
    out = []
    for ch in text:
        code = ord(ch)
        # mathematical letters (U+1D400 to U+1D7FF) whose first digit was lost show up as Korean signs
        if 0xD400 <= code <= 0xD7FF and unicodedata.name(chr(code + 0x10000), "").startswith("MATHEMATICAL"):
            ch = chr(code + 0x10000)
        out.append(ch)
    text = unicodedata.normalize("NFKC", "".join(out))      # ﬁ -> fi, mathematical letters -> plain letters
    return text.replace("­", "")                       # soft hyphens


def _clusters(page, tables):
    """Groups of graphics on a page that make up one figure each: [Rect]."""
    import pymupdf
    area = page.rect
    rects = [pymupdf.Rect(i["bbox"]) & area for i in page.get_image_info() if i["width"] > 30 and i["height"] > 30]
    for drawing in page.get_drawings():
        r = pymupdf.Rect(drawing["rect"]) & area
        if r.is_empty and r.width < 1 and r.height < 1:
            continue
        if r.width > 0.9 * area.width and r.height < 3:      # a rule across the page
            continue
        rects.append(r)
    rects = [r for r in rects if r.width * r.height < 0.85 * area.width * area.height]
    groups = []
    for r in rects:
        r = pymupdf.Rect(r)
        merged = True
        while merged:
            merged = False
            for g in groups:
                if (r + (-JOIN, -JOIN, JOIN, JOIN)).intersects(g):
                    r |= g
                    groups.remove(g)
                    merged = True
                    break
        groups.append(r)
    kept = [g for g in groups if g.width >= MIN_FIGURE[0] and g.height >= MIN_FIGURE[1]]
    return [g for g in kept if not any((g & t).get_area() > 0.5 * g.get_area() for t in tables)]


def read_pdf(pdf_path, folder):
    """Text, tables and figures of a PDF. Returns {"text": file name, "figures": [...], "tables": n, "pages": n}."""
    import pymupdf
    pdf_path, folder = Path(pdf_path), Path(folder)
    (folder / "figures").mkdir(parents=True, exist_ok=True)
    pages, figures, n_tables = [], [], 0
    with pymupdf.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            try:
                found = page.find_tables().tables
            except Exception:
                found = []
            table_boxes = [pymupdf.Rect(t.bbox) for t in found]
            body, captions = [], []
            for x0, y0, x1, y1, text, _, kind in page.get_text("blocks"):       # in the order of the PDF, which keeps columns apart
                box = pymupdf.Rect(x0, y0, x1, y1)
                if kind != 0 or not text.strip():
                    continue
                if any((box & t).get_area() > 0.6 * box.get_area() for t in table_boxes):
                    continue                                    # the words of a table come with the table
                text = clean(text).strip()
                if CAPTION.match(text):
                    captions.append((box, " ".join(text.split())))
                else:
                    body.append(text)
            lines = [f"[page {number}]", *body]
            lines += [f"[caption] {text}" for _, text in captions]
            for table, box in zip(found, table_boxes):
                rows = [" | ".join(clean(str(cell or "")).replace("\n", " ").strip() for cell in row) for row in table.extract()]
                rows = [r for r in rows if r.replace("|", "").strip()]
                if len(rows) < 2:
                    continue
                n_tables += 1
                near = min((c for c in captions if c[1].lower().startswith("tab")), key=lambda c: abs(c[0].y1 - box.y0), default=None)
                lines += [f"[table] {near[1] if near else ''}".rstrip(), *rows, "[end of table]"]
            pages.append("\n".join(lines))
            figure_captions = [c for c in captions if c[1].lower().startswith("fig")]
            # Each group of graphics gets the caption nearest to it: one that starts below it in the same column,
            # one beside it, or else one above it. Groups with the same caption are the panels of one figure and
            # are joined. Graphics with no caption near them (logos) are left out.
            def apart(c, g):
                if c[0].y0 < g.y1 and c[0].y1 > g.y0:                       # the caption stands beside the figure
                    return max(c[0].x0 - g.x1, g.x0 - c[0].x1, 0)
                sideways = 0 if min(c[0].x1, g.x1) - max(c[0].x0, g.x0) > 0.3 * min(c[0].width, g.width) else 1000
                return sideways + (c[0].y0 - g.y1 if c[0].y0 >= g.y1 - 8 else 300 + abs(c[0].y1 - g.y0))

            panels = {}
            for g in _clusters(page, table_boxes):
                nearest = min(range(len(figure_captions)), key=lambda j: apart(figure_captions[j], g), default=None)
                if nearest is not None and apart(figure_captions[nearest], g) < 420:
                    panels[nearest] = (panels[nearest] | g) if nearest in panels else pymupdf.Rect(g)
            for k, (j, group) in enumerate(sorted(panels.items(), key=lambda item: (item[1].y0, item[1].x0))):
                near = figure_captions[j]
                name = f"{pdf_path.stem}_p{number}_{k}.png"
                try:
                    clip = (group + (-4, -4, 4, 4)) & page.rect
                    page.get_pixmap(clip=clip, dpi=150, colorspace=pymupdf.csRGB, alpha=False).save(folder / "figures" / name)
                except Exception:
                    continue
                figures.append({"file": name, "page": number, "caption": (near[1] if near else "")[:600], "source": pdf_path.name,
                                "size_points": [round(group.width), round(group.height)]})
        n_pages = len(document)
    (folder / f"{pdf_path.stem}.txt").write_text("\n".join(pages) + "\n")
    with (folder / "figures" / "all_figures.jsonl").open("a") as f:
        f.writelines(json.dumps(figure) + "\n" for figure in figures)
    return {"text": f"{pdf_path.stem}.txt", "figures": figures, "tables": n_tables, "pages": n_pages}


if __name__ == "__main__":
    result = read_pdf(sys.argv[1], sys.argv[2])
    print(f"{result['pages']} pages, {len(result['figures'])} figures, {result['tables']} tables -> {sys.argv[2]}")
    for figure in result["figures"]:
        print(f"  {figure['file']}  page {figure['page']}  {figure['caption'][:110]}")
