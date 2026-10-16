# edgegate matrix: edgegate.yaml, 3 repeats per cell

| cell | crashed | alive but under spec | time to crash | clean rate | clean power W | board RAM peak MB | RAM before crash | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline (rate 40, batch 1) | 0 / 3 | 0 / 3 | — | detections 39.271/s, errors 0.0/s | — | — | — | PASS |
| batch2 (the batch bug: crashes before emitting anything) | 3 / 3 | 0 / 3 | 1 s | — | — | — | — | FAIL |
| slow | 0 / 3 | 3 / 3 (metric_min:detections) | — | detections 9.918/s, errors 0.0/s | — | — | — | FAIL |
| flaky (dies at 2 s every time) | 3 / 3 | 0 / 3 | 2 s | — | — | — | — | FAIL |

A cell FAILS when its crash rate exceeds 0% or when any run failed its own gate ('alive but under spec': it ran the full window but missed a check such as a metric minimum). 'RAM before crash' is the pattern in the last 30 s of each crashed run: plateau, step (one excursion) or cycling (repeated large swings, typically an allocation that keeps failing).
