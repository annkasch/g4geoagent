# Coordinator: the build plan from the detector graph

Proposal 4.2 and 5.2; agreed with the user 2026-10-14. The coordinator does not change the layout. A model cuts the kept
tree of the geometry view into teams, names the main structures that are to be exact, confirms repeated parts and
objects to graph entries; a second call writes the interfaces. A program makes the tasks. Objections go to the graph
builder (`detector_graph.answer_objections`), the plan is made once more on its answer.

Run: `python experiments/coordinator_run.py free4 <variant> [--papers ...]`, on the graphs and views of run free4.
Output per paper: `runs/papers20/<paper>/free4/coordinator/<variant>/build_plan.txt`.
Development: cuore_cryostat, t2k_fgd, xenonnt, antares, veritas (LEGEND and T2K of the first five have no free4 view).

What the score can tell: every part owned, interfaces answered, values sourced or open, problems left after the
repairs. What it cannot tell: whether the teams are cut where the detector has subsystems, whether the envelopes
are the right spaces, whether the levels are right. That is read in build_plan.txt.

## Rounds

| Round | Variant | Change | What the plan shows |
|---|---|---|---|
| 1 | v01 | first version, gpt-oss-120b, both calls | CUORE: 5 teams, 4 interfaces, 12 of 12 interface values open, 0 objections. Faults: (a) no objection although the graph has visible errors (helium_gas made of PTFE, the external lead shield inside the polyethylene); (b) team 'detector' says it builds the tower support plate, but its roots do not include it, so the cryostat team gets it: the model does not see what its roots mean; (c) polyethylene_shielding and its lead shield are 'lumped' because the graph marked them small_part, and the coordinator can only raise main structures to exact; (d) helium_gas, a filling, is lumped with a mass gap; (e) cryostat 'inside' main_support_plate, so the interface asks for the inner size of a plate: the graph's containment is "hangs from" here |
| 1 | v01 | (other four papers) | Teams: t2k_fgd 16, xenonnt 15, antares 23, veritas 6 for 13 parts. The model makes nearly every child of the outermost part a team (VERITAS: a team for the opal glass diffuser alone). Interfaces into an abstract outermost part (xenonnt, veritas_telescope) have no sizes and stay open. Objections answered sensibly where they are about the tree (ANTARES recoverable_part moved into bss; 885 vs 900 modules kept, the paper says 885); objections to untidy values ('vacuum-insulated m') cannot be answered, since remove_value needs a quantity |
| 2 | v02 | prompt: a team is a subsystem with several parts, a single part is not a team, as few teams as needed | Hardly changes it: cuore 8 (one team per vessel now), t2k 15, xenonnt 10, antares 24, veritas 5. The model does not see what its roots amount to |
| 3 | v03 | the split check reports each team that ends up with one part (the prompt already says it is not a team) | Teams: cuore 3, t2k 7, xenonnt 11, antares 11, veritas 1. Fewer, but cut along the context: T2K gives the whole FGD (the paper's subject, 58 parts) to one team and spends six on ND280 parts the paper only mentions; CUORE now puts cryostat, lead shields and detector into one 'support' team. Interfaces carry every value of the inner parts (pressure ratings, densities, the 41 km cable to shore), not the space; only XENONnT TPC-in-inner-vessel is a real envelope (inner size derived from outer size and wall) |
| 4 | v04 | the tree shows for each part how many kept parts are inside it and how many values it has; prompt: cut where the work is | cuore 4 (platform and support / cryostat / 10 mK vessel with detector / external shield), xenonnt 5 (water tank, neutron veto, cryostat, TPC, rest), antares 8, veritas 3: plausible. T2K one team for 73 parts: the repair message for the lone outermost part ('give it to the team of the part it is in') has no answer for an outermost part, and the model merged everything |
| 5 | v05 | split: a separate repair message for an outermost part left alone (put it among the roots of the team inside it); interfaces: only sizes and positions in a length unit (program check); program: a repeat whose count no claim gives is not used | Unseeded: cuore 3, t2k 2, xenonnt 10, antares 9, veritas 3. Results move a lot between runs, so from here every variant runs with seeds 1 and 2 (`--seed`). Seeds 1/2: cuore 4/4 (support structure, cryostat, detector region, external shield, both seeds), veritas 3/3 (camera, mechanics, optics), t2k 6/6 (still spends teams on ND280 context, cuts the FGD only once), xenonnt 11/9 (teams for the plant: distillation, storage, kept by the view), antares 5/11. Interfaces now hold sizes only |
| - | - | program: a filling takes its vessel's level and has only a material gap (CUORE's helium was lumped with a mass gap) | no model change |
| 6 | v06 | levels: the model may set the level of any part, either way, with a reason (before: only main structures raised to exact) | Reasons sound: ANTARES glass sphere, mu-metal shield and optical gel exact; VERITAS mirror facets simplified; XENONnT PTFE reflectors and field electrodes no longer lumped. But it lists only changes and overlooks parts: CUORE seed 2 makes the 70 t external lead shield lumped and leaves the Roman lead and the 10 mK vessel simplified; seed 1 leaves the polyethylene shield lumped. Teams cuore 4/3, t2k 2/3, xenonnt 12/10, antares 8/7, veritas 3/3 |
| 7 | v07 | levels: one for every kept part, with a reason; the check reports parts without one | CUORE levels right in both seeds (lead shields, 10 mK vessel, tower plate, detector exact; the 70 t external shield no longer lumped). ANTARES overdoes exact (anchor, steel weights, pole): its sensitive PMTs are everywhere. But the split got worse: cuore 3/3 (no detector region), antares 6/1 (one team for 113 parts), t2k 6/6, xenonnt 10/7. The level list crowds out the split in the same answer |
| 8 | v08 | levels in a call of their own (split, levels, interfaces: one job each) | Levels: CUORE right in both seeds; ANTARES fewer wrong exact parts (anchor still exact in seed 1). T2K cuts the FGD out as its own team in both seeds (55/56 parts), the paper's subject; but single-part teams ecal and pi_zero remain in seed 1 after the repairs. Teams cuore 3/4, t2k 7/6, xenonnt 9/6, antares 11/9, veritas 1/3: the split still swings between seeds |
| 9 | v09 | model lbl/gemma-4 for the three calls instead of gpt-oss-120b | Much steadier: the split is nearly the same in both seeds on every paper, and a third of the time (1-4 min a paper). cuore 4/4 (platform and support, cryostat, detector suspension, external shield), t2k 6/7 (FGD its own team, 56 parts), xenonnt 7/7 (TPC, cryostat, neutron veto, muon veto, xenon handling, calibration), antares 7/7 (lines, bottom support, junction box, shore cable, interconnects), veritas 3/3 (mechanics, camera, optics). Levels: CUORE lead shields, plates near the detector, 10 mK vessel, tower plate exact. T2K: the outermost part stays a team of its own after three repairs: it holds the collapsed electronics, and every other part is in a subsystem |
| 10 | v10 | the outermost part may be a team of its own (it holds the teams together and carries the collapsed parts); a single inner part is still not a team | Same answers as round 9 (CBorg served the cached first answers), now with no problem left on any paper, both seeds |

