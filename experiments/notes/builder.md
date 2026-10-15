# Team builder: CUORE's Shielding team, rounds

The builder (`agent/team_builder.py`, model `lbl/gemma-4`) writes a geometry specification (`agent/geometry_spec.py`)
from the team's brief (`experiments/team_walk.py input`), every sentence naming its parts, and a figure of the CUORE
cryostat given by the user (not from the paper: `runs/team/cuore_shielding/figure_cuore_section.png`). A program turns
the specification into GDML; Geant4 loads it, checks overlaps and weighs it.

Asked by the user 2026-10-14: iterate on the builder for this example until it is drastically more similar to the
figure, or for 10 rounds.

Judge (`experiments/builder_rounds.py`), seven checks against the paper and the figure:
1 no overlaps; 2 Roman Pb is a cup (outer radius 62-66 cm, inner 55-60 cm at mid-height, closed bottom 3-10 cm,
height 170-185 cm); 3 its mass within 30% of the stated 5 t; 4 Modern Pb is a solid slab (25-35 cm high, radius
30-50 cm); 5 Modern Pb inside the cup's cavity; 6 polyethylene and boric acid (they cover the external shield) not
built in the cryostat; 7 the 6 cm / 25 cm conflict raised with the Coordinator.
The modern lead's mass is not judged: from the stated radius 36 cm it is 1.4 t against "more than 2 t"; by the
agreed rule the builder keeps the stated value and reports the conflict.
Checked on a hand-written correct specification: 7 of 7 (`runs/team/cuore_shielding/hand`).

| Round | Change | Score | What the picture shows |
|---|---|---|---|
| 1 | first version: one call, repairs only on the specification check | 1 of 7 | Roman Pb a solid block with a cone-shaped hole (no step in the profile), 19.1 t; Modern Pb a 1 m column with a cone-shaped hole, 4.6 t, overlapping; polyethylene and "water" panels built around the cup. Raised the 6 / 25 cm conflict. |
| 2 | revision loop: after each attempt the builder gets Geant4's result (overlaps, mass of each part next to the stated mass), warnings on sloped profiles and the section picture next to the figure; up to 10 revisions, stops when the specification comes back unchanged. Unintended: the building blocks (cylinder, hollow cylinder, cup) were already in the schema the builder receives, and it used "cup". Fixed on the way: materials can be defined (density, formula); a geometry that cannot be written becomes feedback, not a crash | 4 of 7 (attempt 0: 4, last after 3 revisions: 4) | Roman Pb right: a cup 64 / 6 / 178 cm, 5.37 t. Modern Pb a cup 43 cm high, placed above the Roman cup (the builder took the cup to run from 0 to 178 cm, it is centred: -89 to 89 cm); height raised "to bring mass closer to the 2.0 t stated" - fitting a size to the mass, against the agreed rule; the feedback text invited it. The picture sent back was cut off at the bottom (my bug). Polyethylene and boric acid still built. Recognised the 70 t as the external shield's. |

Judge change after round 2: check 7 was "the 6 cm / 25 cm conflict raised"; the builder found the same conflict from the
masses (70 t vs 5 t). Now: "the external shield's facts kept off the Roman shield" (the questions or the reasons for
leaving out mention the external shield and one of its facts). Rounds 1 and 2 rescored: 1 and 4.
| 3 | one convention: every solid centred on its origin (profiles moved so that their z range is centred); the feedback lists where each round volume ends up (z range, outer radius); the section picture shows the whole height (it was cut off); the building blocks described in the instruction | 5 of 7 (every attempt; the 5th attempt failed: the model takes at most 4 pictures per request) | Roman Pb right. Modern Pb now inside the cup near its top, as in the figure, but a cup with a 30 cm wall (the stated "30 cm thick" read as a wall) and its height set "to bring mass closer to 2.0 t", then reported as "excellent agreement". Polyethylene and boric acid still built around the cup. |
| 4 | rules in the instruction: a mass is never a target (no size chosen or changed to fit a mass); a part given by a thickness and a radius with no hollow mentioned is a disk, its thickness its height. Infrastructure: only the figure and the newest picture are sent (limit of 4 pictures), model errors end the loop instead of crashing | 3 of 7 | The mass rule held: the modern lead's height is an estimate (60 cm), not fitted. The thickness rule did not: still a cup with a 30 cm wall, "open at the bottom, based on the figure", 1 cm above the Roman cup's rim (overlap). Polyethylene now a cup overlapping the Roman shield, explained away as "concentric shells". A rule buried in a long instruction does not change a shape decision that is made in passing. |
| 5 | shapes first: a call of its own decides, per part and from the figure, where the figure shows it, solid or hollow, the building block, the open end, and whether to build it; the specification must follow these decisions (program check) | 4 of 7 | Modern Pb now a solid slab with the stated sizes (36 cm, 30 cm), 1.39 t, and the conflict with "more than 2 tons" reported - as agreed. But placed above the cup (z = 110 cm, rim at 89 cm), although the feedback gave the cup's z range. Polyethylene built; boric acid as a 1 cm rod beside the cup; both overlap. |
| 6 | placement by the program: the shape step names, for a part inside another part's hollow, that part and where (top, bottom, centre); the program computes the position from the hollow and reports if it does not fit | 4 of 7 | Nothing was placed: the shape step left "inside which part" empty for every part. It calls the modern lead "a solid cyan block above the towers" but does not see that it is inside the Roman cup. Polyethylene now placed inside the Roman cup volume (overlap). |
