"""Tests for Rich rendering functions."""
from __future__ import annotations

import pytest
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devpulse.renderer import (
    _ci_status_text,
    _format_pr_labels,
    _relative_time,
    render_pr_table,
    render_repo_panel,
    render_workflow_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_relative_time_minutes():
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert _relative_time(ts) == "5m ago"


def test_relative_time_hours():
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert _relative_time(ts) == "3h ago"


def test_relative_time_days():
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert _relative_time(ts) == "5d ago"


def test_relative_time_yesterday():
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert _relative_time(ts) == "yesterday"


def test_format_pr_labels_known():
    labels = [{"name": "bug"}, {"name": "WIP"}]
    text = _format_pr_labels(labels)
    assert isinstance(text, Text)
    assert "bug" in text.plain
    assert "WIP" in text.plain


def test_format_pr_labels_empty():
    text = _format_pr_labels([])
    assert text.plain == ""


def test_ci_status_success():
    run = {"conclusion": "success", "status": "completed"}
    text = _ci_status_text(run)
    assert "pass" in text.plain


def test_ci_status_failure():
    run = {"conclusion": "failure", "status": "completed"}
    text = _ci_status_text(run)
    assert "fail" in text.plain


def test_ci_status_in_progress():
    run = {"conclusion": None, "status": "in_progress"}
    text = _ci_status_text(run)
    assert "running" in text.plain


# ---------------------------------------------------------------------------
# Renderables return the right types
# ---------------------------------------------------------------------------

SAMPLE_REPO = {
    "full_name": "astral-sh/uv",
    "description": "An extremely fast Python package manager.",
    "stargazers_count": 10000,
    "forks_count": 500,
    "open_issues_count": 42,
    "language": "Rust",
}

SAMPLE_PR = {
    "number": 1042,
    "title": "Fix: resolve version conflicts in lockfile",
    "user": {"login": "charliermarsh"},
    "labels": [{"name": "bug"}, {"name": "WIP"}],
    "created_at": "2026-05-01T10:00:00Z",
}

SAMPLE_RUN = {
    "name": "CI",
    "head_branch": "main",
    "conclusion": "success",
    "status": "completed",
    "created_at": "2026-05-10T09:00:00Z",
}


def test_render_repo_panel_returns_panel():
    panel = render_repo_panel(SAMPLE_REPO)
    assert isinstance(panel, Panel)


def test_render_pr_table_returns_table():
    table = render_pr_table([SAMPLE_PR])
    assert isinstance(table, Table)
    assert table.row_count == 1


def test_render_pr_table_empty():
    table = render_pr_table([])
    assert isinstance(table, Table)
    assert table.row_count == 0


def test_render_workflow_table_returns_table():
    table = render_workflow_table([SAMPLE_RUN])
    assert isinstance(table, Table)
    assert table.row_count == 1
