# Contributing to agentcloak

Thanks for your interest in contributing. This guide covers setup, code style, testing, and PR workflow.

## Quick Setup

```bash
git clone https://github.com/shayuc137/agentcloak.git
cd agentcloak
pip install -e ".[dev,mcp,stealth]"
```

The CloakBrowser binary (~200 MB) downloads automatically on first use. No manual browser install needed.

**Headless Linux servers** also need Xvfb for CloakBrowser's headed mode:

```bash
sudo apt-get install -y xvfb
```

## Development Workflow

1. Create a branch from `main`:

   ```bash
   git checkout -b feat/my-feature
   ```

2. Make your changes

3. Run lint and type checks:

   ```bash
   ruff check src/
   ruff format --check src/
   pyright src/
   ```

4. Run tests:

   ```bash
   pytest tests/unit/ -x           # fast unit tests
   pytest tests/integration/ -x    # needs daemon + browser
   ```

5. Run the consistency check (verifies CLI/MCP/daemon route alignment):

   ```bash
   python3 scripts/check_consistency.py
   ```

6. Push and open a PR

## Code Style

**Linting:** [ruff](https://docs.astral.sh/ruff/) with the project config in `pyproject.toml`. The rule set includes pycodestyle, pyflakes, isort, pyupgrade, bugbear, and simplify.

```bash
ruff check src/              # lint
ruff format src/             # format
```

**Type checking:** [pyright](https://github.com/microsoft/pyright) in strict mode.

```bash
pyright src/
```

**General rules:**

- Target Python 3.12+
- Line length: 88 characters
- Use `from __future__ import annotations` is not needed (3.12+ native)
- Prefer `X | Y` union syntax over `Union[X, Y]`

## Project Structure

```
src/agentcloak/
  cli/          # typer CLI commands (talks to daemon over HTTP)
  daemon/       # aiohttp daemon (manages browser lifecycle)
  browser/      # browser backends (BrowserContext protocol)
  core/         # shared utilities, config, types
  mcp/          # MCP server (FastMCP, talks to daemon over HTTP)
  spells/       # spell registry and built-in spells
  bridge/       # RemoteBridge (Chrome extension + WS hub)
```

## Layer Isolation

Layer boundaries are strictly enforced:

| Layer | Can import | Cannot import |
|-------|-----------|---------------|
| `cli/` | daemon HTTP API | `browser/`, `daemon/` internals |
| `daemon/` | `browser/`, `core/` | `cli/` |
| `browser/` | `core/` | `cli/`, `daemon/` |
| `core/` | stdlib + third-party | any sibling layer |
| `spells/` | `core/`, `browser/protocol` | `daemon/`, `cli/` |
| `mcp/` | `core/`, `spells/`, daemon HTTP API | `browser/`, `daemon/` internals |

## Adding a New Feature

When adding a new capability, it must be exposed through the full stack:

1. **Daemon route** in `src/agentcloak/daemon/routes.py`
2. **CLI command** in `src/agentcloak/cli/commands/`
3. **MCP tool** in `src/agentcloak/mcp/tools/`
4. **Skill file** update in `skills/agentcloak/SKILL.md` and `.claude/skills/agentcloak/SKILL.md`

Run `python3 scripts/check_consistency.py` to verify alignment across all three layers.

## Testing

**Unit tests** (`tests/unit/`): fast, no browser or daemon needed. These run in CI on every push.

**Integration tests** (`tests/integration/`): require a running daemon and browser. These run in CI but can also be run locally.

```bash
pytest tests/unit/ -x           # quick feedback loop
pytest tests/ -x                # everything
```

Mark tests that need network access:

```python
@pytest.mark.network
def test_real_site():
    ...
```

## Pull Request Guidelines

- One logical change per PR
- Include tests for new functionality
- Update documentation if behavior changes (README, docs/, Skill files)
- Link to a relevant issue if one exists
- CI must pass: ruff + pyright + pytest + check_consistency

## CI

GitHub Actions runs on every push and PR:

- **ruff** lint + format check
- **pyright** strict type checking
- **pytest** unit tests (Python 3.12 + 3.13 matrix)
- **integration tests** with daemon + browser
- **build** verification (wheel + sdist)
- **pip-audit** dependency vulnerability scan
- **check_consistency** CLI/MCP/daemon alignment

## Questions?

Open a [discussion](https://github.com/shayuc137/agentcloak/discussions) or file an [issue](https://github.com/shayuc137/agentcloak/issues).
