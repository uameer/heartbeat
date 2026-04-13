"""
heartbeat.py — The KAIROS pattern, open and model-agnostic.

Anthropic built an always-on background agent into Claude Code
and never told anyone. The leak revealed it. This is the open version.

Every N seconds, the agent asks one question:
"Is there anything worth doing right now?"

If yes — it acts. If no — it waits.
"""

import os
import time
import json
import logging
import argparse
import datetime
from pathlib import Path
from typing import Optional
import anthropic

# ── Provider setup ────────────────────────────────────────────────────────────

PROVIDER = os.getenv("HEARTBEAT_PROVIDER", "anthropic").lower()
if PROVIDER == "openai":
    from openai import OpenAI

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_DIR = Path(".heartbeat/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.date.today().isoformat()
log_file = LOG_DIR / f"{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),          # append-only daily log
        logging.StreamHandler(),                 # terminal output
    ],
)
log = logging.getLogger("heartbeat")

# ── Memory ────────────────────────────────────────────────────────────────────

MEMORY_DIR = Path(".heartbeat/memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
LEARNINGS_FILE = MEMORY_DIR / "learnings.jsonl"

def write_learning(type: str, key: str, insight: str, confidence: int, source: str = "heartbeat") -> None:
    """Append a structured learning entry — same schema as gstack /learn."""
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "type": type,        # pattern | pitfall | observation | architecture
        "key": key,          # 2-5 words kebab-case
        "insight": insight,  # one sentence
        "confidence": confidence,  # 1-10
        "source": source,
    }
    with open(LEARNINGS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

def load_memory() -> str:
    """Load learnings as readable context for the next tick."""
    if not LEARNINGS_FILE.exists():
        return ""
    lines = LEARNINGS_FILE.read_text().strip().splitlines()
    if not lines:
        return ""
    # Return last 20 entries as readable summary
    recent = [json.loads(l) for l in lines[-20:] if l.strip()]
    return "\n".join(f"[{e['type']}] {e['key']}: {e['insight']} (confidence: {e['confidence']}/10)" for e in recent)

def show_learnings() -> None:
    """Print all learnings grouped by type."""
    if not LEARNINGS_FILE.exists():
        print("No learnings yet.")
        return
    lines = LEARNINGS_FILE.read_text().strip().splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
    # Dedup by key — latest wins
    seen = {}
    for e in entries:
        seen[e["key"]] = e
    by_type = {}
    for e in seen.values():
        by_type.setdefault(e["type"], []).append(e)
    for t, items in sorted(by_type.items()):
        print(f"\n── {t.upper()} ──")
        for e in sorted(items, key=lambda x: -x["confidence"]):
            print(f"  [{e['confidence']}/10] {e['key']}: {e['insight']}")

def consolidate_memory(client, current_memory: str, todays_log: str) -> str:
    """
    autoDream: consolidate what was learned today into persistent memory.
    Runs once per day. Merges observations, removes contradictions,
    compresses to under 200 lines.
    """
    log.info("autoDream: consolidating memory...")
    prompt = f"""You are a memory consolidation agent (autoDream).

Current persistent memory:
<memory>
{current_memory or "(empty)"}
</memory>

Today's activity log:
<log>
{todays_log}
</log>

Merge these into an updated memory file. Rules:
- Remove contradictions (newer info wins)
- Remove redundancy
- Preserve all decisions, findings, and open questions
- Keep under 200 lines
- Use clear markdown headings

Return ONLY the updated memory content, no preamble."""

    if PROVIDER == "openai":
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    else:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

# ── Tick ──────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a proactive background agent running on a heartbeat loop.

Your job: decide if there is anything worth doing right now, then do it.

You have access to the project context below. On each tick you must:
1. Observe the current state
2. Decide: act or wait
3. If acting, take ONE focused action and explain what you did
4. If waiting, explain briefly why

Rules:
- Only act when there is clear value. Silence is better than noise.
- Never repeat actions you already took recently (check memory)
- Keep responses concise — this runs every few seconds
- If you act, describe what you did in one sentence for the log
- If repeated errors appear in logs, invoke the triage skill:
  read skills/triage.md and follow its phases before acting

Respond in JSON:
{
  "decision": "act" | "wait",
  "reasoning": "one sentence",
  "action_taken": "description of what you did (if acting)",
  "learning_type": "pattern" | "pitfall" | "observation" | "architecture",
  "learning_key": "2-5-word-kebab-case-key",
  "confidence": 1-10,
  "memory_update": "any new insight to remember (optional)"
}"""

def tick(client, project_context: str, memory: str, tick_number: int) -> Optional[str]:
    """
    One heartbeat. Returns a memory update string if the agent acted.
    """
    user_message = f"""Tick #{tick_number} — {datetime.datetime.now().isoformat()}

Project context:
<context>
{project_context}
</context>

Persistent memory:
<memory>
{memory or "(empty — first run)"}
</memory>

Anything worth doing right now?"""

    try:
        if PROVIDER == "openai":
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=500,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            raw = response.choices[0].message.content.strip()
        else:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()

        # Parse JSON response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)

        decision = result.get("decision", "wait")
        reasoning = result.get("reasoning", "")
        action = result.get("action_taken", "")
        memory_update = result.get("memory_update", "")

        if decision == "act":
            log.info(f"[ACT] {action}")
            learning_key = result.get("learning_key", "observation")
            learning_type = result.get("learning_type", "observation")
            confidence = result.get("confidence", 5)
            if action:
                write_learning(
                    type=learning_type,
                    key=learning_key,
                    insight=action,
                    confidence=confidence,
                )
            if memory_update:
                return memory_update
        else:
            log.info(f"[WAIT] {reasoning}")

    except json.JSONDecodeError:
        log.warning(f"Non-JSON response on tick {tick_number}: {raw[:100]}")
    except Exception as e:
        log.error(f"Tick {tick_number} error: {e}")

    return None

# ── Main loop ─────────────────────────────────────────────────────────────────

def read_project_context(context_file: Optional[str]) -> str:
    """Load project context from file or auto-detect CLAUDE.md / README.md."""
    candidates = [
        context_file,
        "CLAUDE.md",
        "README.md",
        ".heartbeat/context.md",
    ]
    for path in candidates:
        if path and Path(path).exists():
            content = Path(path).read_text()
            log.info(f"Loaded context from {path}")
            return content[:3000]  # cap at 3K chars
    return "No project context found. Monitor for general activity."

def run(
    interval: int = 30,
    context_file: Optional[str] = None,
    dream_interval: int = 86400,  # 24 hours
):
    if PROVIDER == "openai":
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        log.info("  provider:       openai")
    else:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        log.info("  provider:       anthropic")

    project_context = read_project_context(context_file)
    memory = load_memory()

    log.info("heartbeat started")
    log.info(f"  interval:       {interval}s")
    log.info(f"  dream_interval: {dream_interval}s")
    log.info(f"  context:        {len(project_context)} chars")
    log.info(f"  memory:         {len(memory)} chars")
    log.info("─" * 50)

    tick_number = 0
    last_dream = time.time()
    memory_updates = []

    try:
        while True:
            tick_number += 1
            memory = load_memory()
            update = tick(client, project_context, memory, tick_number)
            if update:
                memory_updates.append(update)

            # autoDream: consolidate memory once per dream_interval
            now = time.time()
            if now - last_dream >= dream_interval and memory_updates:
                todays_log = log_file.read_text() if log_file.exists() else ""
                consolidated = consolidate_memory(client, load_memory(), todays_log)
                write_learning("observation", "autodream-summary", consolidated[:200], 7, "autodream")
                memory_updates.clear()
                last_dream = now
                log.info("autoDream complete")

            time.sleep(interval)

    except KeyboardInterrupt:
        log.info("heartbeat stopped by user")

# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="heartbeat — the KAIROS pattern, open and model-agnostic"
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Seconds between heartbeats (default: 30)"
    )
    parser.add_argument(
        "--context", type=str, default=None,
        help="Path to project context file (default: auto-detect CLAUDE.md/README.md)"
    )
    parser.add_argument(
        "--dream-interval", type=int, default=86400,
        help="Seconds between memory consolidations (default: 86400 = 24h)"
    )
    parser.add_argument(
        "--learn", action="store_true",
        help="Show all learnings grouped by type and exit"
    )
    args = parser.parse_args()

    if args.learn:
        show_learnings()
        exit(0)

    if PROVIDER == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY environment variable not set")
            exit(1)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY environment variable not set")
            exit(1)

    run(
        interval=args.interval,
        context_file=args.context,
        dream_interval=args.dream_interval,
    )