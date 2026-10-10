# G4GeoAgent: rules for working in this repository

## The one hard rule
Only free LBL-hosted models on CBorg (ids starting with `lbl/`). No paid model, for no purpose, until the user lifts this.

## The diagram is the specification
- `g4geoagent/architecture.yaml` lists the boxes and arrows. `diagrams/architecture.py` draws it,
  `g4geoagent/pipeline.py` has one function per box, `tests/test_architecture.py` checks that they agree
  and that a run only moved along the arrows.
- A new component or connection goes into `architecture.yaml` first, then into the code. Tell the user
  about every change to boxes or arrows.
- A box marked `program` makes no model call.
- Each box has `first` (what its first version does) and `done` (how to tell it works). Keep them true.

## How a box is built
1. Give it a score that a program computes.
2. Test, look at what failed and what worked, change one thing, test again: 10 to 20 rounds.
   Keep the variants side by side and write one line per round in `experiments/notes/<box>.md`.
3. Choose the best variant. Develop on LEGEND and T2K; DUNE, IceCube and Super-K are only looked at
   as scores, to confirm the choice.
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

## Practical
- `source setup_env.sh` first. Runs go to `runs/` (not in git). `PROPOSAL.md` and `evidence/` are not in git.
- CBorg caches identical requests: use a different seed for an independent run.
- Check a change with `python tests/test_architecture.py [run folder]`.
