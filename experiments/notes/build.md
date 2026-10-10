# Build box: rounds of test, reflect, improve

Benchmark: `python experiments/build_bench.py <variant> --seeds 2`. Fixed agreed claims of the LEGEND and
T2K papers (saved readings), so only building is tested. Four builds per variant.
Score: valid = loads in Geant4 without overlaps; claims met = share of the construction claims that a
program finds met in the geometry; facts met = the same for the hand-listed facts of the paper.

| Round | Variant | Change | Valid | Claims met | Facts met | What failed, what worked | Decision |
|---|---|---|---|---|---|---|---|
| 1 | v01_baseline | Prompt with the raw pyg4ometry calls, 6 attempts, gemma-4 | 0/4 | 0% | 0% | Failed: 3 to 5 attempts lost on materials (names that do not exist, an element defined twice, an element used as a material). When the script ran, repeated parts overlapped. Worked: the loop itself; scripts get further with each attempt. The two seeds gave the same answers, so a seed adds little | Fix materials first |
| 2 | v02_names | Valid Geant4 material names written into the instructions, plus how to turn an element into a material | 1/4 | 7% | 12% | Worked: material errors down to 0 to 2 attempts; first valid build (LEGEND, 220 volumes, 9 of 13 facts). Failed: overlaps of repeated parts in the other three; the feedback for an overlap is only a list of names, and the builder repeats the same mistake. The valid build showed only 9 of 24 claims; the rest (materials, liquid volumes) it neither showed nor listed as not built | Keep; fix overlap feedback next |
| 3 | v03_helper | `material()` helper from `g4geoagent.blueprint` in place of hand-written materials | 0/4 | 0% | 0% | Worked: material errors down to 1 to 2 attempts, and the helper's error message was understood. Failed: the same overlaps as in round 2 | Not better than round 2 on its own; test again with better overlap feedback |
| 4 | v04_names_overlap | Round 2 plus Geant4's own overlap messages as feedback (which part sticks out of which, by how much) | 2/4 | 14% | 25% | Worked: both LEGEND builds valid (140 and 220 volumes, 9 of 13 facts each). Failed: both T2K builds. T2K asks for 2 million cubes with fibres, which the builder places one by one; one message form ("completely encloses") was not parsed, so one run got feedback without detail | Best so far. Fix the parser; next: nesting rules, more attempts, other model |
| 5 | v05_helper_overlap | Round 3 plus the same overlap messages | 0/4 | 0% | 0% | Failed: overlaps the builder did not resolve; in LEGEND the same message came back unchanged twice. The helper removes material errors but brings nothing beyond round 4 | Drop the helper for now |
