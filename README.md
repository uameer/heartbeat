# heartbeat

> Anthropic built an always-on background agent into Claude Code and never told anyone.  
> The leak revealed it. This is the open version.

---

**KAIROS** is a hidden feature inside Claude Code — gated behind internal flags, never announced.  
It runs in the background, 24/7, without you asking.  
Every few seconds it receives one prompt:

> *"Anything worth doing right now?"*

If yes — it acts. If no — it waits.

`heartbeat` implements that pattern as a standalone, model-agnostic daemon you can attach to any project.

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
# Default: 30-second ticks, auto-detects CLAUDE.md or README.md
python heartbeat.py

# Custom interval and context
python heartbeat.py --interval 60 --context my_project_context.md

# Fast ticks for testing
python heartbeat.py --interval 10 --dream-interval 300
```

## File structure

```
your-project/
├── heartbeat.py
└── .heartbeat/
    ├── memory/
    │   └── context.md      ← persistent memory, updated each tick
    └── logs/
        └── 2026-04-11.log  ← append-only daily log
```

---

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
