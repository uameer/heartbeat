"""
heartbeat.py — The KAIROS pattern, open and model-agnostic.

Anthropic built an always-on background agent into Claude Code
and never told anyone. The leak revealed it. This is the open version.

Every N seconds, the agent asks one question:
"Is there anything worth doing right now?"

If yes — it acts. If no — it waits.
"""

import os
import sys
import time
import json
import logging
import argparse
import datetime
import subprocess
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# ── Provider setup ────────────────────────────────────────────────────────────

PROVIDER = os.getenv("HEARTBEAT_PROVIDER", "anthropic").lower()
OPENAI_MODEL = os.getenv("HEARTBEAT_OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.getenv("HEARTBEAT_ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
OLLAMA_MODEL = os.getenv("HEARTBEAT_OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_BASE_URL = os.getenv("HEARTBEAT_OLLAMA_BASE_URL", "http://localhost:11434")
GEMINI_MODEL = os.getenv("HEARTBEAT_GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
MAX_SIGNAL_LINES = int(os.getenv("HEARTBEAT_MAX_SIGNAL_LINES", "30"))

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_DIR: Path
MEMORY_DIR: Path
LEARNINGS_FILE: Path
log_file: Path

def configure_workspace(workspace: Path) -> None:
    """Initialize workspace-local paths for logs and memory."""
    global LOG_DIR, MEMORY_DIR, LEARNINGS_FILE, log_file

    root = workspace / ".heartbeat"
    LOG_DIR = root / "logs"
    MEMORY_DIR = root / "memory"
    LEARNINGS_FILE = MEMORY_DIR / "learnings.jsonl"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    log_file = LOG_DIR / f"{today}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),      # append-only daily log
            logging.StreamHandler(),            # terminal output
        ],
        force=True,
    )

log = logging.getLogger("heartbeat")

# ── Memory ────────────────────────────────────────────────────────────────────

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

def recent_learning_entries(limit: int = 20) -> list[dict]:
    """Return recent learning entries (latest first)."""
    if not LEARNINGS_FILE.exists():
        return []
    lines = LEARNINGS_FILE.read_text().strip().splitlines()
    if not lines:
        return []
    parsed = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(parsed))

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

