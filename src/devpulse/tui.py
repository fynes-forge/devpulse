from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    Static,
)

from devpulse.client import AsyncGitHubClient, GitHubAPIError, RateLimitWarning
from devpulse.config import load_config
from devpulse.renderer import (
    COLORS,
    _ci_status_text,
    _relative_time,
    render_pr_table,
    render_repo_panel,
    render_workflow_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avg_commits_per_day(activity: list[dict]) -> float:
    if not activity:
        return 0.0
    recent = activity[-4:]
    total = sum(w.get("total", 0) for w in recent)
    return total / (len(recent) * 7) if recent else 0.0


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RepoData:
    slug: str = ""
    repo: dict = field(default_factory=dict)
    prs: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)
    commit_activity: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class OverviewData:
    repos: list[RepoData] = field(default_factory=list)
    total_open_prs: int = 0
    total_open_issues: int = 0
    total_stars: int = 0
    failing_repos: list[str] = field(default_factory=list)
    passing_repos: list[str] = field(default_factory=list)
    avg_commits_per_day: float = 0.0
    stale_prs: list[tuple[str, dict]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sidebar list items
# ---------------------------------------------------------------------------

class SectionHeader(ListItem):
    """Non-selectable section divider in the sidebar."""

    DISABLED = True

    def __init__(self, title: str) -> None:
        super().__init__(disabled=True)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Label(self._title)


class OverviewItem(ListItem):
    """The top-level Overview entry."""

    def compose(self) -> ComposeResult:
        yield Label("  📊 Overview")


class RepoItem(ListItem):
    """A single repo in the sidebar list."""

    def __init__(self, slug: str, is_pinned: bool = False) -> None:
        super().__init__()
        self.slug = slug
        self.is_pinned = is_pinned
        # Display just the repo name, not the full owner/name
        self._display = slug.split("/")[-1] if "/" in slug else slug

    def compose(self) -> ComposeResult:
        yield Label(f"  ⚪ {self._display}")

    def set_status(self, passing: bool | None) -> None:
        icon = "🟢" if passing is True else "🔴" if passing is False else "⚪"
        self.query_one(Label).update(f"  {icon} {self._display}")


# ---------------------------------------------------------------------------
# Overview panel
# ---------------------------------------------------------------------------

class OverviewPanel(Static):
    """Aggregated stats across all loaded repos."""

    DEFAULT_CSS = "OverviewPanel { height: 1fr; overflow-y: auto; }"

    def compose(self) -> ComposeResult:
        yield LoadingIndicator()

    def _clear(self) -> None:
        for node in self.query(".ov"):
            node.remove()

    def show_loading(self) -> None:
        self._clear()
        self.query_one(LoadingIndicator).display = True

    def show_empty(self) -> None:
        self.query_one(LoadingIndicator).display = False
        self._clear()
        lbl = Label(
            "No repositories found. Make sure your token has the correct scopes.",
            classes="ov",
        )
        lbl.styles.color = COLORS["subtext"]
        lbl.styles.padding = (2, 2)
        self.mount(lbl)

    def show_data(self, data: OverviewData) -> None:
        self.query_one(LoadingIndicator).display = False
        self._clear()
        self.mount(Static(self._headline(data), classes="ov"))
        self.mount(Static(self._health_table(data), classes="ov"))
        if data.stale_prs:
            self.mount(Static(self._stale_table(data.stale_prs), classes="ov"))

    # ── Renderables ──────────────────────────────────────────────────────

    def _headline(self, data: OverviewData) -> Panel:
        t = Text()

        def stat(icon: str, val: str, lbl: str, col: str) -> None:
            t.append(f"  {icon} ")
            t.append(val, style=f"bold {col}")
            t.append(f" {lbl}   ", style=COLORS["subtext"])

        stat("🔀", str(data.total_open_prs), "open PRs", COLORS["blue"])
        stat("🐛", str(data.total_open_issues), "open issues", COLORS["peach"])
        stat("⭐", f"{data.total_stars:,}", "stars", COLORS["yellow"])
        stat("📈", f"{data.avg_commits_per_day:.1f}",
             "avg commits/day", COLORS["green"])
        t.append("\n")

        n_p, n_f = len(data.passing_repos), len(data.failing_repos)
        if n_p + n_f:
            stat("🟢", str(n_p), "passing CI", COLORS["green"])
            stat("🔴", str(n_f), "failing CI", COLORS["red"])
            t.append("\n")

        return Panel(
            t,
            title=f"[bold {COLORS['blue']}]📊 Overview — {len(data.repos)} repos loaded[/]",
            border_style=COLORS["surface"],
            padding=(1, 1),
        )

    def _health_table(self, data: OverviewData) -> Table:
        tbl = Table(
            title="Repository Health",
            box=box.ROUNDED,
            border_style=COLORS["surface"],
            header_style=f"bold {COLORS['blue']}",
            title_style=f"bold {COLORS['blue']}",
            expand=True,
            show_lines=False,
        )
        tbl.add_column("Repository", style=COLORS["text"], ratio=2)
        tbl.add_column("PRs", justify="right", style=COLORS["blue"], width=5)
        tbl.add_column("Issues", justify="right",
                       style=COLORS["peach"], width=7)
        tbl.add_column("Stars", justify="right",
                       style=COLORS["yellow"], width=7)
        tbl.add_column("Last CI", width=13)
        tbl.add_column("Commits/day", justify="right",
                       style=COLORS["green"], width=12)

        for rd in data.repos:
            if rd.error or not rd.repo:
                tbl.add_row(rd.slug, "—", "—", "—", Text(
                    "⚠ error", style=COLORS["red"]), "—")
                continue
            issues = max(0, rd.repo.get("open_issues_count", 0) - len(rd.prs))
            ci = _ci_status_text(rd.runs[0]) if rd.runs else Text(
                "—", style=COLORS["subtext"])
            cpd = _avg_commits_per_day(rd.commit_activity)
            tbl.add_row(
                rd.slug,
                str(len(rd.prs)),
                str(issues),
                f"{rd.repo.get('stargazers_count', 0):,}",
                ci,
                f"{cpd:.1f}" if cpd > 0 else "—",
            )
        return tbl

    def _stale_table(self, stale: list[tuple[str, dict]]) -> Table:
        tbl = Table(
            title=f"⏳ Stale PRs — open > 7 days  ({len(stale)})",
            box=box.SIMPLE,
            border_style=COLORS["surface"],
            header_style=f"bold {COLORS['blue']}",
            title_style=f"bold {COLORS['yellow']}",
            expand=True,
        )
        tbl.add_column("Repo", style=COLORS["mauve"], width=26)
        tbl.add_column("#", style=COLORS["subtext"], width=6, justify="right")
        tbl.add_column("Title", style=COLORS["text"], ratio=3)
        tbl.add_column("Author", style=COLORS["mauve"], width=16)
        tbl.add_column(
            "Open", style=COLORS["yellow"], width=12, justify="right")
        for slug, pr in stale[:15]:
            tbl.add_row(slug, str(pr["number"]), pr["title"],
                        pr["user"]["login"], _relative_time(pr["created_at"]))
        return tbl


# ---------------------------------------------------------------------------
# Per-repo detail panel
# ---------------------------------------------------------------------------

class RepoPanel(Static):
    """Detail view for a single selected repository."""

    DEFAULT_CSS = "RepoPanel { height: 1fr; overflow-y: auto; }"

    def compose(self) -> ComposeResult:
        yield LoadingIndicator()

    def _clear(self) -> None:
        try:
            self.query("#repo-content").first().remove()
        except Exception:
            pass

    def show_loading(self) -> None:
        self._clear()
        self.query_one(LoadingIndicator).display = True

    def show_data(self, data: RepoData) -> None:
        self.query_one(LoadingIndicator).display = False
        self._clear()

        if data.error:
            lbl = Label(f"⚠️  {data.error}", id="repo-content")
            lbl.styles.color = COLORS["red"]
            lbl.styles.padding = (2, 2)
            self.mount(lbl)
            return

        content = Vertical(id="repo-content")
        self.mount(content)
        content.mount(Static(render_repo_panel(data.repo)))
        row = Horizontal()
        content.mount(row)
        row.mount(Static(render_pr_table(data.prs), classes="half-panel"))
        row.mount(Static(render_workflow_table(
            data.runs), classes="half-panel"))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DevPulseApp(App):
    """DevPulse — GitHub activity dashboard in the terminal."""

    TITLE = "DevPulse"
    SUB_TITLE = "GitHub Activity Dashboard"

    CSS = """
    Screen { background: #1e1e2e; }

    /* ── Two-column layout ──────────────────────────────────────── */
    #app-body { layout: horizontal; height: 1fr; }

    /* ── Sidebar ────────────────────────────────────────────────── */
    #sidebar {
        width: 32;
        min-width: 26;
        background: #181825;
        border-right: solid #313244;
    }

    #sidebar-header {
        background: #313244;
        color: #89b4fa;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    #repo-list {
        height: 1fr;
        background: #181825;
        border: none;
        padding: 0;
        overflow-y: auto;
    }

    SectionHeader {
        background: #181825;
        color: #6c7086;
        padding: 0 1;
        text-style: italic;
        height: 1;
    }

    OverviewItem {
        background: #181825;
        color: #cba6f7;
        padding: 0 0;
        text-style: bold;
        height: 1;
    }
    OverviewItem.--highlight { background: #313244; color: #cba6f7; }
    OverviewItem:hover { background: #2a2a3c; }

    RepoItem {
        background: #181825;
        color: #cdd6f4;
        padding: 0 0;
        height: 1;
    }
    RepoItem.--highlight { background: #313244; color: #89b4fa; text-style: bold; }
    RepoItem:hover { background: #2a2a3c; }

    #sidebar-hint {
        color: #6c7086;
        height: 1;
        padding: 0 1;
        text-style: italic;
        background: #181825;
        border-top: solid #313244;
    }

    /* ── Main content ───────────────────────────────────────────── */
    #main { width: 1fr; background: #1e1e2e; padding: 0 1; }

    .half-panel { width: 1fr; }

    LoadingIndicator { height: 5; color: #89b4fa; }

    Footer { background: #181825; }
    Header { background: #181825; color: #89b4fa; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+r", "refresh", "Refresh", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client: AsyncGitHubClient | None = None
        self._username: str = ""
        # All repos fetched from the API, keyed by slug
        self._all_repos: dict[str, dict] = {}
        # Detailed fetch cache
        self._cache: dict[str, RepoData] = {}
        self._selected: str = "overview"

    # ── Lifecycle ──────────────────────────────────────────────────

    def on_mount(self) -> None:
        config = load_config()
        if config is None:
            self.exit(
                message="No GitHub token found. Run `devpulse login` first.")
            return
        self._client = AsyncGitHubClient(token=config.github_token)
        self.call_after_refresh(self._boot)

    def _boot(self) -> None:
        """Kick off the initial repo list fetch after DOM is ready."""
        self.query_one(OverviewPanel).show_loading()
        self._fetch_repo_list()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="app-body"):
            with Vertical(id="sidebar"):
                yield Label("🐙 Repositories", id="sidebar-header")
                with ListView(id="repo-list"):
                    yield OverviewItem()
                    # Repos will be populated by _fetch_repo_list()
                yield Label("↑↓ navigate  enter select  ^r refresh", id="sidebar-hint")
            with ScrollableContainer(id="main"):
                yield OverviewPanel(id="overview-panel")
                rp = RepoPanel(id="repo-panel")
                rp.display = False
                yield rp
        yield Footer()

    # ── Stage 1: fetch the repo list and populate sidebar ──────────

    @work(exclusive=False)
    async def _fetch_repo_list(self) -> None:
        """Fetch the user's full repo list from GitHub and populate the sidebar."""
        if self._client is None:
            return

        try:
            # Fetch user identity and repos in parallel
            user, repos = await asyncio.gather(
                self._client.validate_token(),
                self._client.get_user_repos(),
            )
            self._username = user.get("login", "")
        except Exception as e:
            self.query_one(OverviewPanel).show_empty()
            self.notify(f"Failed to fetch repos: {e}", severity="error")
            return

        if not repos:
            self.query_one(OverviewPanel).show_empty()
            return

        # Store all repos keyed by full slug
        self._all_repos = {r["full_name"]: r for r in repos}

        # Populate the sidebar list
        repo_list = self.query_one("#repo-list", ListView)
        await repo_list.clear()
        await repo_list.append(OverviewItem())

        # Group: user's own repos, then org/collaborator repos
        own = [r for r in repos if r.get(
            "owner", {}).get("login") == self._username]
        other = [r for r in repos if r.get(
            "owner", {}).get("login") != self._username]

        if own:
            await repo_list.append(SectionHeader(f"── {self._username} ({len(own)})"))
            for r in own:
                await repo_list.append(RepoItem(r["full_name"]))

        if other:
            # Group org repos by owner
            orgs: dict[str, list[dict]] = {}
            for r in other:
                owner = r.get("owner", {}).get("login", "other")
                orgs.setdefault(owner, []).append(r)
            for org_name, org_repos in sorted(orgs.items()):
                await repo_list.append(SectionHeader(f"── {org_name} ({len(org_repos)})"))
                for r in org_repos:
                    await repo_list.append(RepoItem(r["full_name"]))

        self.sub_title = f"GitHub Activity Dashboard  •  {self._username}  •  {len(repos)} repos"

        # Now fetch overview data for all repos
        self._load_overview()

    # ── Stage 2: fetch detail data for the overview ─────────────────

    @work(exclusive=True)
    async def _load_overview(self) -> None:
        """Fetch PR + CI data for all repos and render the overview."""
        if not self._all_repos:
            self.query_one(OverviewPanel).show_empty()
            return

        slugs = list(self._all_repos.keys())
        # Fetch in batches of 10 to avoid hammering the API
        results: list[RepoData] = []
        for i in range(0, min(len(slugs), 50), 10):
            batch = slugs[i:i + 10]
            batch_results = await asyncio.gather(*[self._fetch_detail(s) for s in batch])
            results.extend(batch_results)
            for rd in batch_results:
                self._cache[rd.slug] = rd
                self._update_badge(rd)
            # Show incremental overview updates as data arrives
            if results:
                self.query_one(OverviewPanel).show_data(
                    self._aggregate(results))

    async def _fetch_detail(self, slug: str) -> RepoData:
        """Fetch PRs, CI runs, and commit activity for one repo."""
        if self._client is None:
            return RepoData(slug=slug, error="Client not initialised.")
        try:
            prs, runs, activity = await asyncio.gather(
                self._client.get_open_prs(slug),
                self._client.get_workflow_runs(slug),
                self._client.get_commit_activity(slug),
            )
            # Reuse the already-fetched repo metadata from the list
            repo_meta = self._all_repos.get(slug, {})
            return RepoData(slug=slug, repo=repo_meta, prs=prs, runs=runs, commit_activity=activity)
        except RateLimitWarning as e:
            self.notify(str(e), title="Rate Limit Warning", severity="warning")
            return RepoData(slug=slug, repo=self._all_repos.get(slug, {}), error=str(e))
        except GitHubAPIError as e:
            return RepoData(slug=slug, repo=self._all_repos.get(slug, {}), error=str(e))
        except Exception as e:
            return RepoData(slug=slug, repo=self._all_repos.get(slug, {}), error=f"{type(e).__name__}: {e}")

    # ── Aggregation ─────────────────────────────────────────────────

    def _aggregate(self, results: list[RepoData]) -> OverviewData:
        ok = [r for r in results if not r.error and r.repo]
        total_prs = sum(len(r.prs) for r in ok)
        total_issues = sum(
            max(0, r.repo.get("open_issues_count", 0) - len(r.prs)) for r in ok)
        total_stars = sum(r.repo.get("stargazers_count", 0) for r in ok)
        passing = [r.slug for r in ok if r.runs and r.runs[0].get(
            "conclusion") == "success"]
        failing = [r.slug for r in ok if r.runs and r.runs[0].get(
            "conclusion") in ("failure", "timed_out")]
        cpd_vals = [_avg_commits_per_day(r.commit_activity)
                    for r in ok if r.commit_activity]
        avg_cpd = sum(cpd_vals) / len(cpd_vals) if cpd_vals else 0.0

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stale: list[tuple[str, dict]] = []
        for r in ok:
            for pr in r.prs:
                opened = datetime.fromisoformat(
                    pr["created_at"].replace("Z", "+00:00"))
                if opened < cutoff:
                    stale.append((r.slug, pr))
        stale.sort(key=lambda x: x[1]["created_at"])

        return OverviewData(
            repos=results,
            total_open_prs=total_prs,
            total_open_issues=total_issues,
            total_stars=total_stars,
            passing_repos=passing,
            failing_repos=failing,
            avg_commits_per_day=avg_cpd,
            stale_prs=stale,
        )

    def _update_badge(self, rd: RepoData) -> None:
        for item in self.query(RepoItem):
            if item.slug == rd.slug:
                if rd.error or not rd.runs:
                    item.set_status(None)
                else:
                    item.set_status(rd.runs[0].get("conclusion") == "success")
                break

    # ── Navigation ───────────────────────────────────────────────────

    def _show_overview(self) -> None:
        self._selected = "overview"
        self.query_one(OverviewPanel).display = True
        self.query_one(RepoPanel).display = False

    def _show_repo(self, slug: str) -> None:
        self._selected = slug
        self.query_one(OverviewPanel).display = False
        rp = self.query_one(RepoPanel)
        rp.display = True

        if slug in self._cache:
            rp.show_data(self._cache[slug])
        else:
            rp.show_loading()
            self._load_single(slug)

    @work(exclusive=True)
    async def _load_single(self, slug: str) -> None:
        rd = await self._fetch_detail(slug)
        self._cache[slug] = rd
        self._update_badge(rd)
        # Only update display if this repo is still the selected one
        if self._selected == slug:
            self.query_one(RepoPanel).show_data(rd)

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, OverviewItem):
            self._show_overview()
        elif isinstance(event.item, RepoItem):
            self._show_repo(event.item.slug)
        # SectionHeader items are disabled — they won't fire this event

    # ── Actions ──────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        if self._selected == "overview":
            self.query_one(OverviewPanel).show_loading()
            self._cache.clear()
            # Re-fetch the repo list entirely (picks up new/deleted repos)
            self._fetch_repo_list()
            self.notify("Refreshing repo list...", timeout=2)
        else:
            self.query_one(RepoPanel).show_loading()
            self._cache.pop(self._selected, None)
            self._load_single(self._selected)
            self.notify(f"Refreshing {self._selected}...", timeout=2)

    async def on_unmount(self) -> None:
        if self._client is not None:
            await self._client.close()


def run() -> None:
    """Entry point for `devpulse-ui` and `devpulse ui`."""
    DevPulseApp().run()


if __name__ == "__main__":
    run()
