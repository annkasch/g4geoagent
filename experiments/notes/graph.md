# Knowledge graph: rounds of design, evaluation, reasoning, fix

Benchmark: `python experiments/graph_bench.py <design> --detail`, on all five papers with hand lists
(LEGEND, T2K, DUNE near detector, IceCube mDOM, Super-Kamiokande pages 3 to 7). No paper is held out here.
Scores by program against hand lists: 64 construction values (`experiments/gold`) and 45 relations
(`experiments/gold_relations`, listed by Claude on 2026-10-10, not checked by an expert).

values = hand-listed values present as a property; relations = hand-listed relations present as an edge;
placed = parts for which the graph says where they are; joined = parts in the largest group tied together by
relations; agreed = entries both readers found; dropped = records removed by the quote check;
doubles = pairs of parts whose names suggest one part twice.

What these scores do not measure: whether an entry in the graph that is not on a hand list is true.

| Round | Design | Change | Values | Relations | Placed | Joined | Agreed | Dropped | Doubles | What failed, what worked | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | g01_first | New template (parts, properties, relations with quotes), two readers, exact quote check, parts merged by shared names | 86% | 76% | 60% | 61% | 23% | 9% | 12 | Failed: materials almost never recorded; readers copy whole sentences and leave out reference marks, so good records are dropped; "sandwiched between" and "downstream of" have no relation type; counts in words and "N per M" missed; readers agree on little because the same statement gets different labels (contains, encloses, surrounds) | Fix check and merge first |
| 2 | g02_tolerant_family | Quote check ignores reference marks and cuts a failing quote to the part that is in the document; agreement by relation family and by same number on same part | 86% | 80% | 60% | 64% | 31% | 2% | 12 | Worked: almost nothing is dropped any more; four more relations. No model call needed | Keep |
| 3 | g03_instructions | New instructions for the readers: materials and counts are properties, relation "next to", sensors are attached to what they read out, short quotes | 86% | 91% | 60% | 73% | 37% | 2% | 19 | Worked: LEGEND and IceCube relations complete, T2K 9 of 10. Failed: values no better (other ones missed: number of cubes, pad sizes); some wrong entries appear (60000 "cubes" are readout channels; 12 "detectors" are strings); more parts under two names | Keep; merge names next |
| 4 | g04_same_parts | A model names parts that appear under two names; they become one part | 86% | 91% | 61% | 74% | 39% | 2% | 14 | Worked: framework, field cage, wavelength-shifting plate and others joined correctly; nothing joined wrongly in the five papers. The remaining "doubles" are mostly different parts with similar names (ND-GAr and its calorimeter) | Keep |
