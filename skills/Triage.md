# Skill: triage
> Cluster errors, score severity, write structured learning entries.
> Invoke when repeated errors or failures are detected in logs.

## When to invoke
- Same error pattern appears 3+ times in today's log
- A file or function is mentioned repeatedly across ACT entries
- autoDream surfaces a recurring pitfall

## Phase 1: Cluster
Group related errors by:
- File or module affected
- Error type (syntax, runtime, logic, dependency)
- Frequency in today's log

## Phase 2: Score
Score each cluster across 3 dimensions (1-10 each):

| Dimension | Question |
|-----------|----------|
| Frequency | How often does this appear? |
| Impact | Does it block core functionality? |
| Trend | Getting worse, stable, or improving? |

Severity = (Frequency + Impact + Trend) / 3

## Phase 3: Write learning entries
For each cluster scoring above 5:

```json
{
  "type": "pitfall",
  "key": "2-5-word-kebab-description",
  "insight": "one sentence: what fails, why, what to watch",
  "confidence": 7,
  "source": "triage"
}
```

For clusters scoring below 5:
```json
{
  "type": "observation",
  "key": "minor-issue-description",
  "insight": "one sentence summary",
  "confidence": 4,
  "source": "triage"
}
```

## Phase 4: Surface
Output a triage summary:

```
TRIAGE SUMMARY — [date]
───────────────────────
HIGH (score 7+):   N clusters
MEDIUM (score 5-7): N clusters  
LOW (score <5):    N clusters

Top issue: [key] — [insight]
Action: [one recommended next step]
```

## Rules
- Never repeat a triage entry already in learnings.jsonl
- If the same key exists, update confidence score only
- Maximum 5 learning entries per triage run
- Triage runs silently — no output unless severity > 5
