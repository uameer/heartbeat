import json
import logging
import datetime
import re
from pathlib import Path
from difflib import SequenceMatcher

# Initialized by configure_workspace() in heartbeat.py
LEARNINGS_FILE: Path
MEMORY_DIR: Path
log_file: Path

log = logging.getLogger("heartbeat")


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
    recent = [json.loads(l) for l in lines[-20:] if l.strip()]
    return "\n".join(f"[{e['type']}] {e['key']}: {e['insight']} (confidence: {e['confidence']}/10)" for e in recent)


def show_learnings() -> None:
    """Print all learnings grouped by type."""
    if not LEARNINGS_FILE.exists():
        print("No learnings yet.")
        return
    lines = LEARNINGS_FILE.read_text().strip().splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
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

    pitfalls = [e for e in all_entries if e.get("type") == "pitfall"]
    seen: dict[str, dict] = {}
    for e in pitfalls:
        seen[e.get("key", "")] = e
    top_pitfalls = sorted(seen.values(), key=lambda x: -x.get("confidence", 0))[:3]

    patterns = [e for e in all_entries if e.get("type") == "pattern"]
    seen2: dict[str, dict] = {}
    for e in patterns:
        seen2[e.get("key", "")] = e
    top_patterns = sorted(seen2.values(), key=lambda x: -x.get("confidence", 0))[:3]

    recent_entries: list[dict] = []
    for e in all_entries:
        try:
            ts = datetime.datetime.fromisoformat(e["ts"])
            if ts >= cutoff_7d:
                recent_entries.append(e)
        except (KeyError, ValueError):
            continue
    new_last_7d = len(recent_entries)

    daily_counts: dict[str, int] = {}
    for e in recent_entries:
        try:
            day = datetime.datetime.fromisoformat(e["ts"]).date().isoformat()
            daily_counts[day] = daily_counts.get(day, 0) + 1
        except (KeyError, ValueError):
            continue
    avg_per_day = round(new_last_7d / 7, 1)

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
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
