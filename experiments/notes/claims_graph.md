# From claims to the detector graph: rounds of test, reflect, improve

Benchmark: `python experiments/claims_graph_bench.py <variant> --detail`, on the five papers with hand lists.
The claims are the same for every variant (from the readings of graph design 14), so only the graph step is
compared. Scores: hand-listed values and relations present in the graph; parts joined into one structure;
and what the program checks found (claims left unaccounted, entries taken out as unsupported, repair rounds).

For comparison, the graph merged by a program from the same readings (graph design 14): values 91%, relations
96%, joined 85%.

| Round | Variant | Change | Values | Relations | Joined | Set aside | Unaccounted | Taken out | Repairs | What failed, what worked | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | c01_one_call | One model builds the whole graph from all claims; a program checks claim ids, numbers, relations, coverage and structure and sends problems back, up to 3 times | 83% | 98% | 93% | 473 of 958 | 0 | 0 | 4 | Worked: structure. One tree per detector; in LEGEND the strings sit inside the fibre shrouds inside the reflector, which the program merge never produced. No number without a claim. Failed: half the claims were set aside, many with the reason "used as property" although the property is not in the graph; materials set aside as "not geometry" | Constrain what "set aside" may mean |
| 2 | c02_reviewed | Round 1 plus a second model reviewing the graph against the claims | not run | | | | | | | Deferred: the faults of round 1 were visible without it, and a review adds a full round of calls | Later |
| 3 | c03_fixed_reasons | Five fixed reasons for setting a claim aside, checked by program ("same as" must name a claim that is in the graph; a size or material cannot be "not geometry"); materials are properties; the same fact under two names for the part is one claim | 91% | 93% | 92% | 98 of 914 | 19 | 0 | 15 | Worked: values back to 58 of 64; set-aside claims down to a tenth; LEGEND cryostat has its material and "domed ends". Failed: 19 claims still unaccounted after 3 repairs; slow, about 10 model minutes per paper, because every repair resends the whole graph | Split the work |
| 4 | c04_two_stages | Two stages: parts and arrangement first, then values in batches of 70 claims | 89% | 98% | 87% | 129 of 914 | 0 | 0 | 24 | Worked: every claim accounted for; 44 of 45 relations. Values 57 of 64, one fewer than round 3, within what changes from run to run. Not faster: 41 against 48 model minutes for five papers | Used as the default for now |

| 5 | c05_strict_tidy | The tree must follow relations that claims state (surrounds, encloses, contains); a built value is never 'not geometry'; a program keeps each value once per part with the wording, unit and each/total of its claim and copies shapes and features from the cited claims; value batches of 40 in parallel | 94% | 96% | 90% | 103 of 914 | 0 | 3 | 20 | Worked: all 60 hand-listed values that are in the claims are in the graphs, so the graph step loses none; 43 of 45 relations; LEGEND values appear once and keep 'about' and 'up to'; 'domed ends' is on the cryostat. Failed: the LEGEND tree fell apart, with 13 parts placed directly in 'world' (strings, nylon tubes, electronics). Round 3 had a good tree for the same claims: the structure varies a lot from run to run, and no score counted it | Count roots; allow one |
| 6 | c06_one_root | Claims with the per-sentence number check; only one node may be inside 'world'; 'A consists of B' puts B inside A | 94% | 93% | 100% | 137 of 923 | 25 | 2 | 21 | Worked: one root per detector (5 in all, where rounds 3 to 5 had 21 to 38), every part tied in. LEGEND reads as one tree down to the detectors inside the strings inside the fibre shrouds, with the electronics outside the tank. Failed: 'LLAMA at the bottom of the cryostat' was set aside as the same as 'cryostat contains LLAMA'; values given as text show as 'about about 6 t t'; DUNE left 25 claims unaccounted after all repairs | Keep; fix those two |

Measured before round 5: the claims themselves hold 60 of 64 hand-listed values and 43 of 45 relations. The claim
step then got a second number check (each number against the claims of its own sentence, number words included),
which added for example the two hatches of Super-K.

## State

Four rounds, not the ten to twenty that a box should get. No variant is clearly ahead of round 3 or 4, and the
differences between them are within the run-to-run noise. Not yet tried: the reviewing model, building large
detectors subsystem by subsystem, a second builder for stability.

By hand, LEGEND graph of round 3: the nesting is right down to the detectors. Wrong: the 6 t of argon is on the
whole argon as well as on the inner volume; the front-end electronics and amplifiers are placed inside the water
tank although the paper says only "outside the cryostat"; the wording "about" and "up to" was dropped from the
values.
