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
MAX_PAGES = 30          # longer documents are cut to this many pages, and the report says so
SMALL_WORDS = {"the", "and", "per", "for", "with", "from", "number", "inside", "size", "two", "three", "six", "eight"}


class Choice(BaseModel):
    paper: int = Field(description="Number of the paper most likely to state the missing value, or -1 if none of them is")
    reason: str


class Choices(BaseModel):
    papers: list[int] = Field(description="Numbers of the papers most likely to state the missing value, best first. Empty if none is")
    reason: str


def key_words(text):
    """The words of a description that are worth searching for."""
    return [w for w in re.findall(r"[a-z][a-z\-]{2,}", text.lower()) if w not in SMALL_WORDS]


def search_inspire(evidence, query, size=CANDIDATES, sort="mostrecent"):
    """Papers on INSPIRE for `query` that have an arXiv version: [{title, abstract, arxiv, year}]."""
    response = evidence.fetch("https://inspirehep.net/api/literature", q=query, size=3 * size, sort=sort,
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


def pdf_text(content, max_pages=MAX_PAGES, words=()):
    """Text of a PDF with page markers. Returns (text, pages kept, pages in the document).

    A document longer than `max_pages` is cut. Without `words` the first pages are kept;
    with `words` the pages that mention them most, plus the first two.
    """
    import pymupdf
    with pymupdf.open(stream=content, filetype="pdf") as document:
        pages = [page.get_text() for page in document]
    keep = list(range(min(len(pages), max_pages)))
    if words and len(pages) > max_pages:
        hits = [sum(page.lower().count(w) for w in words) for page in pages]
        best = sorted(range(2, len(pages)), key=lambda i: -hits[i])[:max_pages - 2]
        keep = sorted({0, 1, *best})
    text = "\n".join(f"[page {i + 1}]\n{pages[i]}" for i in keep)
    return text, len(keep), len(pages)


def candidates(evidence, detector, what, query, broaden=False, fulltext=False, more_queries=(), offer=None):
    """Papers to choose from. `broaden` adds general searches for the detector, `fulltext`
    a search in the text of the papers; both are for queries that find little."""
    searches = [(query, "mostrecent"), *((q, "mostrecent") for q in more_queries)]
    if fulltext:
        words = " and ".join(f'fulltext:"{w}"' for w in key_words(what)[:3])
        searches.insert(0, (f'fulltext:"{detector}" and {words}', "mostrecent"))
    if broaden:
        searches += [(f"{detector} detector design", "mostcited"), (f"{detector} detector", "mostcited"),
                     (detector, "mostcited")]
    found, problems = {}, []
    for text, sort in searches:
        try:
            for paper in search_inspire(evidence, text, sort=sort):
                found.setdefault(paper["arxiv"], paper)
        except Exception as error:
            problems.append(f"{type(error).__name__}: {str(error)[:100]}")
    return list(found.values())[:offer or (12 if broaden or fulltext or more_queries else CANDIDATES)], problems


def research(evidence, detector, part, quantity, query, log=None, broaden=False, fulltext=False,
             select_pages=False, papers=1, more_queries=(), max_pages=MAX_PAGES, offer=None, model=MODEL):
    """Search for one missing item. Returns a dict describing what happened.

    `file` is the saved text of the best paper, `files` of all saved papers (up to `papers`).
    With `select_pages`, a long document is cut to the pages that mention the missing item.
    """
    result = {"part": part, "quantity": quantity, "query": query, "file": None, "files": [], "candidates": 0, "outcome": ""}
    known = _squash(" ".join(evidence.documents().values())[:20000])
    have = {s.get("arxiv") for s in evidence.sources()}
    offered, problems = candidates(evidence, detector, quantity, query, broaden, fulltext, more_queries, offer)
    offered = [p for p in offered if p["arxiv"] not in have and _squash(p["title"]) not in known]
    result["candidates"] = len(offered)
    if not offered:
        return {**result, "outcome": "the search found no new paper" + (f" ({problems[0]})" if problems else "")}
    listing = "\n\n".join(f"{i}. {p['title']} ({p['year']})\n   {p['abstract']}" for i, p in enumerate(offered))
    request = (f"We are building a geometry model of the detector: {detector}.\n"
               f"Missing: {quantity} of {part}.\n\nThese papers were found:\n\n{listing}\n\n"
               f"Which {'one is' if papers == 1 else f'are the {papers}'} most likely to state the missing value? "
               "Prefer papers that describe the design and construction of this detector over physics results, "
               "and papers about this detector over papers about other ones. Answer with one JSON object: "
               + ('{"paper": number or -1, "reason": "one sentence"}' if papers == 1 else
                  '{"papers": [numbers, best first], "reason": "one sentence"}'))
    try:
        choice, _ = call_llm_json(model, [{"role": "user", "content": request}], Choice if papers == 1 else Choices,
                                  log=log, stage="research_choose", temperature=0)
    except ValueError:
        return {**result, "outcome": "the model gave no usable choice"}
    chosen = [choice.paper] if papers == 1 else choice.papers[:papers]
    chosen = [i for i in chosen if 0 <= i < len(offered)]
    if not chosen:
        return {**result, "outcome": f"no paper chosen: {choice.reason}"}
    words = key_words(f"{part} {quantity}") if select_pages else ()
    for i in chosen:
        paper = offered[i]
        url = f"https://arxiv.org/pdf/{paper['arxiv']}"
        try:
            content = evidence.fetch(url).content
            text, read, total = pdf_text(content, max_pages, words)
        except Exception as error:
            result["outcome"] += f"could not get {url}: {type(error).__name__}: {str(error)[:150]}. "
            continue
        name = "arxiv_" + re.sub(r"[^0-9A-Za-z.]+", "_", paper["arxiv"])
        evidence.save(name + ".pdf", content, url, arxiv=paper["arxiv"], title=paper["title"])
        evidence.save(name + ".txt", text, url, arxiv=paper["arxiv"], title=paper["title"],
                      pages_read=read, pages=total, searched_for=f"{part}: {quantity}")
        result["files"].append(name + ".txt")
        if result["file"] is None:
            result.update(file=name + ".txt", title=paper["title"], url=url, pages_read=read, pages=total)
    if result["file"]:
        result["outcome"] = f"saved: {choice.reason}"
    return result
