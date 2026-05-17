#!/usr/bin/env python3
"""Pre-release quality gate — runs every automated check in one shot.

This is the single command CI and humans run before tagging a release. It
bundles nine independent checks so a green run guarantees:

* unit suite passes (no regressions)
* code is lint-clean and strict-type-clean
* the daemon route surface, the typed client, and the SKILL reference are
  all in sync (no drift between layers)
* every ``AgentcloakConfig`` field has matching documentation
* the version string is consistent across the package and the install docs
* every typer command group at least imports without raising

Browser-touching tests (Playwright integration) deliberately live elsewhere
— preflight is the fast feedback loop and must run without a daemon or
browser. Total runtime today is ~6s, dominated by pytest collection.

Usage
-----

    uv run python scripts/preflight.py            # all nine
    uv run python scripts/preflight.py --only smoke
    uv run python scripts/preflight.py -v         # show output of passing
                                                  # checks too, not just
                                                  # failures

Exit code is 0 when every selected check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DOCS = ROOT / "docs"
SCRIPTS = ROOT / "scripts"

# Make ``agentcloak`` importable for the in-process checks (smoke, config,
# version) — they read dataclasses and invoke the typer app directly rather
# than spawning subprocesses.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Locally we run everything through ``uv`` for a hermetic env. CI installs
# packages straight into the runner's Python and doesn't have ``uv`` on the
# PATH, so we transparently drop the prefix when uv is unavailable.
_HAS_UV = shutil.which("uv") is not None


# ---------------------------------------------------------------------------
# Result type + subprocess helper
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of a single preflight check."""

    passed: bool
    summary: str  # short label shown on the progress line ("422 passed")
    detail: str = ""  # full stdout/stderr — shown on failure or with -v


