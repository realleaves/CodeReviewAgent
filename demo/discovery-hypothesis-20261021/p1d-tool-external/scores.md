# P1d static external-read smoke

| arm | eligible | candidate hits | fixed alarms | candidates | completed | calls | tool reads | external calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1/1 | 0 | 0 | 6 | 2/2 | 2 | 0 | 0 |
| tool_first_external | 1/1 | 0 | 0 | 5 | 2/2 | 2 | 6 | 6 |

Candidate hit = concrete reference root cause/symptom + valid trigger at the candidate stage. No evidence engine was run; extra findings are not automatic false positives.

Adjudicators: DeepSeek frozen-reference review; human review pending
