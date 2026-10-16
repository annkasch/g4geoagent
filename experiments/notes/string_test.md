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
| A10 nylon minishroud | array render: white cylinders called "detector units" | wrong, serious |
| A11 HV and CC4 boards | not mentioned | miss |

About 2 right, 4 partial, 5 wrong or missed. No absolute size anywhere: pictures give ratios only.
Single run, single seed; numbers move between runs.