def get_actions(limit: int = 20) -> list[dict]:
    """Return recent actionable items from learnings and today's log."""
    def normalize_action_text(text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"\[tool\.pytest\.ini_options\]", "tool.pytest.ini_options", t)
        t = re.sub(r"\b(read|inspect|check|review)\b", "inspect", t)
        t = re.sub(r"\b(section|addopts section)\b", "addopts", t)
        t = re.sub(r"\b(modified file|exact|obvious|may be|could be)\b", " ", t)
        t = re.sub(r"\b(causing|cause)\b", " ", t)
        t = re.sub(r"\b(pytest startup error|cached test failure)\b", "test failure", t)
        t = re.sub(r"\b(broken imports|syntax errors|todo/fixme items)\b", "code issues", t)
        t = re.sub(r"\b(the|a|an|to|for|of|and)\b", " ", t)
        t = re.sub(r"[^a-z0-9._/\-\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:
            return True
        return SequenceMatcher(None, a, b).ratio() >= 0.88

    items: list[tuple[str, str]] = []  # (source, text)

    for e in recent_learning_entries(limit=200):
        insight = (e.get("insight") or "").strip()
        if insight:
            items.append(("learning", insight))

    if log_file.exists():
        try:
            for line in reversed(log_file.read_text().splitlines()):
                if "[ACT]" in line:
                    action = line.split("[ACT]", 1)[1].strip()
                    if action:
                        items.append(("log", action))
                if len(items) >= 300:
                    break
        except Exception:
            pass

    deduped: list[tuple[str, str]] = []
    seen_normalized: list[str] = []
    for source, text in items:
        normalized = normalize_action_text(text)
        if not normalized:
            continue
        if any(similar(normalized, s) for s in seen_normalized):
            continue
        seen_normalized.append(normalized)
        deduped.append((source, text))
        if len(deduped) >= limit:
            break

    return [{"source": source, "text": text} for source, text in deduped]

def show_actions(limit: int = 20, as_json: bool = False) -> None:
    actions = get_actions(limit=limit)
    if as_json:
        print(json.dumps(actions, indent=2))
        return

    if not actions:
        print("No actionable items yet.")
        return

    print("Recent actionable items:")
    for idx, item in enumerate(actions, 1):
        print(f"{idx}. [{item['source']}] {item['text']}")

def show_report() -> None:
    """Print a weekly summary from learnings.jsonl."""
    # ── Load all entries ──────────────────────────────────────────────────────
    if not LEARNINGS_FILE.exists():
        print("No learnings file found.")
        return
    lines = LEARNINGS_FILE.read_text().strip().splitlines()
    all_entries: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            all_entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    total = len(all_entries)
    now = datetime.datetime.now()
    cutoff_7d = now - datetime.timedelta(days=7)

    # ── Act/wait ratio from today's log ───────────────────────────────────────
    act_count = 0
    wait_count = 0
    if log_file.exists():
        for line in log_file.read_text().splitlines():
            if "[ACT]" in line:
                act_count += 1
            elif "[WAIT]" in line:
                wait_count += 1
    total_decisions = act_count + wait_count
    if total_decisions > 0:
        act_pct = round(100 * act_count / total_decisions)
        wait_pct = 100 - act_pct
        ratio_str = f"{act_count} act / {wait_count} wait  ({act_pct}% act, {wait_pct}% wait)"
    else:
        ratio_str = "No decisions logged today"

    # ── Top 3 pitfalls by confidence ──────────────────────────────────────────
    pitfalls = [e for e in all_entries if e.get("type") == "pitfall"]
    # Dedup by key — latest wins
    seen: dict[str, dict] = {}
    for e in pitfalls:
        seen[e.get("key", "")] = e
    top_pitfalls = sorted(seen.values(), key=lambda x: -x.get("confidence", 0))[:3]

    # ── Top 3 patterns by confidence ──────────────────────────────────────────
    patterns = [e for e in all_entries if e.get("type") == "pattern"]
    seen2: dict[str, dict] = {}
    for e in patterns:
        seen2[e.get("key", "")] = e
    top_patterns = sorted(seen2.values(), key=lambda x: -x.get("confidence", 0))[:3]

    # ── New learnings in last 7 days ──────────────────────────────────────────
    recent_entries: list[dict] = []
    for e in all_entries:
        try:
            ts = datetime.datetime.fromisoformat(e["ts"])
            if ts >= cutoff_7d:
                recent_entries.append(e)
        except (KeyError, ValueError):
            continue
    new_last_7d = len(recent_entries)

    # ── Compounding rate: avg new learnings per day over last 7 days ──────────
    daily_counts: dict[str, int] = {}
    for e in recent_entries:
        try:
            day = datetime.datetime.fromisoformat(e["ts"]).date().isoformat()
            daily_counts[day] = daily_counts.get(day, 0) + 1
        except (KeyError, ValueError):
            continue
    avg_per_day = round(new_last_7d / 7, 1)

    # ── Print ─────────────────────────────────────────────────────────────────
    print()
    print("━" * 50)
    print("  Heartbeat Weekly Summary")
    print("━" * 50)
    print()
    print(f"  Total learning entries : {total}")
    print()
    print(f"  Act/wait ratio (today) : {ratio_str}")
    print()
    print("  Top 3 pitfalls (by confidence):")
    if top_pitfalls:
        for e in top_pitfalls:
            print(f"    [{e.get('confidence', '?')}/10] {e.get('key', '')}: {e.get('insight', '')}")
    else:
        print("    (none recorded)")
    print()
    print("  Top 3 patterns (by confidence):")
    if top_patterns:
        for e in top_patterns:
            print(f"    [{e.get('confidence', '?')}/10] {e.get('key', '')}: {e.get('insight', '')}")
    else:
        print("    (none recorded)")
    print()
    print(f"  New learnings (last 7 days) : {new_last_7d}")
    print(f"  Compounding rate            : {avg_per_day} new learnings/day")
    print()
    print("━" * 50)
    print()


def consolidate_memory(client, current_memory: str, todays_log: str, provider: str, model: str) -> str:
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

    if provider in ("openai", "ollama", "gemini"):
        response = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    else:
        #anthropic
        response = client.messages.create(
            model=model,
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

def run_cmd(cmd: list[str], cwd: Path, timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (result.stdout or result.stderr).strip()
    except Exception as e:
        return f"(command failed: {' '.join(cmd)}: {e})"

def collect_generic_signals(workspace: Path) -> str:
    sections: list[str] = []

    git_status = run_cmd(["git", "status", "--short"], cwd=workspace)
    if git_status:
        lines = git_status.splitlines()[:MAX_SIGNAL_LINES]
        sections.append(f"Git status (top {MAX_SIGNAL_LINES}):\n" + "\n".join(lines))

    todos = run_cmd(
        [
            "rg",
            "-n",
            "--max-count",
            str(MAX_SIGNAL_LINES),
            "--glob",
            "!.git/*",
            "--glob",
            "!.venv/*",
            "--glob",
            "!.heartbeat/*",
            "(TODO|FIXME|HACK|XXX)",
            ".",
        ],
        cwd=workspace,
    )
    if todos and "No files were searched" not in todos:
        sections.append(
            f"Repo TODO/FIXME/HACK hits (top {MAX_SIGNAL_LINES}):\n"
            + "\n".join(todos.splitlines()[:MAX_SIGNAL_LINES])
        )

    tracked = run_cmd(["git", "ls-files"], cwd=workspace)
    stale: list[tuple[float, str]] = []
    if tracked and not tracked.startswith("(command failed"):
        cutoff = datetime.datetime.now().timestamp() - (90 * 24 * 60 * 60)
        for rel in tracked.splitlines():
            p = workspace / rel
            if not p.exists() or not p.is_file():
                continue
            try:
                mtime = p.stat().st_mtime
                if mtime < cutoff:
                    stale.append((mtime, rel))
            except OSError:
                continue
        if stale:
            stale.sort(key=lambda x: x[0])
            sample = [f"- {rel}" for _, rel in stale[:MAX_SIGNAL_LINES]]
            sections.append(
                f"Tracked files not modified in 90+ days (showing {min(len(stale), MAX_SIGNAL_LINES)} of {len(stale)}):\n"
                + "\n".join(sample)
            )

    if not sections:
        return "No concrete repo signals detected."
    return "\n\n".join(sections)

def collect_django_signals(workspace: Path, run_checks: bool = False) -> str:
    sections: list[str] = []
    manage_py = workspace / "manage.py"
    if not manage_py.exists():
        return "No Django markers found (manage.py missing)."

    sections.append("Django project marker detected: manage.py present.")

    pytest_lastfailed = workspace / ".pytest_cache" / "v" / "cache" / "lastfailed"
    if pytest_lastfailed.exists():
        try:
            data = json.loads(pytest_lastfailed.read_text())
            if isinstance(data, dict) and data:
                keys = list(data.keys())[:20]
                sections.append(
                    f"Recent pytest failures from cache ({len(data)} total, showing up to {MAX_SIGNAL_LINES}):\n"
                    + "\n".join(f"- {k}" for k in keys[:MAX_SIGNAL_LINES])
                )
        except Exception:
            pass

    migration_files = list(workspace.glob("**/migrations/*.py"))
    recent_migrations = sorted(
        [p for p in migration_files if p.name != "__init__.py"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    if recent_migrations:
        sections.append(
            f"Recent migration files (top {MAX_SIGNAL_LINES}):\n"
            + "\n".join(
                f"- {p.relative_to(workspace)}" for p in recent_migrations[:MAX_SIGNAL_LINES]
            )
        )

    if run_checks:
        deploy_check = run_cmd(
            ["python", "manage.py", "check", "--deploy"],
            cwd=workspace,
            timeout=30,
        )
        if deploy_check:
            sections.append(
                "Django deploy check output (truncated):\n"
                + "\n".join(deploy_check.splitlines()[:MAX_SIGNAL_LINES])
            )

        pytest_quick = run_cmd(
            ["pytest", "-q", "--maxfail=3"],
            cwd=workspace,
            timeout=90,
        )
        if pytest_quick:
            sections.append(
                "Pytest quick output (truncated):\n"
                + "\n".join(pytest_quick.splitlines()[:MAX_SIGNAL_LINES])
            )

    return "\n\n".join(sections)

def collect_signals(workspace: Path, profile: str, run_checks: bool = False) -> str:
    sections = [f"Profile: {profile}", collect_generic_signals(workspace)]
    if profile == "django":
        sections.append(collect_django_signals(workspace, run_checks=run_checks))
    return "\n\n".join([s for s in sections if s])

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
            #anthropic
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=system_prompt,
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
            # Prevent loops: if the same action was already logged recently, downgrade to WAIT.
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

def build_client(provider: str):
    """Lazy import provider client to avoid unnecessary import failures."""
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable not set")
        from openai import OpenAI
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    
    if provider == "ollama":
        from openai import OpenAI
        return OpenAI(
            base_url=f"{OLLAMA_BASE_URL}/v1",
            api_key="ollama",
        )
    
    if provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY environment variable not set")
        from openai import OpenAI
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.environ["GEMINI_API_KEY"],
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def choose_model(provider: str, model_override: Optional[str]) -> str:
    if model_override:
        return model_override
    if provider == "openai":
        return OPENAI_MODEL
    if provider == "ollama":
        return OLLAMA_MODEL
    if provider == "gemini":
        return GEMINI_MODEL
    return ANTHROPIC_MODEL

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
                todays_log = log_file.read_text() if log_file.exists() else ""
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
