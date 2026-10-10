"""Research: look online for one missing value or part and save what is found.

First version: INSPIRE is searched, a model picks the paper most likely to hold
the answer, and its arXiv PDF is saved as text. Figures stay in the saved PDF
and are not read yet.
"""

import re

from pydantic import BaseModel, Field

from g4geoagent.agent.compare import _squash
from g4geoagent.agent.llm import call_llm_json

MODEL = "lbl/gpt-oss-120b"
CANDIDATES = 8
MAX_PAGES = 30          # longer documents are cut here, and the report says so


class Choice(BaseModel):
    paper: int = Field(description="Number of the paper most likely to state the missing value, or -1 if none of them is")
    reason: str


def search_inspire(evidence, query, size=CANDIDATES):
    """Papers on INSPIRE for `query` that have an arXiv version: [{title, abstract, arxiv, year}]."""
    response = evidence.fetch("https://inspirehep.net/api/literature", q=query, size=3 * size, sort="mostrecent",
                              fields="titles,abstracts,arxiv_eprints,earliest_date")
    papers = []
    for hit in response.json()["hits"]["hits"]:
        data = hit["metadata"]
        if not data.get("arxiv_eprints") or not data.get("titles"):
            continue
        abstract = (data.get("abstracts") or [{}])[0].get("value", "")
        papers.append({"title": data["titles"][0]["title"], "abstract": " ".join(abstract.split())[:900],
                       "arxiv": data["arxiv_eprints"][0]["value"], "year": data.get("earliest_date", "")[:4]})
    return papers[:size]


def pdf_text(content, max_pages=MAX_PAGES):
    """Text of a PDF with page markers. Returns (text, pages read, pages in the document)."""
    import pymupdf
    with pymupdf.open(stream=content, filetype="pdf") as document:
        pages = [page.get_text() for page in document]
    text = "\n".join(f"[page {i}]\n{page}" for i, page in enumerate(pages[:max_pages], 1))
    return text, min(len(pages), max_pages), len(pages)


def research(evidence, detector, part, quantity, query, log=None):
    """Search for one missing item. Returns a dict describing what happened; `file` is the saved text or None."""
    result = {"part": part, "quantity": quantity, "query": query, "file": None, "candidates": 0, "outcome": ""}
    known = _squash(" ".join(evidence.documents().values())[:20000])
    have = {s.get("arxiv") for s in evidence.sources()}
    try:
        papers = [p for p in search_inspire(evidence, query)
                  if p["arxiv"] not in have and _squash(p["title"]) not in known]
    except Exception as error:
        return {**result, "outcome": f"search failed: {type(error).__name__}: {str(error)[:150]}"}
    result["candidates"] = len(papers)
    if not papers:
        return {**result, "outcome": "the search found no new paper"}
    listing = "\n\n".join(f"{i}. {p['title']} ({p['year']})\n   {p['abstract']}" for i, p in enumerate(papers))
    request = (f"We are building a geometry model of the detector: {detector}.\n"
               f"Missing: {quantity} of {part}.\n\nThese papers were found:\n\n{listing}\n\n"
               "Which one is most likely to state the missing value? Prefer papers that describe the design "
               "and construction of this detector over physics results. Answer with one JSON object: "
               '{"paper": number or -1, "reason": "one sentence"}')
    try:
        choice, _ = call_llm_json(MODEL, [{"role": "user", "content": request}], Choice, log=log,
                                  stage="research_choose", temperature=0)
    except ValueError:
        return {**result, "outcome": "the model gave no usable choice"}
    if not 0 <= choice.paper < len(papers):
        return {**result, "outcome": f"no paper chosen: {choice.reason}"}
    paper = papers[choice.paper]
    url = f"https://arxiv.org/pdf/{paper['arxiv']}"
    try:
        content = evidence.fetch(url).content
        text, read, total = pdf_text(content)
    except Exception as error:
        return {**result, "outcome": f"could not get {url}: {type(error).__name__}: {str(error)[:150]}"}
    name = "arxiv_" + re.sub(r"[^0-9A-Za-z.]+", "_", paper["arxiv"])
    evidence.save(name + ".pdf", content, url, arxiv=paper["arxiv"], title=paper["title"])
    evidence.save(name + ".txt", text, url, arxiv=paper["arxiv"], title=paper["title"],
                  pages_read=read, pages=total, searched_for=f"{part}: {quantity}")
    return {**result, "file": name + ".txt", "title": paper["title"], "url": url, "pages_read": read,
            "pages": total, "outcome": f"saved: {choice.reason}"}
