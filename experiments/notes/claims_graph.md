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
| 7 | c07_place_relations | A relation claim that says where something is may not be set aside as 'same as' a claim of another kind; text values become numbers | 94% | 93% | 100% | 87 of 923 | 2 | 2 | 28 | Scores unchanged. The rule did not bring 'LLAMA at the bottom of the cryostat' back: the model did not set that claim aside, it cited it on the node as support for 'inside', so the coverage check passed and the relation was still lost | The program must add such edges |
| 8 | c08_values_reviewed | A second model checks value by value, against its sentence, that it sits on the right part, and moves it if not | 94% | 93% | 100% | 104 of 923 | 1 | 0 | 26 | 14 values moved in five papers. About 8 moves are right (pad area to the pad, 24 PMTs to the PMT, 200 kg to the detectors), 3 are wrong (water as the material of the tank, 4 t of the whole upgrade to the SuperFGD) and for LEGEND it only swapped the two 6 t entries. Not a clear gain | Not kept |
| 9 | c09_place_edges | A claim that says where a part is always becomes an edge: where the model used it only to decide what is inside what, the program adds the edge | 89% | 98% | 100% | 141 of 923 | 1 | 1 | 25 | Worked: 44 of 45 relations; the program added 5 edges, among them 'LLAMA at the bottom of the cryostat' and 'reflector centred in the cryostat'. Values 57 of 64: three of the 'lost' ones were worked out by the model and kept only as the result ('7 x 5' modules as 35; 230 cm as 2.3 m, with the paper's other figure of 2.2 m set aside as contradicted). Sensible judgements, but the stated values were gone | Keep what is stated |
| 10 | c10_keep_stated | What a claim states stays in the graph as stated: a stated value is put back where the model kept only a derived one or dropped one of two that disagree | 94% | 91% | 100% | 98 of 923 | 2 | 3 | 23 | Worked: 60 of 64 values again; '7 x 5' put back beside 35, the 230 cm bar length kept beside 2.2 m as a conflict. Failed: the program added no place edges at all this time, so 'LLAMA at the bottom' was lost again. My mistake: a place claim counted as used if any edge cited it, and the model had cited it on a 'contains' edge | Fix the program |
| 11 | c11_place_edges_fixed | The program's check for place claims put right: such a claim counts as used only if an edge of the same kind cites it | 91% | 98% | 100% | 224 of 923 | 2 | 3 | 22 | Worked: 44 of 45 relations, the program added 6 edges (LEGEND: LLAMA at the bottom, reflector centred). Values 58 of 64: DUNE's '7 x 5' was again kept only as 35. The rule of round 10 did not fire because the model had also set the claim aside. Note: these graphs are from a second run of this round; I overwrote the first by mistake with a rerun, the scores were the same | Fix the rule |
| 12 | c12_restore_stated | No model call: the graphs of round 11 as the model built them, tidied again. A stated value is put back whenever the model used its claim only for a derived value, also if it set the claim aside as well | 94% | 98% | 100% | about 220 of 923 | 0 | 3 | 22 | 60 of 64 values, 44 of 45 relations, one root per detector, no claim unaccounted. Everything still missing is missing from the claims: three values never extracted, Super-K's hatches rejected by the cross-check, one IceCube relation not extracted. The graph step now passes on everything it receives | Chosen for the graph step |

Measured before round 5: the claims themselves hold 60 of 64 hand-listed values and 43 of 45 relations. The claim
step then got a second number check (each number against the claims of its own sentence, number words included),
which added for example the two hatches of Super-K.

## State

Twelve rounds. Chosen: the two-stage build with the program rules of rounds 5 to 12 (`build_in_two` with
`strict`, `one_root`, `keep_stated`). On the five papers: 60 of 64 hand-listed values, 44 of 45 relations, one
root per detector, every claim accounted for. The claims themselves hold 60 values and 43 relations, so the graph
step loses nothing and adds one relation by inference.

What these numbers do not show:
- Whether entries that are not on a hand list are right. By hand, LEGEND: the tree is right from the experiment
  down to the detectors; the 6 t of argon is still on the whole argon as well as on the inner volume.
- Stability: relations moved between 41 and 44 of 45 over rounds 6 to 11 with the same claims. The program rules
  removed most of that, but a different run of the model gives a different tree.
- Cost: 8 to 10 minutes of model time per paper, about 22 correction calls for five papers.
- No paper is held out, and the hand lists are mine.

Not kept: a second model reviewing the whole graph (not run), a second model moving values (round 8).
What limits the result now is the claim step.