## Choice

v10: gemma-4, three calls (split, levels, interfaces), the checks of rounds 3, 5, 7 and 10, fillings take their vessel's level.
Why: the only variant whose split is the same in two independent runs on all five papers, and it looks right on the
papers I read (CUORE, XENONnT, VERITAS, ANTARES); levels right on CUORE; T2K cuts the FGD out as its own team.

Still wrong or not looked at:
- T2K spends five teams on ND280 parts that the paper only mentions (magnet, ECAL, beamline); the view kept them.
  XENONnT has teams for the xenon plant (distillation, storage), also kept by the view. That is the view's job, not
  the coordinator's, but the coordinator plans them.
- CUORE's fourth team is the detector suspension (2 parts), not the detector region; the detector sits in the cryostat team.
- Interfaces into an abstract outermost part (ANTARES 'detector', XENONnT) carry the outer sizes of the inner parts,
  some of them not envelopes at all (ANTARES depth 2475 m, line spacing 60 m). Many values open: the papers give few
  inner sizes.
- T2K: 36 of 74 parts exact. For an FGD paper the FGD's insides are exact on purpose, but ECAL, TPC and pi-zero
  detector are exact only because they are sensitive.
- The graph builder's answers are read on five papers only; no measured error rate.

## Confirmation on the 15 test papers (scores only)

v10, seed 1: every paper gets a plan, no part without a team, 1 problem left (next_white). Teams 3 to 7. Small
detectors get several teams (swift_bat 14 parts: 5, next100 19: 6, baikal_gvd 11: 3); the proposal says a small
detector gets one team. Not settled: what 'small' is. Question for the user, not a limit I set.
