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
> heartbeat doesn't.

---

## What it does

- tick #1  → [WAIT] No open issues or stale files detected
- tick #2  → [WAIT] Tests passing, no action needed
- tick #3  → [ACT]  Found TODO in auth.py from 3 weeks ago — flagged in memory
- tick #4  → [WAIT] Nothing urgent
...
- [night]  → autoDream: consolidating memory from today's observations
- Runs silently in the background
- Reads your project context (CLAUDE.md, README.md, or custom file)
- Decides autonomously whether to act each tick
- Keeps append-only daily logs — it cannot erase its own history
- Runs **autoDream** once per day: consolidates memory, removes contradictions, compresses observations
- Writes structured learning entries after every action — queryable, exportable, yours

---

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/heartbeat
cd heartbeat
./scripts/install.sh
```

Then choose a provider key:

```bash
# Anthropic (default provider)
export ANTHROPIC_API_KEY=your_key_here

# OR OpenAI
# export HEARTBEAT_PROVIDER=openai
# export OPENAI_API_KEY=your_key_here

# OR Gemini
# export HEARTBEAT_PROVIDER=gemini
# export GEMINI_API_KEY=your_key_here

# OR Ollama
# export HEARTBEAT_PROVIDER=ollama
# ollama pull qwen3.5:9b
```

## Run

```bash
# Run heartbeat against the current folder (workspace ".")
./scripts/run.sh . --interval 30

# Show what the agent has learned across sessions
./scripts/run.sh . --learn

# Show recent actionable items
./scripts/run.sh . --actions --actions-limit 20

# JSON output for automation/scripts
./scripts/run.sh . --actions-json --actions-limit 20

# Run heartbeat for a different project folder
./scripts/run.sh /absolute/path/to/your-project --interval 60

# Save defaults for this workspace (one-time)
./scripts/run.sh /absolute/path/to/your-project \
  --provider anthropic \
  --model claude-sonnet-4-6 \
  --profile django \
  --run-checks \
  --interval 120 \
  --save-config

# After saving config, this is enough
./scripts/run.sh /absolute/path/to/your-project

# Optional provider/model overrides
./scripts/run.sh . --provider openai --model gpt-4o
./scripts/run.sh . --provider anthropic --model claude-3-7-sonnet-latest
./scripts/run.sh . --provider gemini --model gemini-3.1-flash-lite-preview
./scripts/run.sh . --provider ollama --model qwen3.5:9b

# Optional profile (default: generic)
./scripts/run.sh /absolute/path/to/django-project --profile django --interval 60

# Optional deeper checks (django profile)
./scripts/run.sh /absolute/path/to/django-project --profile django --run-checks --interval 120

# Optional context file
./scripts/run.sh . --context my_project_context.md
```

All logs/memory are stored inside the target workspace:
`.heartbeat/logs/` and `.heartbeat/memory/learnings.jsonl`.
Workspace defaults are stored in `.heartbeat/config.json`.

## Python version

Use Python 3.11 or 3.12.
Python 3.14 is currently blocked by dependency ABI issues (`pydantic_core`).

---

## File structure

```
your-project/
├── heartbeat.py             ← the harness (~300 lines)
├── skills/
│   └── triage.md            ← error clustering skill
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt

# created automatically when heartbeat runs:
.heartbeat/
├── memory/
│   └── learnings.jsonl      ← every action logged as structured entry
└── logs/
    └── 2026-04-13.log       ← append-only daily log
```

`.heartbeat/` is in `.gitignore` — your learnings stay local.  
`skills/` is public — the methodology is shared, the memory is yours.

---

## Architecture

Three layers. Same pattern as Garry Tan's YC framework — arrived at independently.

**Fat skills on top** — `skills/` encodes what the agent knows how to do.
Structured markdown procedures. Invoke on pattern match.

****Thin harness in the middle** — `heartbeat.py`, ~300 lines.
JSON in, text out. Read-only by default.

**Your project on the bottom** — `CLAUDE.md`, `README.md`, or any context file.
The deterministic foundation.

Push intelligence up into skills.
Push execution down into your existing project files.
Keep the harness thin.

Every model improvement automatically improves every tick.

---

## Skills

Built-in skills that trigger automatically:

| Skill | Triggers when | What it does |
|-------|--------------|--------------|
| `skills/triage.md` | Same error appears 3+ times | Cluster errors, score severity, write structured learning entries |

Add your own skills as markdown files in `skills/`.

---

## The KAIROS architecture

From the leaked Claude Code source (512,000 lines, March 31 2026):

KAIROS receives periodic <tick> prompts and decides independently
whether to act. It has three tools normal Claude Code never sees:
push notifications, file delivery, and GitHub PR subscriptions.
At night it runs autoDream — memory consolidation while you sleep.
heartbeat implements the core loop:

```
while True:
    observe()        ← read project context + memory
    decide()         ← act or wait?
    if acting:
        do_one_thing()
        log_it()
        write_learning()   ← structured JSONL entry
    sleep(interval)

