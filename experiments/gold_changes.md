# Changes to the hand lists after a run

Rule: an entry is added or changed only from the sentence in the paper, never because a reader produced it. Test papers
are corrected once, at the end. Scores are reported against the lists as they were (frozen) and as corrected.

## After run 1 (2026-10-12), development papers only

| Paper | Change | Why |
|---|---|---|
| t2k_fgd | key of "5 steel crossbars" narrowed to `crossbar` | false hit: it matched "five stainless steel straps" |
| t2k_fgd | key of "16 MPPCs per busboard" narrowed to `mppc` | false hit: it matched "Sixteen LEDs are also mounted on each busboard" |
| xenonnt | relation "liquid xenon surrounds the TPC" now needs `surrounds` from xenon to TPC | false hit: it matched "tpc contains liquid_xenon" |
| xenonnt | added 71 wire field electrodes, 48 PTFE panels, 24 PTFE pillars, 84 neutron veto PMTs, 5 wire grid electrodes | stated in the paper, missing from the list; noticed among the readers' claims, each confirmed in the text |
| cuore_cryostat | added suspension bar diameter 12 mm, Kevlar rope 6 mm, 5 pulse tubes, 4 copper connectors, 3 Minus-K insulators, more than 7 t of lead | stated in the paper, missing from the list |
| cuore_cryostat | object of "Y-beam stands on the main support plate" narrowed to `msp|main` | it also matched the tower support plate |
| all | the comparison now also counts a number that a relation claim carries ("xy_module consists of scintillator_bar (x192)") | false misses: T2K's 192 bars per layer was held this way |

Not changed, but known: the lists hold no materials at all, only numbers and relations.
