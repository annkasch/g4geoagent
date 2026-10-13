# Free readers (agent/statements.py), 2026-10-12

A reader writes each fact as a plain sentence with a receipt (quote, numbers with units, parts, material, outer / inner),
reads in sections of about 14,000 characters, and the cross-check may put a statement right. The old readers
(agent/claims.py) are unchanged beside it. Run: `python experiments/first_run.py <name> --free`.

| Round | Change | Development papers: values in claims / relations in claims / relations in graph |
|---|---|---|
| old readers (run1) | | 95 of 142 / 37 of 59 / 34 |
| free1 | first version, CUORE only | 22 of 23 / 8 of 9 / 6 |
| free2 | a statement keeps the numbers its quote holds; one fact per sentence; names are not numbers | 137 / 51 / 40 |
| free3 | which words mean "inside"; facts of the abstract and introduction count | 142 / 54 / 41 |

All 20 papers, free3 (code f2dbcc7), against the frozen run of the old readers:

| | Old readers | Free readers |
|---|---|---|
| Papers that gave nothing | 3 | 0 (155 sections read, none failed) |
| Values in the claims | 316 of 430 (73%) | 436 of 441 (99%) |
| Values in the graph | 305 (71%) | 432 (98%) |
| Relations in the claims | 161 of 226 (71%) | 209 (92%) |
| Relations in the graph | 158 (70%) | 171 (76%) |
| Test papers only: values / relations in the graph | 75% / 74% | 97% / 78% |

Per paper: `runs/papers20/<paper>/free3/compare.txt`; table: `runs/papers20/free3_summary.txt`.

What is still wrong (2026-10-12):
- The graph step does not cope with long papers: 489 claims unaccounted on five papers (ANTARES 219, T2K FGD 124, SNO+ 88,
  SND@LHC 53, JUNO 5), 20 to 58 minutes per graph, up to 39 repair rounds. It was built for 200 to 400 claims.
- Of 48 listed relations that are in the claims but not in the graph: 19 are in the tree (one part inside the other) without
  an edge, so only the comparison misses them; 20 have both parts as nodes with nothing joining them; 9 lack a node.
- 40 random statements of four development papers judged against the text: 1 wrong (marked by the reader as its own
  conclusion), 2 could not be checked, about 4 with a wrong receipt (a company as material, "mounted on" given as inside),
  about 10 true but not about the built detector (location, assembly steps, electronics, a year).
- The rule for construction numbers takes a year (no unit) and a wavelength in nm as construction values.
- 6282 different sentences become 11277 claims, because a sentence is split by number and relation.
- Not measured: what the second reading pass adds; the error rate on more than 40 statements.
