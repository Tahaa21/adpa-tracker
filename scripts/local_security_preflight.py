#!/usr/bin/env python3
"""Lightweight local-only security preflight — run before using real data.

Checks configuration and file layout ONLY. It never opens, queries, or
prints the contents of backend/app.db or any uploaded/assessment data —
only whether the database file/path exists and is git-ignored.

Usage:
    python3 scripts/local_security_preflight.py

Exit code 0 + "PASS: Local-only security preflight" means every check
passed (warnings, if any, are still shown but don't fail the run). Exit
code 1 means at least one FAIL — read the output and fix before importing
real data.

This is intentionally simple: a flat list of checks, not a framework.
"""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

sys.path.insert(0, str(BACKEND_DIR))

FAILS: list[str] = []
WARNINGS: list[str] = []
PASSES: list[str] = []


def check(label: str, ok: bool, detail: str, *, warn_only: bool = False) -> None:
    if ok:
        PASSES.append(f"PASS  {label}: {detail}")
    elif warn_only:
        WARNINGS.append(f"WARN  {label}: {detail}")
    else:
        FAILS.append(f"FAIL  {label}: {detail}")


def git_check_ignore(path: str) -> bool | None:
    """Returns True if git ignores `path`, False if not, None if git/repo
    unavailable (caller should fall back to a text-based check)."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def gitignore_text() -> str:
    gi = REPO_ROOT / ".gitignore"
    return gi.read_text() if gi.exists() else ""


# --- 1. LOCAL_ONLY enabled -------------------------------------------------
try:
    from app.core.config import Settings  # noqa: E402

    settings = Settings()
    check(
        "LOCAL_ONLY",
        settings.local_only is True,
        f"local_only={settings.local_only}"
        + ("" if settings.local_only else " — set LOCAL_ONLY=true in .env"),
    )
except Exception as exc:  # pragma: no cover - defensive only
    check("LOCAL_ONLY", False, f"could not load backend settings: {exc}")
    settings = None

# --- 2. Database path is local ---------------------------------------------
if settings is not None:
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        check("Database location", True, f"SQLite (local file): {db_url}")
        db_is_sqlite = True
    else:
        parsed = urlparse(db_url)
        host = parsed.hostname or ""
        local_hosts = {"localhost", "127.0.0.1", "db", "::1", ""}
        check(
            "Database location",
            host in local_hosts,
            f"non-SQLite DATABASE_URL host = {host!r} "
            f"({'local/docker-internal' if host in local_hosts else 'NOT LOCAL — review this'})",
        )
        db_is_sqlite = False
else:
    db_is_sqlite = None

# --- 3. Database file is gitignored where practical -------------------------
if db_is_sqlite:
    # Resolve the sqlite file path relative to where the backend runs
    # (backend/), matching documented usage (DATABASE_URL=sqlite:///./app.db).
    rel_path = "backend/app.db"
    ignored = git_check_ignore(rel_path)
    if ignored is None:
        ignored = bool(re.search(r"^\*\.db$|^backend/app\.db$", gitignore_text(), re.MULTILINE))
        check(
            "Database gitignored",
            ignored,
            f"{rel_path} matched by .gitignore text (git unavailable, used text fallback)",
        )
    else:
        check("Database gitignored", ignored, f"`git check-ignore` confirms {rel_path} is ignored")
elif db_is_sqlite is False:
    check(
        "Database gitignored",
        True,
        "N/A — using a non-SQLite database (Postgres); no local DB file to ignore",
        warn_only=False,
    )

# --- 4. Upload/data directories gitignored ----------------------------------
CANDIDATE_DATA_DIRS = ["backend/uploads", "uploads", "data", "local-data", "real-data", "backend/logs"]
gi_text = gitignore_text()
missing = []
for d in CANDIDATE_DATA_DIRS:
    ignored = git_check_ignore(d + "/dummy_probe_file")
    if ignored is None:
        # Fallback: does .gitignore textually reference this path?
        ignored = any(d.rstrip("/") in line for line in gi_text.splitlines())
    if not ignored:
        missing.append(d)
check(
    "Upload/data directories gitignored",
    not missing,
    "all candidate paths ignored" if not missing else f"NOT ignored: {', '.join(missing)}",
)

# --- 5. Local-only host bindings in config files ----------------------------
def _strip_ts_comments(text: str) -> str:
    """Strip // line comments and /* */ block comments so config checks
    don't false-positive on comment text (e.g. a comment that quotes the
    exact pattern it's warning against)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


