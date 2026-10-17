# Six-arm preference pilot

Measured September 30, 2026. [Machine-readable metrics](results/learning-six-arm-pilot.json). Uses the same 15 real saved pairwise choices and group split as the earlier [four-arm pilot](learning-pilot.md); no new feedback or independent evidence was created.

## Protocol and sensory modes

`group-holdout-v2`, split seed 784, 16 reviewed apartments: 13 training and 3 held out. Twelve comparisons train readouts and the experimental memory; three are evaluated. Every unique available gallery image is included: 202 images per spiking arm, 606 inference episodes across three arms, plus reinforcement episodes. Coverage is 100%.

Current inference uses **Pure Fly**. The twelve eligible saved reinforcement events retain their original **Cyborg** codec. The learned arm therefore measures transfer from Cyborg-conditioned memory to Pure sensory inputs. It is not a Pure-only conditioning study. The earlier four-arm pilot used Cyborg inference, explaining why its spiking scores are different. Comparing their accuracies does not isolate the effect of adding controls or changing plasticity.

Every arm uses the same training/test choices. Readout normalization is fitted only on the thirteen training apartments. The direct CLIP arm uses full 512-d stored image embeddings averaged over each unique gallery. KC→MBON rewiring uses seed 783 and 384,220 valid directed double-edge swaps. It preserves KC out-degree, MBON in-degree and per-KC weight multiset; other connections are unchanged. The report records the graph hash.

## Observed agreement

| Model                 | Correct comparisons | Agreement | Descriptive Wilson 95% interval |
| --------------------- | ------------------- | --------- | ------------------------------- |
| Price + distance      | 1 / 3               | 33.3%     | 6.2–79.2%                       |
| Direct CLIP + readout | 1 / 3               | 33.3%     | 6.2–79.2%                       |
| Rate + readout        | 1 / 3               | 33.3%     | 6.2–79.2%                       |
| Fixed LIF + readout   | 1 / 3               | 33.3%     | 6.2–79.2%                       |
| Learned LIF + readout | 1 / 3               | 33.3%     | 6.2–79.2%                       |
| Rewired LIF + readout | 1 / 3               | 33.3%     | 6.2–79.2%                       |

Learned-minus-fixed agreement is **0 percentage points**. All three test comparisons form **one connected comparison component**. Component bootstrap is unavailable; the Wilson intervals assume independence and remain descriptive. There are no individual binary ratings, so rating AUC and precision@k are unavailable. These results do not establish an improvement or reliable population performance.

## Resources and state

Total evaluation wall time: **512.59 seconds**. Per-photo LIF mean / p95: fixed **0.831 / 1.274 s**, learned **0.546 / 0.801 s**, rewired **0.666 / 1.136 s**. Measurements include ambient application use and are not a controlled hardware benchmark. Worker peak RSS was **128.4 MB**, a worker-lifetime high-water mark; it excludes API/CLIP/desktop processes.

The live saved checkpoint `2e7d8bc9c7f8…` and memory revision 15 were retained. Experimental weights were not published. Public JSON excludes apartment IDs, galleries and human label values; it contains numeric metrics and model source hashes. The next experiment must reserve new groups before feedback, keep the brief/mode fixed, collect diverse real choices and evaluate the frozen design.
