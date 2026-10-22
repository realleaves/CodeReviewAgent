# P2 mechanism audit smoke scores

| arm | eligible | hits | fixed alarms | findings | completed/failed | calls | prompt/completion tokens | removed/added/fallback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 2/2 | 0 | 0 | 6 | 4/0 | 4 | 13775/1730 | 0/0/0 |
| mechanism_audit | 2/2 | 0 | 0 | 7 | 4/0 | 8 | 34441/8198 | 0/0/1 |

do not expand or change the baseline default

A single smoke repetition cannot establish reproducibility or generalization.
Candidate hits do not measure valid evidence conversion; no evidence engine was run.
Removed/added counts compare path, line, category and title, not semantic mechanisms.
Semantic adjudication is by Codex against the frozen rubric; independent human review is pending.
