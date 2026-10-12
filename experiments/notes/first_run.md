# First run on the 20 further papers (frozen, 2026-10-12)

Claim step and graph step as they were at commit 7413ae0, on `lbl/gpt-oss-120b` and `lbl/gemma-4`. Hand lists as of commit e376fef.
Per paper: `runs/papers20/<paper>/run1/compare.txt` (not in git). Rerun the comparison without model calls: `python experiments/first_run.py run1 --compare-only`.

```
Run 'run1' of the claim step and the graph step, code at commit 7413ae0, 2026-10-12 16:09
Found = share of the hand-listed entries. Claims on no list are not judged.

paper                split       pages claims  values: claims     graph  relations: claims     graph  notes
t2k_fgd              development    47    366      31/34  91% 29/34  85%         13/14  93% 11/14  79%  
xenonnt              development    32    402      26/34  76% 26/34  76%         10/13  77% 8/13  62%  
cuore_cryostat       development     8    217      15/17  88% 15/17  88%           8/9  89%  9/9 100%  
antares              development    86      0       0/36   0% 0/36   0%          0/16   0% 0/16   0%  ValueError: lbl/gpt-oss-120b gave no valid Extraction in 3 attempts
veritas              development    24    200      10/10 100% 10/10 100%           7/7 100%  7/7 100%  
TOTAL development                        1185     82/131  63% 80/131  61%         38/59  64% 35/59  59%

sno_plus             test           67    333      16/19  84% 16/19  84%          9/11  82% 9/11  82%  
snd_lhc              test           57    316      32/37  86% 30/37  81%         15/15 100% 14/15  93%  
lz                   test           28    317      17/20  85% 15/20  75%          9/12  75% 11/12  92%  
kamland_zen_balloon  test           25    348      21/23  91% 21/23  91%         10/10 100% 10/10 100%  
next_white           test           30    380      19/23  83% 19/23  83%         11/16  69% 10/16  62%  
next100              test           30      0       0/21   0% 0/21   0%          0/15   0% 0/15   0%  ValueError: lbl/gpt-oss-120b gave no valid Extraction in 3 attempts
hawc                 test           39    278      16/21  76% 15/21  71%           6/6 100%  6/6 100%  
swift_bat            test           18    265      18/21  86% 17/21  81%         11/11 100% 11/11 100%  
juno                 test           78    246      13/17  76% 13/17  76%           7/9  78%  7/9  78%  
cosine100            test           11    150      11/12  92% 10/12  83%           9/9 100%  9/9 100%  
pandax4t             test           11    159      14/15  93% 13/15  87%           8/9  89%  8/9  89%  
project8_phase2      test           29      0       0/12   0% 0/12   0%          0/10   0% 0/10   0%  ValueError: lbl/gpt-oss-120b gave no valid Extraction in 3 attempts
baikal_gvd           test            8    163      13/14  93% 13/14  93%           8/8 100%  7/8  88%  
supernemo_calo       test           26    319      30/30 100% 30/30 100%         11/15  73% 12/15  80%  
cta_sst              test            9    247      14/14 100% 13/14  93%          9/11  82% 9/11  82%  
TOTAL test                               3521    234/299  78% 225/299  75%       123/167  74% 123/167  74%

TOTAL all                                4706    316/430  73% 305/430  71%       161/226  71% 158/226  70%

```
