# heartbeat

> Your harness. Your memory.

Anthropic built KAIROS — an always-on background agent — into 
Claude Code and never told anyone. The leak revealed it.

Then they launched Claude Managed Agents: the same pattern, 
locked behind their API at $0.08/hour. Your memory. Their servers.

heartbeat is the open version.

Runs on your machine. Model-agnostic. Zero vendor lock-in.
Your learnings stay in `.heartbeat/learnings.jsonl` — a file 
you own, you read, you export, you take anywhere.

Every N seconds, one question:
> "Anything worth doing right now?"

If yes — it acts. If no — it waits.

> Every other open harness waits for you.  
> heartbeat doesn't

---

## What it does

```
tick #1  → [WAIT] No open issues or stale files detected
tick #2  → [WAIT] Tests passing, no action needed
tick #3  → [ACT]  Found TODO in auth.py from 3 weeks ago — flagged in memory
tick #4  → [WAIT] Nothing urgent
...
[night]  → autoDream: consolidating memory from today's observations
```

- Runs silently in the background
- Reads your project context (CLAUDE.md, README.md, or custom file)
- Decides autonomously whether to act each tick
- Keeps append-only daily logs — it cannot erase its own history
- Runs **autoDream** once per day: consolidates memory, removes contradictions, compresses observations

---

## Install

```bash
git clone https://github.com/YOUR_USERNAME/heartbeat
cd heartbeat
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
```

## Run

```bash
# Default: 30-second ticks
python heartbeat.py

# Show what the agent has learned across sessions
python heartbeat.py --learn

# Custom interval and context
python heartbeat.py --interval 60 --context my_project_context.md
```

**3. File structure — update the memory line:**
```markdown
└── .heartbeat/
    ├── memory/
    │   └── learnings.jsonl  ← structured learnings, one entry per action
    └── logs/
        └── 2026-04-12.log
```
## Architecture

Fat skills on top — learnings.jsonl encodes what 
the agent discovered. Structured, searchable, yours.

Thin harness in the middle — heartbeat.py, ~200 lines.
JSON in, text out. Read-only by default.

Your project on the bottom — CLAUDE.md, README.md, 
or any context file. The deterministic foundation.

Push intelligence up into learnings.
Push execution down into your existing project files.
Keep the harness thin.

Every model improvement automatically improves every tick.


## The KAIROS architecture

From the leaked Claude Code source (512,000 lines, March 31 2026):

```
KAIROS receives periodic <tick> prompts and decides independently
whether to act. It has three tools normal Claude Code never sees:
push notifications, file delivery, and GitHub PR subscriptions.
At night it runs autoDream — memory consolidation while you sleep.
```

`heartbeat` implements the core loop:

```
while True:
    observe()      ← read project context + memory
    decide()       ← act or wait?
    if acting:
        do_one_thing()
        log_it()
        update_memory()
    sleep(interval)

# once per day:
    autoDream()    ← consolidate memory, compress observations
```

---

## Why this exists

Anthropic's KAIROS is locked behind feature flags with no announced release date.

Every analysis of the leak documented what it *is*. Nobody built what it *does*.

This is that.

---

## vs. OpenClaw

OpenClaw 4.11 has the most complete memory loop 
in open source: capture, structuring, retrieval, 
portability.

But you still have to trigger it through conversation.

heartbeat doesn't wait for the conversation.
It runs the loop on its own.


---

## Model support

Works with any Anthropic model. Swap `claude-sonnet-4-20250514` in `heartbeat.py`  
for any model you have access to.

OpenAI / Gemini / local model support: PRs welcome — the pattern is model-agnostic,  
only the client call needs swapping.

---

## Status

- [x] Core heartbeat loop
- [x] autoDream memory consolidation  
- [x] Append-only daily logs
- [x] CLAUDE.md / README.md auto-detection
- [x] Structured JSONL learnings (gstack-compatible schema)
- [x] `--learn` command to review what the agent observed
- [ ] Push notifications (phone/desktop)
- [ ] GitHub webhook subscriptions
- [ ] OpenAI / Gemini client support
- [ ] Web dashboard for log viewing

---

## Contributing

Open issues for:
- Alternative model client implementations
- Notification backends (Telegram, Slack, desktop)
- GitHub webhook integration

---

*Named after the Greek concept of "the right moment" — καιρός*

