"""DevPulse TUI — Textual interactive dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
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
from devpulse.config import add_pinned_repo, load_config, remove_pinned_repo
from devpulse.renderer import (
    COLORS,
    render_pr_table,
    render_repo_panel,
    render_workflow_table,
)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RepoData:
    """Holds fetched data for a single repository."""
    repo: dict = field(default_factory=dict)
    prs: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Modal screens
# ---------------------------------------------------------------------------

class PinRepoScreen(ModalScreen[str | None]):
    """Modal dialog to pin a new repository."""

    CSS = """
    PinRepoScreen {
        align: center middle;
    }

    #pin-dialog {
        width: 60;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #pin-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #pin-input {
        margin-bottom: 1;
    }

    #pin-buttons {
        height: auto;
        align: right middle;
    }

    Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="pin-dialog"):
            yield Label("📌 Pin a Repository", id="pin-title")
            yield Label("Enter in owner/name format (e.g. astral-sh/uv):")
            yield Input(placeholder="owner/repo", id="pin-input")
            with Horizontal(id="pin-buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Pin", variant="primary", id="confirm")

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm")
    def confirm(self) -> None:
        value = self.query_one("#pin-input", Input).value.strip()
        if value and "/" in value:
            self.dismiss(value)
        else:
            self.query_one("#pin-input", Input).border_subtitle = "Invalid format"

    @on(Input.Submitted)
    def on_submit(self) -> None:
        self.confirm()


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class RepoListItem(ListItem):
    """A single repository entry in the sidebar list."""

    def __init__(self, repo: str) -> None:
        super().__init__()
        self.repo = repo

    def compose(self) -> ComposeResult:
        yield Label(self.repo)


