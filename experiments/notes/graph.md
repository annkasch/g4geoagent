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
| 5 | g05_cross_check | Every entry only one reader has is checked by the other reader against its sentence; 'wrong' entries are taken out and kept apart | 86% | 87% | 53% | 59% | 92% | 2% | 14 | Worked: wrong entries go (12 'detectors' that are strings, chains of electronics read as attachments). Failed: 29 entries removed, among them true ones stated with the wrong kind of relation (huts 'in' the tank that stand on it), so relations and joined drop | Let the checker correct |
| 6 | g06_cross_correct | The checker may put right the kind of a relation instead of rejecting it | 86% | 89% | 56% | 63% | 92% | 2% | 14 | Worked: 12 relations corrected, nearly all sensibly (huts mounted on the tank, cameras attached to the support structure); 21 rejected. Values unchanged: the misses are numbers the readers never wrote down | Keep; go after missed numbers |
| 7 | g07_coverage | Before the cross-check, numbers that no property covers, in and around the sentences the readers used, go back to one reader | 91% | 87% | 57% | 62% | 94% | 2% | 14 | Worked: three more values (number of cubes, gas mixture, calibration devices). One relation fewer than round 6: the cross-check gives slightly different verdicts from run to run. Still missed: values in tables and captions (pad sizes), 'three fibres per cube', hatches | Keep |
| 8 | g08_placement | For every part without a stated place, the sentences that mention it go back to one reader | 91% | 87% | 60% | 61% | 94% | 2% | 14 | Little gain: 42 relations proposed, most rejected by the cross-check (58 disputed in all). Reading the LEGEND graph showed that 'placed' and 'joined' are low mainly because of small electronics parts that the papers never place, not because structure is missing | Drop |
| 9 | g09_instructions3 | Sharper instructions: the detector as a whole is a part, a vessel and its filling are two parts with a relation, a value in brackets belongs to what is named before it, tables and captions count, 'each' only for repeated parts | 88% | 96% | 62% | 75% | 91% | 1% | 13 | Worked: 43 of 45 relations; DUNE and Super-K complete; fewer and better-joined parts (117). Values 56 of 64, two fewer than round 7: T2K Micromegas sizes were missed this time. The values score moves by a few points between readings of the same paper | Keep; steady the reading |
| 10 | g10_figures | The figures that show the construction are read by one vision model and merged in | 88% | 91% | 63% | 68% | 79% | 1% | 21 | Scores on the hand lists unchanged. Worked: shapes the text never gives (cryostat with domed ends, a magnet yoke around the T2K detectors). Failed: 40 more parts, many of them noise (prototypes, 'gap', parts of the old detector), and more doubles | Restrict what figures may add |
| 11 | g11_figures_extend | A figure only adds to parts that the text names; parts only a figure shows are kept apart | 88% | 91% | 64% | 79% | 94% | 1% | 13 | Worked: the noise is gone, features and relations stay. Failed: a figure label that differs from the text's name ('LAr cryostat') is treated as a new part, so its features are lost | Keep; join labels to names |
| 12 | g12_two_passes | Each reader reads the text twice; the records are pooled before checking | 91% | 96% | 65% | 82% | 89% | 1% | 14 | Worked: 58 of 64 values, 43 of 45 relations, and the graph hangs together better. Cost: twice the reading | Keep |
| 13 | g13_two_votes | The checker is asked twice; an entry is taken out only if rejected both times | 91% | 96% | 66% | 82% | 90% | 1% | 14 | Reason: the cross-check gave two or three different verdicts per paper when run again, which moved scores by about two relations between runs. With two votes 31 entries are disputed instead of 38 | Keep |
| 14 | g14_tidy | A value written as text ('about 6 t') becomes number, unit and wording; labels from figures are offered when names are merged | 91% | 96% | 68% | 85% | 90% | 1% | 14 | Worked: the same value is no longer kept twice (LEGEND: 30 properties become 24); 'LAr cryostat' from the figure joins 'cryostat' and brings 'domed ends' | Chosen |

## Choice

**Design 14.** Per paper: each of the two readers reads the text twice with the three-record template; a
program checks every quote (ignoring reference marks, cutting a failing quote to the part that is in the
document); numbers left out go back to one reader; what only one reader has is checked by the other, twice,
and may be corrected; figures that show the construction add features and relations to parts the text names;
values are tidied; names that mean the same part are joined, with figure labels offered.

| | Design 1 | Design 14 |
|---|---|---|
| Hand-listed values in the graph | 55 of 64 | 58 of 64 |
| Hand-listed relations in the graph | 34 of 45 | 43 of 45 |
| Parts tied together by relations | 61% | 85% |
| Entries both readers back | 23% | 90% |
| Records lost to the quote check | 9% | 1% |

Still missed in every design: values in tables (T2K Micromegas sizes), "three fibres per cube", "seven strings",
the two hatches of Super-K, the Micromegas reading out the TPCs.

## What this does not show

- **Precision is not measured.** The hand lists say what must be in the graph, not whether the rest is true.
  Reading the LEGEND graph of design 14 by hand: of 30 relations about 28 are right; of 24 properties about 21
  (the 6 t of argon sits on the whole argon as well as on the inner volume; two fine-detail thicknesses).
- **No paper was held out.** All five were used to choose, as asked. How it does on a sixth is unknown.
- **The hand lists are mine** and not checked by a detector expert.
- **Figures are read by one model only,** and their entries are not cross-checked. One feature landed on the
  wrong part ("neck at the top" on the detector instead of the cryostat).
- **Scores move by about two relations between runs,** because the models do not answer identically each time.
