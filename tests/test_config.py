"""Tests for config loading and persistence."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from devpulse.config import (
    CONFIG_PATH,
    DevPulseConfig,
    add_pinned_repo,
    load_config,
    remove_pinned_repo,
    save_config,
    save_token,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Remove GITHUB_TOKEN from env and redirect config to a temp file."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("devpulse.config.CONFIG_PATH", tmp_path / ".devpulse.json")
    yield


def test_load_config_returns_none_when_nothing_set():
    assert load_config() is None


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env_token_123")
    config = load_config()
    assert config is not None
    assert config.github_token == "env_token_123"


def test_save_and_load_config(tmp_path, monkeypatch):
    config_path = tmp_path / ".devpulse.json"
    monkeypatch.setattr("devpulse.config.CONFIG_PATH", config_path)

    save_token("my_secret_token")
    loaded = load_config()

    assert loaded is not None
    assert loaded.github_token == "my_secret_token"


def test_config_file_permissions(tmp_path, monkeypatch):
    config_path = tmp_path / ".devpulse.json"
    monkeypatch.setattr("devpulse.config.CONFIG_PATH", config_path)

    save_token("token123")
    mode = oct(config_path.stat().st_mode)[-3:]
    assert mode == "600", f"Expected 600, got {mode}"


def test_pin_and_unpin_repo(tmp_path, monkeypatch):
    config_path = tmp_path / ".devpulse.json"
    monkeypatch.setattr("devpulse.config.CONFIG_PATH", config_path)

    save_token("token123")

    result = add_pinned_repo("astral-sh/uv")
    assert result is True

    config = load_config()
    assert "astral-sh/uv" in config.pinned_repos

    result = add_pinned_repo("astral-sh/uv")
    assert result is False  # already pinned

    remove_pinned_repo("astral-sh/uv")
    config = load_config()
    assert "astral-sh/uv" not in config.pinned_repos


def test_env_token_takes_priority_over_file(tmp_path, monkeypatch):
    config_path = tmp_path / ".devpulse.json"
    monkeypatch.setattr("devpulse.config.CONFIG_PATH", config_path)

    save_token("file_token")
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")

    config = load_config()
    assert config.github_token == "env_token"