def _run(cmd: list[str]) -> tuple[int, str]:
    """Run ``cmd`` with stdout+stderr captured. ``ROOT`` is always the cwd.

    When ``uv`` isn't on PATH (typical for CI) we strip a leading ``uv run``
    so the command falls back to whichever Python is active. Being explicit
    about cwd matters because sub-agent threads reset it between Bash
    calls — relative paths like ``src/`` or ``scripts/`` must resolve here.
    """
    if not _HAS_UV and cmd[:2] == ["uv", "run"]:
        cmd = cmd[2:]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    return proc.returncode, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_tests() -> CheckResult:
    """Run the unit suite. The integration suite is too slow for preflight."""
    rc, out = _run(["uv", "run", "pytest", "tests/unit/", "-q"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    # Sample line: ``422 passed in 2.03s``.
    m = re.search(r"(\d+) passed", out)
    count = m.group(1) if m else "?"
    return CheckResult(True, f"{count} passed", out)


def check_lint() -> CheckResult:
    """Ruff over ``src/`` and ``tests/``. Exit code is the source of truth."""
    rc, out = _run(["uv", "run", "ruff", "check", "src/", "tests/"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    return CheckResult(True, "clean", out)


def check_types() -> CheckResult:
    """Strict-mode pyright. Pyright reports the summary on its last line."""
    rc, out = _run(["uv", "run", "pyright", "src/agentcloak/"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    m = re.search(r"(\d+) errors?", out)
    count = m.group(1) if m else "0"
    return CheckResult(True, f"{count} errors", out)


def check_surface() -> CheckResult:
    """Cross-check daemon routes / MCP tools / CLI commands all line up."""
    rc, out = _run(["uv", "run", "python", "scripts/check_surface_count.py"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    routes = re.search(r"Daemon routes\s*:\s*(\d+)", out)
    tools = re.search(r"MCP tools\s*:\s*(\d+)", out)
    groups = re.search(r"CLI groups\s*:\s*(\d+)", out)
    if routes and tools and groups:
        summary = f"{routes.group(1)}/{tools.group(1)}/{groups.group(1)} aligned"
    else:
        summary = "aligned"
    return CheckResult(True, summary, out)


def check_client() -> CheckResult:
    """Confirm ``DaemonClient`` exposes both async + sync methods per route."""
    rc, out = _run(["uv", "run", "python", "scripts/generate_client.py", "--check"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    return CheckResult(True, "0 drift", out)


def check_skill() -> CheckResult:
    """Ensure ``commands-reference.md`` matches the freshly rendered version."""
    rc, out = _run(["uv", "run", "python", "scripts/generate_skill.py", "--check"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    return CheckResult(True, "in sync", out)


def check_skill_data() -> CheckResult:
    """Mirror under ``src/agentcloak/_skill_data/`` must match ``skills/``.

    The editable skill bundle lives at ``skills/agentcloak/`` (where authors
    edit ``SKILL.md``); the wheel ships the same files from
    ``src/agentcloak/_skill_data/agentcloak/`` so ``cloak skill install``
    can read them via :mod:`importlib.resources`. Drift means the next
    release would ship a stale bundle to users — fail loudly here instead.
    Resolved with ``python scripts/sync_skill_data.py``.
    """
    rc, out = _run(["uv", "run", "python", "scripts/sync_skill_data.py", "--check"])
    if rc != 0:
        return CheckResult(False, "FAIL", out)
    m = re.search(r"\((\d+) files\)", out)
    count = m.group(1) if m else "?"
    return CheckResult(True, f"{count} files in sync", out)


def check_config() -> CheckResult:
    """Every ``AgentcloakConfig`` field must show up in ``config.md``.

    ``config.py`` is the source of truth — when a field is added there it
    needs a matching row in the env-var reference table. We resolve each
    dataclass field to its associated ``_env("KEY")`` calls (by walking the
    file top-down and remembering the most recent ``cfg.<field>`` assignment)
    and then verify that ``AGENTCLOAK_<KEY>`` appears somewhere in the docs.

    Fields without an env-var binding (none today, but in principle config-
    file-only) fall back to matching the snake_case field name directly.
    """
    from dataclasses import fields

    from agentcloak.core.config import AgentcloakConfig

    config_text = (SRC / "agentcloak" / "core" / "config.py").read_text(
        encoding="utf-8"
    )
    docs_text = (DOCS / "en" / "reference" / "config.md").read_text(encoding="utf-8")

    # Walk the load_config body line-by-line, threading the "currently
    # assigned field" so each _env("KEY") attaches to the right field.
    field_to_envs: dict[str, list[str]] = {f.name: [] for f in fields(AgentcloakConfig)}
    current_field: str | None = None
    field_assign_re = re.compile(r"cfg\.(\w+)\s*=")
    env_call_re = re.compile(r'_env\("(\w+)"\)')
    for line in config_text.splitlines():
        m_field = field_assign_re.search(line)
        if m_field and m_field.group(1) in field_to_envs:
            current_field = m_field.group(1)
        # _env(...) calls — only credit when we've seen a field anchor.
        if current_field is not None:
            for env_key in env_call_re.findall(line):
                field_to_envs[current_field].append(env_key)

    missing: list[str] = []
    for field_name, envs in field_to_envs.items():
        if envs:
            if any(f"AGENTCLOAK_{key}" in docs_text for key in envs):
                continue
            missing.append(
                f"{field_name} — env var(s) {envs} not in docs/en/reference/config.md"
            )
        else:
            # No env binding — fall back to a textual match.
            if field_name in docs_text:
                continue
            missing.append(
                f"{field_name} — no env binding and snake_case name absent from docs"
            )

    total = len(field_to_envs)
    if missing:
        return CheckResult(
            False,
            f"FAIL ({len(missing)} undocumented)",
            "Fields in code but not in docs/en/reference/config.md:\n"
            + "\n".join(f"  - {m}" for m in missing),
        )
    return CheckResult(
        True,
        "all fields documented",
        f"{total} dataclass fields ↔ docs verified",
    )


def check_version() -> CheckResult:
    """Pyproject version, installed ``__version__``, and docs all agree.

    ``__version__`` reads from ``importlib.metadata`` so a forgotten
    ``pip install -e .`` after bumping pyproject.toml will surface here.
    The install docs are also scanned for hard-coded ``v0.X.Y`` references
    that haven't been bumped along with the release.
    """
    from agentcloak import __version__

    pyproj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pyproj_version = pyproj["project"]["version"]

    if pyproj_version != __version__:
        return CheckResult(
            False,
            "FAIL",
            f"pyproject.toml version ({pyproj_version}) != installed package "
            f"__version__ ({__version__}). Reinstall with `pip install -e .` "
            "(or `uv sync`) to refresh the metadata.",
        )

    # Hard-coded version refs in install docs (we tolerate the current
    # version — e.g. "the default in v0.2.0 changed to …" — but flag older
    # ones that would mislead a reader).
    install_md = (DOCS / "en" / "getting-started" / "installation.md").read_text(
        encoding="utf-8"
    )
    refs = re.findall(r"\bv(\d+\.\d+\.\d+)\b", install_md)
    stale = sorted({r for r in refs if r != pyproj_version})
    if stale:
        return CheckResult(
            False,
            "FAIL",
            f"docs/en/getting-started/installation.md mentions v{stale} but "
            f"pyproject.toml is at v{pyproj_version}. Update or remove the "
            "outdated references.",
        )

    return CheckResult(
        True,
        f"{pyproj_version} everywhere",
        f"pyproject + __version__ + installation.md all on v{pyproj_version}",
    )


def check_smoke() -> CheckResult:
    """Invoke ``--help`` for every registered typer group.

    This catches import-time errors (a typo in a new command module would
    break ``agentcloak --help`` itself) and silently-skipped subcommands —
    cheaply, without spawning 18 subprocesses. ``CliRunner`` shares one
    Python interpreter, keeping the whole check well under a second.
    """
    from typer.testing import CliRunner

    from agentcloak.cli.app import app

    runner = CliRunner()
    # ``g.name`` is typed ``str | None`` (typer permits anonymous groups),
    # but every group in this app is registered with an explicit name.
    # Filter the Nones to keep ``CliRunner.invoke`` happy.
    groups: list[str] = [g.name for g in app.registered_groups if g.name]
    failures: list[str] = []
    for grp in groups:
        result = runner.invoke(app, [grp, "--help"])
        if result.exit_code != 0:
            failures.append(f"  - `agentcloak {grp} --help` exited {result.exit_code}")
            if result.exception:
                exc = result.exception
                failures.append(f"    {type(exc).__name__}: {exc}")
            if result.output:
                # Show the first few lines so the cause is visible inline.
                for ln in result.output.splitlines()[:5]:
                    failures.append(f"    {ln}")
    if failures:
        return CheckResult(False, "FAIL", "\n".join(failures))
    return CheckResult(True, f"{len(groups)} commands OK", "")


def check_skill_coverage() -> CheckResult:
    """Cross-check SKILL.md command mentions against actual CLI commands.

    Extracts ``cloak <cmd>`` references from SKILL.md and compares them
    against the registered typer groups + top-level shortcuts. Reports
    CLI commands missing from SKILL.md (undocumented) and SKILL.md commands
    not found in the CLI (stale).
    """
    skill_path = ROOT / "skills" / "agentcloak" / "SKILL.md"
    if not skill_path.is_file():
        return CheckResult(False, "FAIL", f"{skill_path} not found")

    skill_text = skill_path.read_text(encoding="utf-8")

    # Extract "cloak <word>" from SKILL.md (skip code fence language tags)
    skill_cmds: set[str] = set()
    for m in re.finditer(r"`cloak\s+(\w+)", skill_text):
        cmd = m.group(1)
        if cmd not in ("navigate", "snapshot", "screenshot"):
            # Top-level shortcuts are aliases — map them to their group
            skill_cmds.add(cmd)
        else:
            skill_cmds.add(cmd)

    # Get registered CLI groups from the typer app
    from agentcloak.cli.app import app as cli_app

    cli_groups: set[str] = {g.name for g in cli_app.registered_groups if g.name}

    # Top-level shortcut commands (registered directly, not as groups)
    from agentcloak.cli.app import _register_shortcuts  # noqa: F401

    cli_commands: set[str] = set()
    for cmd_info in cli_app.registered_commands:
        if cmd_info.name:
            cli_commands.add(cmd_info.name)

    all_cli = cli_groups | cli_commands

    missing_from_skill = sorted(all_cli - skill_cmds)
    stale_in_skill = sorted(skill_cmds - all_cli)

    # SKILL.md uses shortcuts (``cloak click``) not full paths
    # (``cloak do click``), so subcommand names appear without their
    # parent group. Parent groups (browser/daemon/do/js) are containers
    # that users invoke through subcommands — they don't need direct
    # SKILL.md mentions.
    shortcuts = {
        "click",
        "fill",
        "type",
        "scroll",
        "hover",
        "select",
        "press",
        "keydown",
        "keyup",
        "navigate",
        "snapshot",
        "screenshot",
        "resume",
        "evaluate",
        "batch",
    }
    # ``skill`` is the user-facing skill-bundle installer (``cloak skill
    # install``); SKILL.md targets the agent's runtime needs and shouldn't
    # mention the installation command.
    parent_groups = {"browser", "daemon", "do", "js", "skill"}
    skip = shortcuts | parent_groups
    stale_in_skill = [s for s in stale_in_skill if s not in skip]
    missing_from_skill = [m for m in missing_from_skill if m not in skip]

    issues: list[str] = []
    if missing_from_skill:
        issues.append(f"CLI commands not in SKILL.md: {missing_from_skill}")
    if stale_in_skill:
        issues.append(f"SKILL.md mentions not in CLI: {stale_in_skill}")

    if issues:
        return CheckResult(False, "FAIL", "\n".join(issues))

    covered = len(skill_cmds & (all_cli | shortcuts))
    return CheckResult(True, f"{covered} commands covered", "")


# Order matters: cheap structural checks first so a typo fails fast before
# we sit through pytest. Tests still go first for the "is everything sane?"
# baseline; subsequent checks are sorted roughly by runtime.
CHECKS: dict[str, tuple[str, Callable[[], CheckResult]]] = {
    "tests": ("Unit tests", check_tests),
    "lint": ("Lint", check_lint),
    "types": ("Type check", check_types),
    "surface": ("Surface consistency", check_surface),
    "client": ("Client drift", check_client),
    "skill": ("Skill reference sync", check_skill),
    "skill_cov": ("Skill coverage", check_skill_coverage),
    "skill_data": ("Skill data mirror", check_skill_data),
    "config": ("Config docs sync", check_config),
    "version": ("Version consistency", check_version),
    "smoke": ("CLI smoke test", check_smoke),
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Width of the "[N/M] <name> ..." prefix before the status column. The
# longest label we render today is "Skill reference sync" (20 chars); 40
# leaves room for a few more characters of prefix without realigning.
_LINE_WIDTH = 40


def _format_line(idx: int, total: int, name: str, status: str) -> str:
    """Render a single progress line, padded with dots for alignment."""
    header = f"[{idx}/{total}] {name} "
    return f"{header.ljust(_LINE_WIDTH, '.')} {status}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pre-release quality gate — every automated check, in one go.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--only",
        choices=sorted(CHECKS.keys()),
        help="Run only the named check (e.g. `--only smoke`).",
    )
    selection.add_argument(
        "--skip",
        action="append",
        choices=sorted(CHECKS.keys()),
        default=[],
        metavar="NAME",
        help=(
            "Skip the named check (repeatable). Handy in CI when another job "
            "owns that step — e.g. `--skip tests` because the matrix job "
            "already runs pytest on 3.12 + 3.13."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every check's full output, not just failures.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    selected: dict[str, tuple[str, Callable[[], CheckResult]]]
    if args.only:
        selected = {args.only: CHECKS[args.only]}
    elif args.skip:
        selected = {k: v for k, v in CHECKS.items() if k not in set(args.skip)}
    else:
        selected = CHECKS

    total = len(selected)
    failures: list[tuple[str, CheckResult]] = []
    for idx, (_, (name, fn)) in enumerate(selected.items(), start=1):
        result = fn()
        tick = "OK" if result.passed else "FAIL"
        status = f"{result.summary} [{tick}]"
        print(_format_line(idx, total, name, status), flush=True)
        if not result.passed:
            failures.append((name, result))
        elif args.verbose and result.detail:
            for ln in result.detail.rstrip().splitlines():
                print(f"    {ln}")

    print()
    if failures:
        print(f"--- {len(failures)} preflight check(s) failed ---")
        for name, result in failures:
            print()
            print(f"### {name}")
            print(result.detail.rstrip() or "(no detail captured)")
        return 1
    plural = "s" if total != 1 else ""
    print(f"--- All {total} preflight check{plural} passed ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
