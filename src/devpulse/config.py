"""DevPulse configuration — token loading and persistence."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from pydantic import BaseModel

CONFIG_PATH = Path.home() / ".devpulse.json"


class DevPulseConfig(BaseModel):
    github_token: str
    pinned_repos: list[str] = [
        "astral-sh/uv",
        "astral-sh/ruff",
    ]


def load_config() -> DevPulseConfig | None:
    """Load config from environment variable or config file.

    Environment variable takes priority over the config file.
    Returns None if no token is found anywhere.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return DevPulseConfig(github_token=token)

    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text())
        return DevPulseConfig(**raw)

    return None


def save_config(config: DevPulseConfig) -> None:
    """Persist config to ~/.devpulse.json with restricted permissions."""
    CONFIG_PATH.write_text(config.model_dump_json(indent=2))
    # Restrict to owner read/write only — tokens are sensitive
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def save_token(token: str) -> None:
    """Save a token, preserving any existing pinned repos."""
    existing = load_config()
    pinned = existing.pinned_repos if existing else DevPulseConfig.__fields__["pinned_repos"].default
    save_config(DevPulseConfig(github_token=token, pinned_repos=pinned))


def add_pinned_repo(repo: str) -> bool:
    """Add a repo to the pinned list. Returns True if added, False if already pinned."""
    config = load_config()
    if config is None:
        return False
    if repo in config.pinned_repos:
        return False
    config.pinned_repos.append(repo)
    save_config(config)
    return True


def remove_pinned_repo(repo: str) -> bool:
    """Remove a repo from the pinned list. Returns True if removed."""
    config = load_config()
    if config is None or repo not in config.pinned_repos:
        return False
    config.pinned_repos.remove(repo)
    save_config(config)
    return True
