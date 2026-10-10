# Research box: rounds of test, reflect, improve

Benchmark: `python experiments/research_bench.py <variant> --detail`. For each of the 36 hand-listed
facts of the LEGEND and T2K papers, Research is asked for the fact as if it were missing; the starting
paper is never offered again. Found = the saved text has a sentence with the value and the fact's key
word. This scores search and choice of paper, not reading.

| Round | Variant | Change | Found | Paper saved | What failed, what worked | Decision |
|---|---|---|---|---|---|---|
| 1 | r01_baseline | Query = detector name plus the missing item, newest papers first, model picks one, first 30 pages kept | 12/36 | 18/36 | Failed: for 18 facts no paper was saved, mostly because the search returns nothing for a long query (11 times) or offers too little to choose from (7 times). Facts in long documents are lost beyond page 30 (the T2K design report was found, the pad sizes were not). Once a paper about another apparatus was picked (CAGE for the LEGEND cryostat; it counted as found by accident). Worked: when design papers are offered, the model picks them (SuperFGD, TOF, HA-TPC) | Broaden the search, select pages, try full-text search |
| 2 | r02_broaden | Also general searches for the detector (design, detector, name alone), most cited first | 19/36 | 31/36 | Worked: a paper is now saved for 31 facts; the T2K design report is offered almost always. Failed: the design report is long and the fact lies beyond page 30 (7 T2K facts); for LEGEND no design paper exists among the offers and the model rightly declines (5 facts) | Keep |
| 3 | r03_pages | Long documents: keep the 30 pages that mention the missing item most | 13/36 | 18/36 | One fact more than the baseline. On its own it cannot help much, because the long documents are rarely offered without the broader search | Combine with round 2 |
| 4 | r04_fulltext | Search inside the text of the papers for the detector and the item's words | 19/36 | 33/36 | Worked: as many found as round 2 with fewer requests, and partly different facts | Combine all three |
| 5 | r05_broaden_pages | Rounds 2 and 3 together | 19/36 | 31/36 | No gain over round 2: the page selection did not bring the missing T2K facts in | Keep both, look at why |
| 6 | r06_all_three | Rounds 2, 3 and 4 together | 21/36 | 34/36 | Two more facts than either search alone | Keep |
| 7 | r07_two_papers | Round 6, and the model picks two papers | 26/36 | 36/36 | Worked: the largest single gain; a paper is saved for every fact. Failed: 5 LEGEND facts (water tank, PMTs, reflector, strings, shrouds), where the saved papers are about LEGEND-200 but not about its infrastructure, which was taken over from GERDA; 5 T2K facts where the design report is saved but the value is not matched, possibly written in other units. Cost: two papers to read per search | Best so far |
