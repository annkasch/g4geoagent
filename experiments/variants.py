"""Reader variants for experiments/reader_bench.py: name -> function(documents, log) -> Reading."""

from g4geoagent.agent import readers
from g4geoagent.agent.compare import _squash, claim_numbers
from g4geoagent.agent.schemas import Reading


def union(*readings):
    """All claims of several readings, without exact repeats."""
    seen, claims, parts = set(), [], {}
    for reading in readings:
        for part in reading.parts:
            parts.setdefault(part.name, part)
        for claim in reading.claims:
            key = (tuple(claim_numbers(claim)), _squash(claim.quote), claim.category == "not_geometry")
            if key not in seen:
                seen.add(key)
                claims.append(claim)
    return Reading(parts=list(parts.values()), claims=claims, gaps=[g for r in readings for g in r.gaps])


def both(documents, log, **options):
    return [readers.read_paper(documents, name, log, **options) for name in "AB"]


def agreed(documents, log, **options):
    from g4geoagent.agent.agree import agreed_reading
    keep_disputed = options.pop("keep_disputed", False)
    result = agreed_reading(documents, log, **options)
    if keep_disputed:
        result.reading.claims += result.disputed
    return result.reading


VARIANTS = {
    # the pipeline: repair failing quotes, pair up the readers, cross-check what only one has
    "agreed": agreed,                                             # disputed claims are left out
    "agreed_keep": lambda d, log: agreed(d, log, keep_disputed=True),   # disputed claims are kept (and flagged)
    "repaired_union": lambda d, log: agreed(d, log, check=False),       # no cross-check
    # one reader, and both without pairing
    "A": lambda d, log: readers.read_paper(d, "A", log),
    "B": lambda d, log: readers.read_paper(d, "B", log),
    "A_no_verdicts": lambda d, log: readers.read_paper(d, "A", log, coverage=False),
    "B_no_verdicts": lambda d, log: readers.read_paper(d, "B", log, coverage=False),
    "union": lambda d, log: union(*both(d, log)),
    # ways to find more
    "union_pieces": lambda d, log: union(*both(d, log, whole_limit=0)),          # always read in pieces
    "union_window3": lambda d, log: union(*both(d, log, window=3)),              # verdicts on a wider neighbourhood
    "union_pieces_window3": lambda d, log: union(*both(d, log, whole_limit=0, window=3)),
}