class RepoPanel(Static):
    """The main content area — renders data for the selected repo."""

    BORDER_TITLE = "Repository Pulse"

    def compose(self) -> ComposeResult:
        yield LoadingIndicator()

    def show_loading(self) -> None:
        """Switch to the loading state."""
        try:
            self.query("#repo-content").first().remove()
        except Exception:
            pass
        self.query_one(LoadingIndicator).display = True

    def show_placeholder(self) -> None:
        """Show the 'select a repo' placeholder."""
        self.query_one(LoadingIndicator).display = False
        try:
            self.query("#repo-content").first().remove()
        except Exception:
            pass
        placeholder = Label(
            "Select a repository from the sidebar to view its pulse.",
            id="repo-content",
        )
        placeholder.styles.color = COLORS["subtext"]
        placeholder.styles.content_align = ("center", "middle")
        placeholder.styles.height = "1fr"
        self.mount(placeholder)

    def show_data(self, data: RepoData) -> None:
        """Render fetched repository data."""
        self.query_one(LoadingIndicator).display = False
        try:
            self.query("#repo-content").first().remove()
        except Exception:
            pass

        if data.error:
            error_label = Label(f"⚠️  {data.error}", id="repo-content")
            error_label.styles.color = COLORS["red"]
            error_label.styles.padding = (2, 2)
            self.mount(error_label)
            return

        content = Vertical(id="repo-content")
        self.mount(content)

        content.mount(Static(render_repo_panel(data.repo)))

        row = Horizontal()
        content.mount(row)

        pr_static = Static(render_pr_table(data.prs), classes="half-panel")
        ci_static = Static(render_workflow_table(data.runs), classes="half-panel")
        row.mount(pr_static)
        row.mount(ci_static)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DevPulseApp(App):
    """DevPulse — GitHub activity dashboard in the terminal."""

    TITLE = "DevPulse"
    SUB_TITLE = "GitHub Activity Dashboard"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 5;
        background: #1e1e2e;
    }

    #sidebar {
        column-span: 1;
        border: solid #313244;
        border-title-color: #89b4fa;
        padding: 0 1;
        background: #181825;
    }

    #sidebar-title {
        color: #89b4fa;
        text-style: bold;
        padding: 1 0 0 0;
    }

    #repo-list {
        height: 1fr;
        background: #181825;
    }

    RepoListItem {
        padding: 0 1;
        color: #cdd6f4;
    }

    RepoListItem:hover {
        background: #313244;
    }

    RepoListItem.--highlight {
        background: #313244;
        color: #89b4fa;
        text-style: bold;
    }

    #sidebar-footer {
        color: #6c7086;
        padding: 1 0;
        text-style: italic;
    }

    #main {
        column-span: 4;
        padding: 0 1;
    }

    #repo-panel {
        height: 1fr;
        border: solid #313244;
        border-title-color: #89b4fa;
    }

    .half-panel {
        width: 1fr;
    }

    LoadingIndicator {
        height: 5;
        color: #89b4fa;
    }

    Footer {
        background: #181825;
    }

    Header {
        background: #181825;
        color: #89b4fa;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+r", "refresh", "Refresh", priority=True),
        Binding("ctrl+p", "pin_repo", "Pin repo"),
        Binding("ctrl+u", "unpin_repo", "Unpin"),
        Binding("q", "quit", "Quit"),
    ]

    selected_repo: reactive[str | None] = reactive(None, always_update=False)

    def __init__(self) -> None:
        super().__init__()
        self._token: str | None = None
        self._client: AsyncGitHubClient | None = None
        self._pinned: list[str] = []

    def on_mount(self) -> None:
        config = load_config()
        if config is None:
            self.exit(message="No GitHub token found. Run `devpulse login` first.")
            return

        self._token = config.github_token
        self._client = AsyncGitHubClient(token=self._token)
        self._pinned = list(config.pinned_repos)

        if self._pinned:
            # Pre-select the first repo
            self.call_after_refresh(self._select_first)
        else:
            self.query_one(RepoPanel).show_placeholder()

    def _select_first(self) -> None:
        repo_list = self.query_one("#repo-list", ListView)
        if repo_list.children:
            repo_list.index = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with ScrollableContainer(id="sidebar"):
                yield Label("📌 Pinned Repos", id="sidebar-title")
                with ListView(id="repo-list"):
                    for repo in self._pinned:
                        yield RepoListItem(repo)
                yield Label(
                    "ctrl+p to pin  •  ctrl+u to unpin",
                    id="sidebar-footer",
                )

            with Container(id="main"):
                yield RepoPanel(id="repo-panel")

        yield Footer()

    def watch_selected_repo(self, repo: str | None) -> None:
        """Called automatically when selected_repo reactive changes."""
        if repo is None:
            return
        panel = self.query_one(RepoPanel)
        panel.show_loading()
        self._load_repo(repo)

    @work(exclusive=True)
    async def _load_repo(self, repo: str) -> None:
        """Fetch repo data in the background — never blocks the UI thread."""
        panel = self.query_one(RepoPanel)

        if self._client is None:
            panel.show_data(RepoData(error="Client not initialised."))
            return

        try:
            repo_data = await self._client.get_repo(repo)
            prs = await self._client.get_open_prs(repo)
            runs = await self._client.get_workflow_runs(repo)
            panel.show_data(RepoData(repo=repo_data, prs=prs, runs=runs))
        except RateLimitWarning as e:
            panel.show_data(RepoData(error=str(e)))
            self.notify(str(e), title="Rate Limit Warning", severity="warning")
        except GitHubAPIError as e:
            panel.show_data(RepoData(error=str(e)))
        except Exception as e:
            panel.show_data(RepoData(error=f"Unexpected error: {e}"))

    @on(ListView.Selected)
    def on_repo_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, RepoListItem):
            self.selected_repo = event.item.repo

    def action_refresh(self) -> None:
        """Refresh the currently selected repository."""
        if self.selected_repo:
            panel = self.query_one(RepoPanel)
            panel.show_loading()
            self._load_repo(self.selected_repo)
            self.notify(f"Refreshing {self.selected_repo}...", timeout=2)

    async def action_pin_repo(self) -> None:
        """Open the pin repo dialog."""
        repo = await self.push_screen_wait(PinRepoScreen())
        if repo is None:
            return

        if add_pinned_repo(repo):
            self._pinned.append(repo)
            repo_list = self.query_one("#repo-list", ListView)
            await repo_list.append(RepoListItem(repo))
            self.notify(f"Pinned {repo}", timeout=2)
        else:
            self.notify(f"{repo} is already pinned.", severity="warning", timeout=2)

    def action_unpin_repo(self) -> None:
        """Unpin the currently selected repository."""
        if not self.selected_repo:
            self.notify("No repository selected.", severity="warning", timeout=2)
            return

        repo = self.selected_repo
        if remove_pinned_repo(repo):
            self._pinned.remove(repo)
            # Remove from sidebar list
            repo_list = self.query_one("#repo-list", ListView)
            for item in repo_list.query(RepoListItem):
                if item.repo == repo:
                    item.remove()
                    break
            self.selected_repo = None
            self.query_one(RepoPanel).show_placeholder()
            self.notify(f"Unpinned {repo}", timeout=2)

    async def on_unmount(self) -> None:
        if self._client is not None:
            await self._client.close()


def run() -> None:
    """Entry point for `devpulse-ui` and `devpulse ui`."""
    app = DevPulseApp()
    app.run()


if __name__ == "__main__":
    run()
