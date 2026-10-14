# G4GeoAgent: rules for working in this repository

## The one hard rule
Only free LBL-hosted models on CBorg (ids starting with `lbl/`). No paid model, for no purpose, until the user lifts this.
In use: `lbl/gpt-oss-120b` and `lbl/gemma-4` (the latter also for pictures). `agent/llm.py` refuses any other model
before a request is sent; do not set `G4GEO_ALLOW_PAID`.

## How the user wants to work (learned the hard way, 2026-10-10 to 12)
- Go through the system step by step **together**. Show the actual output of a step (claims, graph, picture) and say
  what is wrong with it before moving on. Do not run ahead and build several boxes unasked.
- Never present a shortcut as the system. One team instead of several, a cap on a loop, a source left out:
  say it first. No limits on loops, rounds or searches that the user or `PROPOSAL.md` did not set.
- A score is not the result. Twice a rising score hid a worse geometry. Look at the output itself, and say what a
  score does not measure.
- Judges before builders: do not tune a step against its own weak check.
- Answer questions directly and briefly, in plain words. Say what is not done.

## The diagram is the specification
- `g4geoagent/architecture.yaml` lists the boxes and arrows. `diagrams/architecture.py` draws it,
  `g4geoagent/pipeline.py` has one function per box, `tests/test_architecture.py` checks that they agree
  and that a run only moved along the arrows.
- A new component or connection goes into `architecture.yaml` first, then into the code. Tell the user
  about every change to boxes or arrows.
- A box marked `program` makes no model call.
- Each box has `first` (what its first version does) and `done` (how to tell it works). Keep them true.
- A box is `built` only when it does what the diagram and `PROPOSAL.md` say. If it works but falls short, it is
  `partial` and `differs` lists every way in which it falls short. Never mark a box `built` because a function
  with its name exists. Before building a box, read its section in `PROPOSAL.md` and build to that.
- A shortcut that changes the structure (one team instead of several, one shared script, a limit on a loop,
  a source left out) is not a detail. Say it before building it, and write it into `differs`.

## How a box is built
1. Give it a score that a program computes.
2. Test, look at what failed and what worked, change one thing, test again: 10 to 20 rounds.
   Keep the variants side by side and write one line per round in `experiments/notes/<box>.md`.
3. Choose the best variant. Develop on LEGEND and T2K; DUNE, IceCube and Super-K are only looked at
   as scores, to confirm the choice. Exception by the user's wish: the knowledge graph and the claims-to-graph
   step were tuned on all five papers, so nothing is held out for them.
4. More experiments, if these are too few: `../papers/geant4-experiment-repositories.md`. The list is
   not verified: cross-check paper against code before using an entry.

## Fixed decisions
- The agent works from documents and its own research. It never reads GitHub or other code hosts;
  `agent/evidence.py` holds the list of allowed sources.
- Public geometry code is the closest ground truth for grading during development. It is far more
  detailed than a build needs to be and is never the target.
- Research happens inside the teams, covers text and figures, and everything found is saved to the
  evidence folder and passes both Readers and Compare before it is used.

## Working without asking
Decide details yourself and report them. Stop and ask only before: using a paid model, publishing
something new, deleting the user's files, or changing what a box of the diagram is for.
Commit after each finished piece and push. Commits carry no co-author line.

## Where the work stands (2026-10-14)

The user and I are going through the pipeline from the start. **Done for now: from the paper to the detector graph and
its geometry view.** Next: the Coordinator, working from the geometry view. Everything after the graph (Research,
Coordinator, Build, Look, Evaluator) exists from an earlier, rushed pass and has NOT been redone on top of the graph.

| Step | Code | State |
|---|---|---|
| Step 1: PDF to text and figures | `agent/documents.py` | Works. Open: running page headers and words hyphenated at line ends are left in |
| Claim step, free readers (in use) | `agent/statements.py` | Each fact a plain sentence with a receipt (quote, numbers, parts, material, outer/inner); read in sections; cross-check may correct. All 20 papers: 99% of listed values, no paper fails |
| Claim step, old form readers | `agent/claims.py` | Kept for comparison; fails on long papers |
| Graph step | `agent/detector_graph.py` | One claim per sentence; long papers built in portions. All 20: 98% of listed values, 85% of relations in the graph, 7 min per graph |
| Geometry view | `detector_graph.geometry_view`, `experiments/view_run.py` | A model marks each part keep / collapse / drop. 1691 parts -> 1029 kept, almost nothing listed lost |
| Wiring into a run | `pipeline.py` | Not done: `graph_builder` is a stub there |

Runs: `python experiments/first_run.py <name> --free` (all 20 papers, comparison per paper in
`runs/papers20/<paper>/<name>/compare.txt`), then `python experiments/view_run.py <name>`. Latest: `free4`.
Records: `experiments/notes/free_reader.md` (all rounds and numbers), `experiments/notes/first_run.md` (frozen first run),
`experiments/gold_changes.md` (every change to the hand lists).

Known open faults, left on purpose for now: duplicate parts under several names in graphs of long papers (give each
portion the other names of existing parts); untidy values (a unit glued to a material); about a quarter of the
statements are true but not geometry; the error rate of statements is measured only on 40 (1 wrong, about 4 wrong
receipts); results move by one or two facts between runs; the test papers' hand lists are uncorrected.

Open decisions waiting for the user:
- Look: the user set 10 revisions per piece; implemented, never run to the end.
- Teams still build one after the other on one shared script; parallel teams with a real Integrate were announced,
  not built.
- Which public repository the Evaluator grades against per detector.
- The user's CBorg key shows $243.34 total spend that this project does not explain.

Earlier results to treat with care: the Build rounds (`notes/build.md`) chose variants by "claims met", which did
not see that the geometry was arranged wrongly. 3D pictures: `python -m g4geoagent.inspector.render3d`.

## Practical
- `source setup_env.sh` first. Runs go to `runs/` (not in git). `PROPOSAL.md` and `evidence/` are not in git.
- CBorg caches identical requests: use a different seed for an independent run.
- Check a change with `python tests/test_architecture.py [run folder]`.
- A model call takes one to two minutes; a benchmark over five papers 15 to 20. Run them in the background.
- `git push` sometimes drops the connection to GitHub; push again.
- Files in `runs/` are not in git. They hold the readers' saved answers that the benchmarks reuse
  (`runs/graph_bench/readings/`, `runs/claims_graph/claims_v3/`); without them a benchmark reads the papers again.
- The papers are in `../papers/` (PDF) and as text in `runs/papers_test/text/`.

## Development and test papers (decided 2026-10-12)

- Development (10): legend, T2K, dune, ice_cube, super-k, and of the 20 further papers t2k_fgd, antares, xenonnt, cuore_cryostat, veritas.
- Test (15): the other papers in `experiments/papers20.yaml` (field `split`). Hand lists: `experiments/gold/`, `experiments/gold_relations/`.
- The first run on all 20 is frozen and kept. On test papers look at total scores only, never at which entries were missed.
- Hand lists of test papers are corrected once, at the end, each change logged with its sentence. An entry is added only if the paper states it plainly.
- The lists measure what the system misses, not whether its other claims are right; extra claims are not counted as wrong.
