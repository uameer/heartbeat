import os
import json
import datetime
import subprocess
from pathlib import Path

MAX_SIGNAL_LINES = int(os.getenv("HEARTBEAT_MAX_SIGNAL_LINES", "30"))


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
