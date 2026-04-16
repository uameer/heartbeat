"""
heartbeat.py — The KAIROS pattern, open and model-agnostic.

Anthropic built an always-on background agent into Claude Code
and never told anyone. The leak revealed it. This is the open version.

Every N seconds, the agent asks one question:
"Is there anything worth doing right now?"

If yes — it acts. If no — it waits.
"""

import sys
import time
import json
import logging
import argparse
import datetime
from pathlib import Path
from typing import Optional

import heartbeat_memory
from heartbeat_providers import PROVIDER, build_client, choose_model
from heartbeat_memory import (
    write_learning, load_memory, show_learnings, show_report,
    get_actions, show_actions, consolidate_memory, recent_learning_entries,
)
from heartbeat_signals import collect_signals

log = logging.getLogger("heartbeat")


def configure_workspace(workspace: Path) -> None:
    """Initialize workspace-local paths for logs and memory."""
    root = workspace / ".heartbeat"
    log_dir = root / "logs"
    memory_dir = root / "memory"
    learnings_file = memory_dir / "learnings.jsonl"
    log_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    log_file = log_dir / f"{today}.log"

    heartbeat_memory.MEMORY_DIR = memory_dir
    heartbeat_memory.LEARNINGS_FILE = learnings_file
    heartbeat_memory.log_file = log_file

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),      # append-only daily log
            logging.StreamHandler(),            # terminal output
        ],
        force=True,
    )


# ── Prompts ───────────────────────────────────────────────────────────────────

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
- Prefer concrete runtime signals over generic assumptions
- If your previous action was "read/inspect file X", do not repeat it on the next tick.
  Propose a different concrete next step or wait.

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

SYSTEM_PROMPT_LEAN = """You are a minimal background agent on a heartbeat loop.

Only act when something is clearly broken or blocked. Default to waiting.

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


# ── Tick ──────────────────────────────────────────────────────────────────────

def tick(
    client,
    project_context: str,
    memory: str,
    tick_number: int,
    provider: str,
    model: str,
    signals: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> Optional[str]:
    """One heartbeat. Returns a memory update string if the agent acted."""
    user_message = f"""Tick #{tick_number} — {datetime.datetime.now().isoformat()}

Project context:
<context>
{project_context}
</context>

Persistent memory:
<memory>
{memory or "(empty — first run)"}
</memory>

Collected signals:
<signals>
{signals}
</signals>

