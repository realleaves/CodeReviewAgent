# P1 baseline vs hypothesis-first discovery

| arm | candidate hits | fixed alarms | discriminated | candidates | calls | completion tokens | tool reads | completed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1/6 | 0 | 1/6 | 29 | 21 | 8187 | 6 | 18/18 |
| hypothesis | 0/6 | 0 | 0/6 | 33 | 18 | 19165 | 0 | 18/18 |

Candidate hit = concrete reference root cause/symptom + valid trigger at the candidate stage. No evidence engine was run; extra findings are not automatic false positives.

Adjudicators: DeepSeek frozen-reference review; human review pending