# once per day:
    autoDream()      ← consolidate memory, compress observations
```
---

## Why this exists

Anthropic's KAIROS is locked behind feature flags with no announced release date.

Every analysis of the leak documented what it *is*. Nobody built what it *does*.

This is that.

---

## vs. Claude Managed Agents

Anthropic launched Managed Agents on April 8, 2026 — same always-on pattern,
locked behind their API at $0.08/hour. Your memory on their servers.

heartbeat runs on your machine.
Zero infrastructure cost beyond API calls.
Your learnings stay in a file you own, read, and take anywhere.

If Claude gets worse, swap to GPT. Your memory comes with you.

---

## vs. OpenClaw

OpenClaw 4.11 has the most complete memory loop in open source:
capture, structuring, retrieval, portability.

But you still have to trigger it through conversation.

heartbeat doesn't wait for the conversation.
It runs the loop on its own.

---

## vs. Claude Code Routines

Anthropic launched Routines on April 14 2026 —
scheduled autonomous agent runs on their cloud.

Same pattern. Their infrastructure. Claude only.
Your observations on their servers.

heartbeat runs on your machine.
Works with any model.
Builds structured memory across every tick.
The agent compounds. Routines reset.

---

## Model support

Set model via env or CLI, no code changes needed:

| Provider    | Default model                    | Env var                       | API key env var   |
|-------------|----------------------------------|-------------------------------|-------------------|
| `anthropic` | `claude-3-7-sonnet-latest`       | `HEARTBEAT_ANTHROPIC_MODEL`   | `ANTHROPIC_API_KEY` |
| `openai`    | `gpt-4o`                         | `HEARTBEAT_OPENAI_MODEL`      | `OPENAI_API_KEY`  |
| `gemini`    | `gemini-3.1-flash-lite-preview`  | `HEARTBEAT_GEMINI_MODEL`      | `GEMINI_API_KEY`  |
| `ollama`    | `qwen2.5:7b`                     | `HEARTBEAT_OLLAMA_MODEL`      | *(not required)*  |

Ollama runs fully locally. Install from [ollama.com](https://ollama.com).

CLI override: `--model ...`

## Profiles (pluggable signals)

Heartbeat keeps the harness generic and uses optional profiles for deeper signals:

- `generic` (default): git status, TODO/FIXME/HACK hits, stale tracked files
- `django`: generic signals + Django markers (pytest `lastfailed`, recent migrations)
  - optional `--run-checks`: runs `python manage.py check --deploy` and `pytest -q --maxfail=3`

Example:

```bash
./scripts/run.sh /Users/you/your-django-repo --profile django --interval 60
```

Signal volume can be tuned with:

```bash
export HEARTBEAT_MAX_SIGNAL_LINES=50
```

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
- [x] Triage skill — cluster errors, score severity, structured entries
- [x] OpenAI client support (`HEARTBEAT_PROVIDER=openai`)
- [x] Gemini client support (`HEARTBEAT_PROVIDER=gemini`)
- [x] Ollama client support (`HEARTBEAT_PROVIDER=ollama`)
- [x] --lean mode for token-efficient ticks
- [x] --report weekly summary command
- [x] --dry-run mode
- [ ] Push notifications (phone/desktop)
- [ ] GitHub webhook subscriptions
- [ ] Web dashboard for log viewing

---

## Security model

heartbeat's autonomous core — `tick()` and `run()` — is ~100 lines. That's the part that makes decisions.

The full codebase splits across 4 files:
- `heartbeat.py` — core loop + CLI (~450 lines)
- `heartbeat_memory.py` — learning storage
- `heartbeat_signals.py` — project signal collection
- `heartbeat_providers.py` — model API clients

heartbeat reads files from your project directory.
It does not write to files by default.
It does not make network requests except to the model API.
It does not execute shell commands.

Read `tick()` and `run()` before you run it.
That's the security model.

---

## Contributing

Open issues for:
- Notification backends (Telegram, Slack, desktop)
- GitHub webhook integration
- Additional skills

---

*Named after the Greek concept of "the right moment" — καιρός*
