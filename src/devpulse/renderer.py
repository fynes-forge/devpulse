from __future__ import annotations

from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Catppuccin Mocha palette
# Designed with semantic roles in mind — greens, reds, and yellows are
# distinct enough to read as status signals without being aggressive.
# Useful for a dashboard that stays on-screen for hours.
# ---------------------------------------------------------------------------
COLORS: dict[str, str] = {
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "yellow": "#f9e2af",
    "blue": "#89b4fa",
    "mauve": "#cba6f7",
    "peach": "#fab387",
    "text": "#cdd6f4",
    "subtext": "#a6adc8",
    "surface": "#313244",
    "overlay": "#6c7086",
    "base": "#1e1e2e",
}

# Semantic label colors — tunable for your team's label vocabulary.
# Anything not listed here renders in subtext (neutral gray).
LABEL_COLORS: dict[str, str] = {
    "bug": COLORS["red"],
    "wip": COLORS["yellow"],
    "work in progress": COLORS["yellow"],
    "enhancement": COLORS["blue"],
    "feature": COLORS["blue"],
    "documentation": COLORS["mauve"],
    "docs": COLORS["mauve"],
    "good first issue": COLORS["green"],
    "help wanted": COLORS["peach"],
    "blocked": COLORS["red"],
    "breaking change": COLORS["red"],
    "dependencies": COLORS["peach"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_pr_labels(labels: list[dict]) -> Text:
    """Render PR label badges with semantic colors."""
    text = Text()
    for i, label in enumerate(labels):
        name = label["name"].lower()
        color = LABEL_COLORS.get(name, COLORS["subtext"])
        if i > 0:
            text.append(" ")
        text.append(f"[{label['name']}]", style=color)
    return text


def _relative_time(iso_timestamp: str) -> str:
    """Convert ISO 8601 timestamp to a human-readable relative string."""
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = now - dt
    days = delta.days

    if days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        return f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"


def _ci_status_text(run: dict) -> Text:
    """Render a workflow run conclusion as an emoji + colored label."""
    conclusion = run.get("conclusion")
    status = run.get("status")

    if conclusion == "success":
        return Text("🟢 pass", style=COLORS["green"])
    elif conclusion in ("failure", "timed_out"):
        return Text("🔴 fail", style=COLORS["red"])
    elif conclusion == "cancelled":
        return Text("⚫ skip", style=COLORS["overlay"])
    elif conclusion == "skipped":
        return Text("⬜ skip", style=COLORS["subtext"])
    elif status in ("in_progress", "queued", "waiting"):
        return Text("🟡 running", style=COLORS["yellow"])
    else:
        return Text("⬜ unknown", style=COLORS["subtext"])


# ---------------------------------------------------------------------------
# Renderables
# ---------------------------------------------------------------------------

def render_pr_table(prs: list[dict]) -> Table:
    """Render open pull requests as a Rich table with semantic label colors."""
    table = Table(
        box=box.ROUNDED,
        border_style=COLORS["surface"],
        header_style=f"bold {COLORS['blue']}",
        show_lines=True,
        expand=True,
    )

    table.add_column("#", style=COLORS["subtext"], width=6, justify="right")
    table.add_column("Title", style=COLORS["text"], ratio=3)
    table.add_column("Author", style=COLORS["mauve"], width=18)
    table.add_column("Labels", ratio=2)
    table.add_column(
        "Opened", style=COLORS["subtext"], width=12, justify="right")

    for pr in prs:
        labels = _format_pr_labels(pr.get("labels", []))
        table.add_row(
            str(pr["number"]),
            pr["title"],
            pr["user"]["login"],
            labels,
            _relative_time(pr["created_at"]),
        )

    return table


def render_workflow_table(runs: list[dict]) -> Table:
    """Render recent CI workflow runs as a compact status table."""
    table = Table(
        box=box.SIMPLE,
        border_style=COLORS["surface"],
        header_style=f"bold {COLORS['blue']}",
        expand=True,
    )

    table.add_column("Workflow", style=COLORS["text"], ratio=2)
    table.add_column("Branch", style=COLORS["mauve"], ratio=1)
    table.add_column("Status", width=12, justify="center")
    table.add_column("Ran", style=COLORS["subtext"], width=12, justify="right")

    for run in runs[:8]:
        table.add_row(
            run["name"],
            run["head_branch"],
            _ci_status_text(run),
            _relative_time(run["created_at"]),
        )

    return table


def render_repo_panel(repo: dict) -> Panel:
    """Render a summary header panel for a repository."""
    stars = repo["stargazers_count"]
    forks = repo["forks_count"]
    open_issues = repo["open_issues_count"]
    language = repo.get("language") or "Unknown"
    description = repo.get("description") or "No description provided."

    content = Text()
    content.append(description + "\n\n", style=COLORS["text"])
    content.append("⭐ ", style=COLORS["yellow"])
    content.append(f"{stars:,} stars  ", style=COLORS["subtext"])
    content.append("🍴 ", style=COLORS["blue"])
    content.append(f"{forks:,} forks  ", style=COLORS["subtext"])
    content.append("🐛 ", style=COLORS["red"])
    content.append(f"{open_issues:,} open issues  ", style=COLORS["subtext"])
    content.append("📦 ", style=COLORS["mauve"])
    content.append(language, style=COLORS["subtext"])

    return Panel(
        content,
        title=f"[bold {COLORS['blue']}]{repo['full_name']}[/]",
        border_style=COLORS["surface"],
        padding=(1, 2),
    )


def render_pulse_dashboard(repo: dict, prs: list[dict], runs: list[dict]) -> None:
    """Render the full two-panel dashboard layout to the console."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
    )

    layout["body"].split_row(
        Layout(name="prs", ratio=3),
        Layout(name="ci", ratio=2),
    )

    layout["header"].update(render_repo_panel(repo))

    pr_count = len(prs)
    pr_title = (
        f"[bold {COLORS['blue']}]Open Pull Requests[/] "
        f"[{COLORS['subtext']}]({pr_count})[/]"
    )
    if prs:
        layout["prs"].update(
            Panel(render_pr_table(prs), title=pr_title,
                  border_style=COLORS["surface"])
        )
    else:
        layout["prs"].update(
            Panel(
                Text("No open pull requests 🎉",
                     style=COLORS["green"], justify="center"),
                title=pr_title,
                border_style=COLORS["surface"],
            )
        )

    ci_title = f"[bold {COLORS['blue']}]Recent CI Runs[/]"
    if runs:
        layout["ci"].update(
            Panel(
                render_workflow_table(runs),
                title=ci_title,
                border_style=COLORS["surface"],
            )
        )
    else:
        layout["ci"].update(
            Panel(
                Text("No workflow runs found.",
                     style=COLORS["subtext"], justify="center"),
                title=ci_title,
                border_style=COLORS["surface"],
            )
        )

    console.print(layout)


def fetch_with_progress(
    client,  # GitHubClient
    repo: str,
) -> tuple[dict, list[dict], list[dict]]:
    """Fetch all repo data with a Rich progress bar.

    Uses transient=True so the bar disappears after completion,
    keeping the output clean above the rendered dashboard.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching repository metadata...", total=3)

        repo_data = client.get_repo(repo)
        progress.advance(task)
        progress.update(task, description="Fetching open pull requests...")

        prs = client.get_open_prs(repo)
        progress.advance(task)
        progress.update(task, description="Fetching workflow runs...")

        runs = client.get_workflow_runs(repo)
        progress.advance(task)

    return repo_data, prs, runs