vite_config = FRONTEND_DIR / "vite.config.ts"
if vite_config.exists():
    code_only = _strip_ts_comments(vite_config.read_text())
    bad_host = re.search(r"host\s*:\s*(true|['\"]0\.0\.0\.0['\"])", code_only)
    check(
        "Vite host binding",
        bad_host is None,
        "no host:true/0.0.0.0 override in vite.config.ts (defaults to localhost)"
        if bad_host is None
        else "vite.config.ts sets host:true or 0.0.0.0 — this exposes the dev server to the LAN",
    )
else:
    check("Vite host binding", False, "frontend/vite.config.ts not found", warn_only=True)

compose_file = REPO_ROOT / "docker-compose.yml"
if compose_file.exists():
    text = compose_file.read_text()
    # Every host-side port publish for backend/frontend should be prefixed 127.0.0.1:
    port_lines = [
        line for line in text.splitlines()
        if re.search(r'-\s*"?\$\{(BACKEND_PORT|FRONTEND_PORT)', line)
    ]
    unbound = [line.strip() for line in port_lines if "127.0.0.1:" not in line]
    check(
        "Docker Compose port bindings",
        not unbound,
        "backend/frontend ports bound to 127.0.0.1 only"
        if not unbound
        else f"found non-localhost-bound port mapping(s): {unbound}",
    )
    # An active (non-commented) ports: mapping under the db: service
    # publishing 5432 would mean Postgres is exposed to the host.
    db_section = text.split("backend:")[0]
    active_pg_port_lines = [
        line for line in db_section.splitlines()
        if "5432" in line and not line.strip().startswith("#")
    ]
    check(
        "PostgreSQL host exposure",
        not active_pg_port_lines,
        "Postgres has no active host port publish (internal Docker network only)"
        if not active_pg_port_lines
        else f"Postgres appears to publish a host port: {active_pg_port_lines}",
    )
else:
    check("Docker Compose port bindings", False, "docker-compose.yml not found", warn_only=True)

# --- 6. No configured external API endpoints in source ----------------------
ALLOWLISTED_URLS = {"https://vite.dev"}  # known-safe doc-comment links, not runtime calls
suspicious: list[str] = []
for base, patterns in [(BACKEND_DIR / "app", "*.py"), (FRONTEND_DIR / "src", "*.ts*")]:
    if not base.exists():
        continue
    for path in base.rglob(patterns):
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for match in re.finditer(r"https?://[a-zA-Z0-9._-]+(?::\d+)?", text):
            url = match.group(0)
            if url in ALLOWLISTED_URLS:
                continue
            if re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])", url):
                continue
            suspicious.append(f"{path.relative_to(REPO_ROOT)}: {url}")
check(
    "No unexpected external endpoints in source",
    not suspicious,
    "only localhost references and allowlisted doc links found"
    if not suspicious
    else f"found {len(suspicious)} non-localhost URL(s) — review: {suspicious}",
)

# --- 7. Expected local configuration files present ---------------------------
expected_files = [
    REPO_ROOT / ".env.example",
    REPO_ROOT / ".gitignore",
    BACKEND_DIR / "requirements.txt",
    FRONTEND_DIR / "package.json",
]
missing_files = [str(p.relative_to(REPO_ROOT)) for p in expected_files if not p.exists()]
check(
    "Expected local configuration present",
    not missing_files,
    "all expected config files present" if not missing_files else f"missing: {missing_files}",
)


def main() -> int:
    print("Local-only security preflight\n" + "=" * 40)
    for line in PASSES:
        print(line)
    for line in WARNINGS:
        print(line)
    for line in FAILS:
        print(line)
    print()

    if FAILS:
        print(f"FAIL: Local-only security preflight ({len(FAILS)} failure(s), {len(WARNINGS)} warning(s))")
        return 1

    if WARNINGS:
        print(f"PASS: Local-only security preflight ({len(WARNINGS)} warning(s) — review above)")
        return 0

    print("PASS: Local-only security preflight")
    return 0


if __name__ == "__main__":
    sys.exit(main())
