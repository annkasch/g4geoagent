# String test: can a LEGEND-200 string's arrangement be read from pictures?

Key: experiments/ceiling/legend200_string_key.md (from the reference code; grading only).
Pictures: evidence/legend_detector_unit/ (saved 2026-10-08, source of each not recorded).
NOT used: baseplate_large_public_mesh.png and baseplate_large_numbered.png: rendered from the reference's STL mesh, a leak.

## Round 1 (2026-10-16), gemma-4, one picture at a time, no text, seed 1
Script: experiments/ceiling/string_pictures.py. Answers: runs/ceiling/string_pictures/s1/.

| Key | Read from pictures | Grade |
|---|---|---|
| A1 12 strings, two radii | array render: "6-8 columns" | wrong |
| A2 units stacked vertically | string photo, array render | right |
| A3 unit pitch | "gap ~1/10 of detector height", no scale | ratio only |
| A4 3 rods at 120 deg | unit render, close-up: 3 at 120 deg; string photo: 4 rods | right in 2 of 3, pictures disagree |
| A5 order clamp/flap/PEN/insulator/detector | unit render: detector on plate; close-up (seen from below): plate "rests on the bottom face", tabs "on top of plate" | plate-under-detector right; finer order not seen; close-up inverted |
| A6 orientation | vertical axis; contact side not seen | partial |
| A7 LMFE and clamps | close-up: "copper tabs/clamps", not recognised as front end | miss |
| A8 cables | string photo: "suspension cable" | miss |
| A9 hanger/tristar at top | string photo: "translucent top cap" | partial |
| A10 nylon minishroud | not mentioned (white cylinders in the render read as detector units; whether the render shows shrouds is unclear) | miss |
| A11 HV and CC4 boards | not mentioned | miss |

About 2 right, 4 partial, 5 wrong or missed. The array render may show a design version, not as-built (string count differs). No absolute size anywhere: pictures give ratios only.
Single run, single seed; numbers move between runs.

## Round 2 (2026-10-16): text and picture reader together, seed 1
Script: experiments/ceiling/string_together.py. Answers: runs/ceiling/string_together/s1/.
Text reader (gpt-oss) lists parts from the paper passage (lines 110-160 of legend.txt: PEN supports, 12 strings, NMS,
LMFE, CC4, electroformed copper, fiber shrouds); picture reader (gemma-4) gets that list with each picture; text
reader merges and writes questions.

| Key | Round 1 (pictures alone) | Round 2 (with names) |
|---|---|---|
| A1 12 strings | "6-8" wrong | 12, but the number was in the list given: likely echoed |
| A2 stacked | right | right |
| A3 pitch | ratio | ratio |
| A4 3 rods at 120 deg | right in 2 pictures | lost: rods folded into "supports" |
| A5 order | plate under detector | LMFE under detector via the plate (close-up) right; unit render WRONG: germanium detector named "NMS", a gold pin named "detector" |
| A7 LMFE | miss | found in close-up (gold block under detector) |
| A8 cables | miss | close-up: thin wires from LMFE upwards (unnamed) |
| A9 hanger/tristar | partial | miss |
| A10 minishroud | miss | string photo: "around top 3 detectors", probably the dark detectors themselves; unsure |
| A11 CC4 boards | miss | array render: gold boards above strings, below top plate: right |

Merge step invented facts ("copper never touches the crystal", "strings hang from a bottom plate", "copper the only
metal") and put the wrong NMS reading under "all pictures agree". Its questions were useful: picture views to find
(full-length side view of a string, close-up of the shroud) and sizes the text lacks (detector height, pitch, NMS size).

Lessons: names let the picture reader find small parts (LMFE, CC4, cables); but forcing names makes it pin a name on
the wrong thing, numbers in the list get echoed, and facts it saw before (3 rods) get lost; the merge must not be free text.
