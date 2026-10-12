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

## Where the work stands (2026-10-12)

The user and I restarted from the beginning of the pipeline and are working forward. Current position: **from the
paper to the detector graph**. Everything after the graph (Research, Coordinator, Build, Look, Evaluator) exists
from an earlier, rushed pass and has NOT been redone on top of the graph.

Drawn: `diagrams/claims_to_graph.png` (paper to graph, every model call, program step and tool; drawn by hand
from the code, not tested against it) and `diagrams/architecture.png` (the whole system, generated).

| Step | Code | State |
|---|---|---|
| Claim step: one claim per fact, with quote, sentence, page, checks | `agent/claims.py` (uses the readers and checks in `agent/graph.py`) | Works. Holds 61 of 64 hand-listed values and 43 of 45 relations |
| Graph step: a model builds the graph, a program checks it | `agent/detector_graph.py` | 11 rounds, see below. Not yet good enough for the user |
| Wiring into a run | `pipeline.py` | Not done: `graph_builder` is a stub there, the Coordinator still uses the old flat claims |

Graph step, last complete round (10, all five papers): values 94%, relations 91%, one root per detector, 2 claims
unaccounted. Round 11 (`c11_place_edges_fixed`, fixes a mistake of the program in adding place edges) was started
and **only two of five papers finished**; rerun it:
`python experiments/claims_graph_bench.py c10_keep_stated c11_place_edges_fixed --detail` (about 20 minutes).

Known faults of the graphs: LEGEND has "about 6 t" of argon on the whole argon and on the inner volume; the
fibre shrouds are beside the strings in the tree instead of around them; three values and two relations never
reach the claims; the cross-check wrongly rejected Super-K's two hatches; results move by one or two relations
between runs; a graph takes 8 to 10 minutes of model time per paper.

Tried and not kept: a program that merges records into the graph (the user's experience and the tests agree: a
model builds better structure); a second look for parts without a place; a model moving values between parts.

Records of every round: `experiments/notes/{graph,claims_graph,research,build}.md`.
Hand lists used as scores (written by Claude, not checked by an expert): `experiments/gold/` (64 values) and
`experiments/gold_relations/` (45 relations). Outputs to look at: `runs/claims_graph/claims_v3/<paper>/claims.txt`
and `runs/claims_graph/<variant>/<paper>/detector_graph.txt`.

Open decisions waiting for the user:
- Look: the user set 10 revisions per piece; implemented, never run to the end.
- Teams still build one after the other on one shared script; parallel teams with a real Integrate were announced,
  not built.
- Which public repository the Evaluator grades against per detector (LEGEND: `legend-exp/legend-pygeom-l200`, read
  as source text only; the user does not trust a GDML generated from it).
- The user's CBorg key shows $243.34 total spend that this project does not explain (its only paid calls were
  $0.066 in the smoke test of 2026-10-08).

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
