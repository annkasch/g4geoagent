"""Variants of the Research box for experiments/research_bench.py:
name -> function(evidence, detector, what is missing, log) -> result dict of research()."""

from pydantic import BaseModel

from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.research import MODEL, research


class Queries(BaseModel):
    queries: list[str]


def written_queries(evidence, detector, what, log):
    """Three short search queries written by a model that has seen the start of the starting paper."""
    start = " ".join(next(iter(evidence.documents().values())).split()[:1200])
    request = (f"We need a value that this paper does not give: {what} of the detector {detector}.\n\n"
               f"Start of the paper:\n{start}\n\n"
               "Write three short queries for a literature database (2 to 5 words each, no quotes) that would find "
               "a paper stating this value. Think about what the part is called elsewhere, and whether it was taken "
               "over from an earlier experiment or is described in a paper of its own. "
               'Answer with one JSON object: {"queries": ["...", "...", "..."]}')
    try:
        answer, _ = call_llm_json(MODEL, [{"role": "user", "content": request}], Queries, log=log,
                                  stage="research_queries", temperature=0)
        return [q for q in answer.queries if q.strip()][:3]
    except ValueError:
        return []


def variant(write_queries=False, **options):
    def run(evidence, detector, what, log):
        more = written_queries(evidence, detector, what, log) if write_queries else ()
        return research(evidence, detector, "the detector", what, f"{detector} {what}", log, more_queries=more, **options)
    return run


BEST = dict(broaden=True, fulltext=True, select_pages=True, papers=2)
VARIANTS = {
    "r01_baseline": variant(),
    # one change each
    "r02_broaden": variant(broaden=True),                 # also general searches for the detector, most cited first
    "r03_pages": variant(select_pages=True),              # long documents: keep the pages that mention the item
    "r04_fulltext": variant(fulltext=True),               # search inside the text of the papers
    # combinations of what helped
    "r05_broaden_pages": variant(broaden=True, select_pages=True),
    "r06_all_three": variant(broaden=True, fulltext=True, select_pages=True),
    "r07_two_papers": variant(**BEST),
    # from round 7, one change each
    "r08_three_papers": variant(**{**BEST, "papers": 3}),
    "r09_written_queries": variant(write_queries=True, **BEST),      # a model writes three more queries
    "r10_pages50": variant(max_pages=50, **BEST),
    # from round 10, one change each
    "r11_queries_offer20": variant(write_queries=True, max_pages=50, offer=20, **BEST),
    "r12_offer20": variant(max_pages=50, offer=20, **BEST),
    "r13_gemma_chooses": variant(max_pages=50, model="lbl/gemma-4", **BEST),
}