Anything worth doing right now?"""

    try:
        if provider in ("openai", "ollama", "gemini"):
            response = client.chat.completions.create(
                model=model,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            raw = response.choices[0].message.content.strip()
        else:
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()

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
            normalized_action = " ".join(action.lower().split())
            recent_actions = {
                " ".join((e.get("insight", "") or "").lower().split())
                for e in recent_learning_entries(limit=10)
            }
            if normalized_action and normalized_action in recent_actions:
                log.info(f"[WAIT] Repeated recent action suppressed: {action}")
                return None

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

def read_project_context(context_file: Optional[str], workspace: Path) -> str:
    """Load project context from file or auto-detect CLAUDE.md / README.md."""
    candidates = [
        Path(context_file) if context_file else None,
        workspace / "CLAUDE.md",
        workspace / "README.md",
        workspace / ".heartbeat/context.md",
    ]
    for path in candidates:
        if path and path.exists():
            content = path.read_text()
            log.info(f"Loaded context from {path}")
            return content[:3000]  # cap at 3K chars
    return "No project context found. Monitor for general activity."


def load_workspace_config(workspace: Path) -> dict:
    """Load optional workspace defaults from .heartbeat/config.json."""
    config_path = workspace / ".heartbeat" / "config.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        log.warning(f"Invalid config file: {config_path}")
        return {}


def write_workspace_config(workspace: Path, config: dict) -> Path:
    config_path = workspace / ".heartbeat" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return config_path


def run(
    interval: int = 30,
    context_file: Optional[str] = None,
    dream_interval: int = 86400,  # 24 hours
    provider: str = PROVIDER,
    model: Optional[str] = None,
    workspace: Optional[Path] = None,
    profile: str = "generic",
    run_checks: bool = False,
    lean: bool = False,
):
    workspace = workspace or Path.cwd()
    configure_workspace(workspace)
    selected_provider = provider.lower()
    selected_model = choose_model(selected_provider, model)
    client = build_client(selected_provider)
    system_prompt = SYSTEM_PROMPT_LEAN if lean else SYSTEM_PROMPT
    log.info(f"  provider:       {selected_provider}")
    log.info(f"  model:          {selected_model}")
    log.info(f"  profile:        {profile}")
    log.info(f"  run_checks:     {run_checks}")
    log.info(f"  lean:           {lean}")

    project_context = read_project_context(context_file, workspace)
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
            signals = collect_signals(workspace, profile, run_checks=run_checks)
            update = tick(
                client,
                project_context,
                memory,
                tick_number,
                selected_provider,
                selected_model,
                signals,
                system_prompt=system_prompt,
            )
            if update:
                memory_updates.append(update)

            # autoDream: consolidate memory once per dream_interval
            now = time.time()
            if now - last_dream >= dream_interval and memory_updates:
                todays_log = heartbeat_memory.log_file.read_text() if heartbeat_memory.log_file.exists() else ""
                consolidated = consolidate_memory(
                    client, load_memory(), todays_log, selected_provider, selected_model
                )
                write_learning("observation", "autodream-summary", consolidated[:200], 7, "autodream")
                memory_updates.clear()
                last_dream = now
                log.info("autoDream complete")

            time.sleep(interval)

    except KeyboardInterrupt:
        log.info("heartbeat stopped by user")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.version_info >= (3, 14):
        print("Error: Python 3.14 is not supported yet by some dependencies.")
        print("Use Python 3.11 or 3.12 to run heartbeat.")
        exit(1)

    parser = argparse.ArgumentParser(
        description="heartbeat — the KAIROS pattern, open and model-agnostic"
    )
    parser.add_argument(
        "--interval", type=int, default=None,
        help="Seconds between heartbeats (default: 30 or workspace config)"
    )
    parser.add_argument(
        "--context", type=str, default=None,
        help="Path to project context file (default: auto-detect CLAUDE.md/README.md)"
    )
    parser.add_argument(
        "--dream-interval", type=int, default=None,
        help="Seconds between memory consolidations (default: 86400 or workspace config)"
    )
    parser.add_argument(
        "--workspace", type=str, default=".",
        help="Project directory where .heartbeat data is stored (default: current directory)"
    )
    parser.add_argument(
        "--provider", type=str, default=None, choices=["anthropic", "openai", "ollama", "gemini"],
        help="Model provider (default: workspace config, HEARTBEAT_PROVIDER, or anthropic)"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model name override (default: workspace config or HEARTBEAT_*_MODEL env var)"
    )
    parser.add_argument(
        "--profile", type=str, default=None, choices=["generic", "django"],
        help="Signal collector profile (default: workspace config or generic)"
    )
    parser.add_argument(
        "--run-checks", dest="run_checks", action="store_true", default=None,
        help="Enable optional profile-specific commands each tick"
    )
    parser.add_argument(
        "--no-run-checks", dest="run_checks", action="store_false", default=None,
        help="Disable optional profile-specific commands each tick"
    )
    parser.add_argument(
        "--learn", action="store_true",
        help="Show all learnings grouped by type and exit"
    )
    parser.add_argument(
        "--actions", action="store_true",
        help="Show recent actionable items and exit"
    )
    parser.add_argument(
        "--actions-json", action="store_true",
        help="Show recent actionable items as JSON and exit"
    )
    parser.add_argument(
        "--actions-limit", type=int, default=20,
        help="Maximum number of actionable items to show with --actions (default: 20)"
    )
    parser.add_argument(
        "--lean", action="store_true", default=False,
        help="Use minimal system prompt — only act when something is clearly broken"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print weekly summary from learnings.jsonl and exit"
    )
    parser.add_argument(
        "--save-config", action="store_true",
        help="Save current run defaults to <workspace>/.heartbeat/config.json and exit"
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    configure_workspace(workspace)
    workspace_config = load_workspace_config(workspace)

    interval = args.interval if args.interval is not None else int(workspace_config.get("interval", 30))
    dream_interval = (
        args.dream_interval
        if args.dream_interval is not None
        else int(workspace_config.get("dream_interval", 86400))
    )
    provider = args.provider or workspace_config.get("provider", PROVIDER)
    profile = args.profile or workspace_config.get("profile", "generic")
    model = args.model or workspace_config.get("model")
    run_checks = (
        args.run_checks
        if args.run_checks is not None
        else bool(workspace_config.get("run_checks", False))
    )

    if args.save_config:
        config_to_save = {
            "interval": interval,
            "dream_interval": dream_interval,
            "provider": provider,
            "profile": profile,
            "run_checks": run_checks,
        }
        if model:
            config_to_save["model"] = model
        path = write_workspace_config(workspace, config_to_save)
        print(f"Saved config: {path}")
        exit(0)

    if args.report:
        show_report()
        exit(0)
    if args.learn:
        show_learnings()
        exit(0)
    if args.actions or args.actions_json:
        show_actions(limit=max(args.actions_limit, 1), as_json=args.actions_json)
        exit(0)

    try:
        run(
            interval=interval,
            context_file=args.context,
            dream_interval=dream_interval,
            provider=provider,
            model=model,
            workspace=workspace,
            profile=profile,
            run_checks=run_checks,
            lean=args.lean,
        )
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
