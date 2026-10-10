"""Designs of the knowledge graph for experiments/graph_bench.py.

A design names its reading set-up (`reading`: the readers' raw answers are kept under that name and
shared by every design that uses it), whether figures are read, and options for checking and merging.
"""

from g4geoagent.agent import graph as G

TOLERANT = {"check_options": {"tolerant": True}, "merge_options": {"by_family": True}}
DESIGNS = {
    # 1: the first template, two readers, quotes checked word for word, parts merged by shared names. Text only.
    "g01_first": {"reading": "r1"},
    # 2: same readings. Quote check ignores reference marks and cuts a failing quote down to the part that is
    #    in the document. Two readers agree when they state the same number on the same part, or relations of
    #    the same family (contains / encloses / surrounds / consists of; mounted on / attached to).
    "g02_tolerant_family": {"reading": "r1", "check_options": {"tolerant": True}, "merge_options": {"by_family": True}},
    # 3: design 2 with new instructions for the readers: materials and counts are properties (also counts in words,
    #    "N per M", arrays), a relation "next to", sensors are attached to what they read out, short quotes.
    "g03_instructions": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT},
    # 4: design 3, and a model names the parts that appear under two names; they become one part.
    "g04_same_parts": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT, "same_parts": "r2"},
}
