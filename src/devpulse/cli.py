"""DevPulse CLI — Typer command definitions."""
from __future__ import annotations

import json

import typer

from devpulse.client import GitHubAPIError, GitHubClient, RateLimitWarning
from devpulse.config import add_pinned_repo, load_config, remove_pinned_repo, save_token
from devpulse.renderer import console, fetch_with_progress, render_pulse_dashboard

app = typer.Typer(
    name="devpulse",
    help="Your GitHub activity dashboard in the terminal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_client() -> GitHubClient:
    """Return an authenticated client or exit with a helpful error."""
    config = load_config()
    if config is None:
        console.print(
            "[bold red]No GitHub token found.[/] "
            "Run [bold]devpulse login[/] to get started."
        )
        raise typer.Exit(code=1)
    return GitHubClient(token=config.github_token)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def login() -> None:
    """Save a GitHub Personal Access Token to your config.

    Token is validated against the API before saving.
    Stored at [dim]~/.devpulse.json[/] with restricted file permissions.
    """
    console.print(
        "\n[bold]DevPulse Login[/]\n"
        f"Create a token at: [link=https://github.com/settings/tokens]https://github.com/settings/tokens[/link]\n"
        f"Required scopes: [bold]repo[/], [bold]read:org[/]\n"
    )
    token = typer.prompt("GitHub Personal Access Token", hide_input=True)

    with console.status("Validating token..."):
        try:
            with GitHubClient(token=token) as client:
                user = client.validate_token()
        except GitHubAPIError as e:
            console.print(f"[bold red]Token validation failed:[/] {e}")
            raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red]Unexpected error:[/] {e}")
            raise typer.Exit(code=1)

    save_token(token)
    console.print(
        f"\n[bold green]✓ Logged in as[/] [bold]{user['login']}[/]\n"
        f"Token saved to [dim]~/.devpulse.json[/]"
    )


@app.command()
def summary(
    repo: str = typer.Argument(
        help="Repository in owner/name format, e.g. [bold]astral-sh/uv[/]"
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Output raw JSON (pipe-friendly)"
    ),
) -> None:
    """Show a summary of a repository's current activity."""
    with get_client() as client:
        try:
            repo_data, prs, runs = fetch_with_progress(client, repo)
        except RateLimitWarning as e:
            console.print(f"[bold yellow]⚠️  Rate limit warning:[/] {e}")
            raise typer.Exit(code=1)
        except GitHubAPIError as e:
            console.print(f"[bold red]GitHub API error:[/] {e}")
            raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
            raise typer.Exit(code=1)

    if raw:
        typer.echo(
            json.dumps(
                {"repo": repo_data, "open_prs": prs, "recent_runs": runs},
                indent=2,
            )
        )
        return

    render_pulse_dashboard(repo_data, prs, runs)


@app.command()
def pulse(
    repo: str = typer.Argument(
        help="Repository in owner/name format, e.g. [bold]astral-sh/uv[/]"
    ),
) -> None:
    """Show the full dashboard for a repository. Alias for summary."""
    summary(repo=repo, raw=False)


@app.command()
def pin(
    repo: str = typer.Argument(help="Repository to pin, e.g. [bold]astral-sh/uv[/]"),
) -> None:
    """Pin a repository to your DevPulse dashboard."""
    config = load_config()
    if config is None:
        console.print("[bold red]Not logged in.[/] Run [bold]devpulse login[/] first.")
        raise typer.Exit(code=1)

    if add_pinned_repo(repo):
        console.print(f"[bold green]✓ Pinned[/] [bold]{repo}[/]")
    else:
        console.print(f"[dim]{repo}[/] is already pinned.")


@app.command()
def unpin(
    repo: str = typer.Argument(help="Repository to unpin"),
) -> None:
    """Remove a repository from your pinned list."""
    if remove_pinned_repo(repo):
        console.print(f"[bold yellow]Unpinned[/] [bold]{repo}[/]")
    else:
        console.print(f"[dim]{repo}[/] was not in your pinned list.")


@app.command()
def repos() -> None:
    """List your pinned repositories."""
    config = load_config()
    if config is None:
        console.print("[bold red]Not logged in.[/] Run [bold]devpulse login[/] first.")
        raise typer.Exit(code=1)

    if not config.pinned_repos:
        console.print("[dim]No pinned repositories. Use [bold]devpulse pin owner/repo[/] to add one.[/]")
        return

    console.print(f"\n[bold]📌 Pinned Repositories[/] [{len(config.pinned_repos)}]\n")
    for repo in config.pinned_repos:
        console.print(f"  [bold]{repo}[/]")
    console.print()


@app.command()
def ui() -> None:
    """Launch the interactive TUI dashboard."""
    from devpulse.tui import run
    run()
