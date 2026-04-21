# forge-template

> Your GitHub activity dashboard in the terminal.

A persistent cockpit for monitoring open PRs, CI status, and repository health — without leaving your editor.


---

<div align="center">

![Status](https://img.shields.io/badge/status-active-63C5EA?style=flat-square&labelColor=404E5C)
![License](https://img.shields.io/badge/license-MIT-9F7EBE?style=flat-square&labelColor=404E5C)
![Org](https://img.shields.io/badge/org-fynes--forge-ECDA90?style=flat-square&labelColor=404E5C)

</div>

---

## Overview

Developed as part of the Fynes-Forge blog, this lightweight cli provides a clean and perisitant dashboard for your Github activity.

This is a Fynes Forge project built with **precision over cleverness**.

---

## Quick Start

```bash
# Install with uv
uv tool install .

# Or run directly during development
uv run devpulse --help
```

## Setup

```bash
devpulse login
```

Prompts for a [GitHub Personal Access Token](https://github.com/settings/tokens). Requires `repo` and `read:org` scopes. Saved to `~/.devpulse.json`.

Alternatively, set the `GITHUB_TOKEN` environment variable — it takes priority over the config file.

## Commands

```bash
# Summary of a repository (formatted)
devpulse summary astral-sh/uv

# Raw JSON output (pipe-friendly)
devpulse summary astral-sh/uv --raw

# Full pulse dashboard
devpulse pulse astral-sh/uv

# Launch interactive TUI
devpulse ui
# or
devpulse-ui
```

## Tech Stack

- **[Typer](https://typer.tiangolo.com/)** — CLI framework
- **[httpx](https://www.python-httpx.org/)** — Async-capable HTTP client
- **[Rich](https://rich.readthedocs.io/)** — Terminal formatting & layout
- **[Textual](https://textual.textualize.io/)** — Interactive TUI framework
- **[Pydantic](https://docs.pydantic.dev/)** — Config validation

## Project Structure

```
src/devpulse/
├── __init__.py
├── cli.py        # Typer command definitions
├── client.py     # GitHub API logic (sync + async)
├── config.py     # Token management
├── renderer.py   # Rich formatting (shared between CLI and TUI)
└── tui.py        # Textual app and widgets
```

## Blog Series

This project was built as part of a three-part blog series on [Fynes Forge](https://fynes-forge.github.io):

- **Part 1: The Skeleton** — Typer + httpx + GitHub API
- **Part 2: The Facelift** — Rich tables, panels, and dashboards
- **Part 3: The Cockpit** — Textual interactive TUI

## Security

Tokens are never hardcoded. They live in `~/.devpulse.json` (mode 600) or `GITHUB_TOKEN`. The config file is gitignored by default.

---

## Project Structure

```
<repo-name>/
├── .github/
│   ├── workflows/          ← CI/CD pipelines
│   ├── ISSUE_TEMPLATE/     ← Bug reports, feature requests
│   ├── PULL_REQUEST_TEMPLATE/
│   └── copilot/            ← GitHub Copilot instructions
├── docs/                   ← Documentation
├── src/                    ← Source code
├── tests/                  ← Test suite
├── AGENTS.md               ← AI agent conventions
├── CONTRIBUTING.md         ← Contribution guide
├── CHANGELOG.md            ← Release history
└── README.md               ← This file
```

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.

---

## Licence

MIT © [Fynes Forge](https://github.com/fynes-forge) — see [LICENSE](./LICENSE) for details.
