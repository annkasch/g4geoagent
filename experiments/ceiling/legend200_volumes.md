# LEGEND-200 information-ceiling test: volumes a simplified build needs

Reference: legend-pygeom-l200 (public geometry, cloned 2026-10-16 to runs/ceiling/ref/, not in git).
Used ONLY to choose the volumes and to check values afterwards; the search sees the name "LEGEND-200" only.
"Ref source" = where the reference code itself says the number comes from.

| # | Volume | Material | Reference values (mm) | Ref source |
|---|---|---|---|---|
| 1 | Water tank | steel | inner r 5000, height 8900, wall 7 | none given |
| 2 | Reflective foil lining tank | VM2000 | 0.04 thick | none given |
| 3 | Water + air buffer at top | water / air | air layer 486 high | none given |
| 4 | Muon-veto PMTs | glass, steel cone | ~r 103 bulb; rings on floor, pillbox, wall (counts per ring) | none given |
| 5 | Pillbox (cryostat skirt) | steel | 12 thick, r = cryostat outer, cryostat 1280 above floor | Knoepfle2022 paper |
| 6 | Manhole in pillbox | - | r 400 | none given |
| 7 | Cryostat outer vessel | steel | ID 4160, cyl. 4149.2, wall 20, heads 862/870 | Knoepfle2022 + P. Krause |
| 8 | Insulation vacuum | vacuum | gap 80 | Knoepfle2022 |
| 9 | Cryostat inner vessel | steel | ID 3976, cyl. 3900, wall 12, heads 826/829 | Knoepfle2022 |
| 10 | Neck (inner/outer) | steel | ID 789 / 964, wall 10, height 1720 | Knoepfle2022 |
| 11 | Liquid argon | LAr | fills inner vessel | - |
| 12 | Argon gas in neck | GAr | 800 high | none given |
| 13 | WLS reflector | Cu 50 um, Tetratex 254 um, TPB 600 nm | diameter 1374, height 3000, top 1247 below neck | Krause thesis 2023, Araujo2022 |
| 14 | Array top plate | copper | 3 thick, shape from STL | CAD model |
| 15 | Array vertical position | - | from meter-drive readings | private (calibration readings) |
| 16 | Outer fiber barrel | PS fibers, TPB | 20 modules x 81 fibers, r 284, length 1630, bend r 155 | CAD model |
| 17 | Inner fiber barrel | PS fibers, TPB | 9 modules x 81 fibers, r 126, length 1400 | CAD model |
| 18 | SiPMs at fiber ends | Si | position 25 below top plate | "guessed from photos" |
| 19 | HPGe detectors | enriched Ge | per-detector shapes | private metadata (public geometry uses dummies) |
| 20 | String layout | - | string radius and angle per string | private channel map |
| 21 | String supports: copper rods (4/string), tristar, hanger, counterweight | copper | counterweight 513 high | rods partly "estimate from CAD", counterweight "estimated from photos" |
| 22 | Detector base plates | PEN | per detector | CAD |
| 23 | Minishrouds (tube + lid) | nylon | per string | email (A. Lubashevskiy, 2023) |
| 24 | Clamps, LMFE, cables | Ultem, Cu 0.076 x 2 | | partly given |
| 25 | Electronics boards (CC4, HV) | copper (simplified) | 100 x 25 x 62.5; 104.5 below plate | CAD |
| 26 | Calibration: tubes, sources, Cu absorbers | nylon, Cu | absorber 15 high, r 7 | drawing (S. Schönert), one "estimate!" |
| 27 | Fiber-shroud copper rings and rods | copper | r 127.5, rings at 7 heights | CAD |
