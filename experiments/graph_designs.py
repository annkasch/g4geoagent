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
    # 5: design 4, and every entry that only one reader has is checked by the other reader against its sentence.
    #    Confirmed entries count as agreed, entries judged wrong are taken out and kept apart as disputed.
    "g05_cross_check": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT, "same_parts": "r2x",
                        "cross_check": "r2"},
    # 6: design 5, but the checker may put right the kind of a relation instead of rejecting it.
    "g06_cross_correct": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT, "same_parts": "r2c",
                          "cross_check": "r2c", "cross_options": {"correct": True}},
    # 7: design 6, and before the cross-check the numbers that no property covers, in and around the sentences
    #    the readers used, go back to one reader: a construction value that was missed?
    "g07_coverage": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT, "same_parts": "r2v",
                     "coverage": "r2", "cross_check": "r2v", "cross_options": {"correct": True}},
    # 8: design 7, and for every part of which the graph does not say where it is, the sentences that mention
    #    it go back to one reader, who gives the relation to another part if the document states one.
    "g08_placement": {"reading": "r2", "read_options": {"prompt": G.PROMPT_2}, **TOLERANT, "same_parts": "r2p",
                      "coverage": "r2", "placement": "r2", "cross_check": "r2p", "cross_options": {"correct": True}},
    # 9: design 7 with sharper instructions: the detector as a whole is a part, a vessel and its filling are two
    #    parts with a relation, a value in brackets belongs to what is named before it, tables and captions count,
    #    'each' only for parts that exist many times.
    "g09_instructions3": {"reading": "r3", "read_options": {"prompt": G.PROMPT_3}, **TOLERANT, "same_parts": "r3",
                          "coverage": "r3", "cross_check": "r3", "cross_options": {"correct": True}},
    # 10: design 9, and the figures of the paper that show the construction are read by one vision model.
    #     Their entries are marked "from a figure" and are not cross-checked.
    "g10_figures": {"reading": "r3", "read_options": {"prompt": G.PROMPT_3}, **TOLERANT, "same_parts": "r3f",
                    "coverage": "r3", "cross_check": "r3", "cross_options": {"correct": True}, "figures": "f1"},
    # 11: design 10, but a figure only adds to parts that the text names (features, relations between them).
    #     Parts that only a figure shows are kept apart as "seen only in figures".
    "g11_figures_extend": {"reading": "r3", "read_options": {"prompt": G.PROMPT_3},
                           "check_options": {"tolerant": True}, "merge_options": {"by_family": True, "figures_extend_only": True},
                           "same_parts": "r3", "coverage": "r3", "cross_check": "r3", "cross_options": {"correct": True}, "figures": "f1"},
    # 12: design 11, and each reader reads the text twice; the records of both passes are pooled before checking.
    "g12_two_passes": {"reading": "r3", "passes": 2, "read_options": {"prompt": G.PROMPT_3},
                       "check_options": {"tolerant": True}, "merge_options": {"by_family": True, "figures_extend_only": True},
                       "same_parts": "r3x2", "coverage": "r3x2", "cross_check": "r3x2", "cross_options": {"correct": True}, "figures": "f1"},
    # 13: design 12, and the checker is asked twice; an entry is taken out only if it is rejected both times.
    "g13_two_votes": {"reading": "r3", "passes": 2, "read_options": {"prompt": G.PROMPT_3},
                      "check_options": {"tolerant": True}, "merge_options": {"by_family": True, "figures_extend_only": True},
                      "same_parts": "r3v2", "coverage": "r3x2", "cross_check": "r3v2", "cross_options": {"correct": True, "votes": 2}, "figures": "f1"},
    # 14: design 13, and (a) a value written as text ("about 6 t") becomes the number with its unit and wording, so
    #     that the same value is not kept twice; (b) labels read from figures are offered when names are merged,
    #     so that "LAr cryostat" in a figure joins "cryostat" in the text and brings its features along.
    "g14_tidy": {"reading": "r3", "passes": 2, "read_options": {"prompt": G.PROMPT_3}, "check_options": {"tolerant": True},
                 "merge_options": {"by_family": True, "figures_extend_only": True, "tidy_values": True},
                 "same_parts": "r3t", "same_options": {"with_figures": True}, "coverage": "r3x2",
                 "cross_check": "r3v2", "cross_options": {"correct": True, "votes": 2}, "figures": "f1"},
}
