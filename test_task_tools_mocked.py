"""Mocked tests for Google Tasks service tools (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bridge.diagnostics import ordered_tool_names
from mcp_server import build_app

TASK_TOOL_NAMES = (
    "get_task_lists",
    "get_tasks",
    "search_tasks",
    "get_open_tasks",
    "create_task_list",
    "create_task",
    "complete_task",
    "update_task",
    "move_task",
)


@pytest.fixture
def mock_service(monkeypatch):
    service = MagicMock()
    monkeypatch.setattr("services.tasks.services._get_service", lambda: service)
    return service


@pytest.fixture
def sample_lists():
    return [
        {"title": "General", "id": "list-general", "updated": "2024-01-01T00:00:00.000Z"},
        {"title": "Work", "id": "list-work", "updated": "2024-01-02T00:00:00.000Z"},
    ]


def test_create_server_registers_task_tools():
    server, _auth_provider = build_app()
    tool_names = ordered_tool_names(server._tool_manager)

    for name in TASK_TOOL_NAMES:
        assert name in tool_names
    assert "get_bridge_diagnostics" in tool_names


def test_get_task_lists_mocked(mock_service, sample_lists, monkeypatch):
    monkeypatch.setattr(
        "services.tasks.services.fetch_task_lists", lambda _svc: sample_lists
    )
    from services.tasks import get_task_lists

    result = get_task_lists()
    assert result == [
        {
            "name": "General",
            "id": "list-general",
            "updated": "2024-01-01T00:00:00.000Z",
        },
        {"name": "Work", "id": "list-work", "updated": "2024-01-02T00:00:00.000Z"},
    ]


def test_get_tasks_and_open_tasks_mocked(mock_service, sample_lists, monkeypatch):
    raw_tasks = [
        {
            "title": "Open item",
            "id": "task-1",
            "status": "needsAction",
            "notes": "",
            "due": None,
            "updated": "2024-01-03T00:00:00.000Z",
        },
        {
            "title": "Done item",
            "id": "task-2",
            "status": "completed",
            "notes": "",
            "due": None,
            "updated": "2024-01-04T00:00:00.000Z",
        },
    ]
    monkeypatch.setattr(
        "services.tasks.services.fetch_task_lists", lambda _svc: sample_lists
    )
    monkeypatch.setattr(
        "services.tasks.services.fetch_tasks", lambda _svc, list_id: raw_tasks
    )
    from services.tasks import get_open_tasks, get_tasks

    all_tasks = get_tasks("General")
    assert len(all_tasks) == 2
    assert all_tasks[0]["open"] is True
    assert all_tasks[1]["open"] is False

    open_tasks = get_open_tasks("General")
    assert len(open_tasks) == 1
    assert open_tasks[0]["title"] == "Open item"


def test_search_tasks_mocked(mock_service, sample_lists, monkeypatch):
    monkeypatch.setattr(
        "services.tasks.services.fetch_task_lists", lambda _svc: sample_lists
    )
    def _fetch_tasks(_svc, list_id):
        if list_id != "list-general":
            return []
        return [
            {
                "title": "Buy milk",
                "id": "task-1",
                "status": "needsAction",
                "notes": "groceries",
                "due": None,
                "updated": "2024-01-03T00:00:00.000Z",
            }
        ]

    monkeypatch.setattr("services.tasks.services.fetch_tasks", _fetch_tasks)
    from services.tasks import search_tasks

    matches = search_tasks("milk")
    assert len(matches) == 1
    assert matches[0]["title"] == "Buy milk"


def test_write_tools_mocked(mock_service, sample_lists, monkeypatch):
    monkeypatch.setattr(
        "services.tasks.services.fetch_task_lists", lambda _svc: sample_lists
    )
    monkeypatch.setattr(
        "services.tasks.services.fetch_tasks",
        lambda _svc, list_id: [
            {
                "title": "Move me",
                "id": "task-move",
                "status": "needsAction",
                "notes": "note",
                "due": "2024-12-01T00:00:00.000Z",
                "updated": "2024-01-03T00:00:00.000Z",
            }
        ],
    )
    monkeypatch.setattr(
        "services.tasks.services.insert_task_list",
        lambda _svc, title: {
            "title": title,
            "id": "list-new",
            "updated": "2024-01-05T00:00:00.000Z",
        },
    )
    monkeypatch.setattr(
        "services.tasks.services.insert_task",
        lambda _svc, list_id, body: {
            "title": body["title"],
            "id": "task-new",
            "status": "needsAction",
            "notes": body.get("notes", ""),
            "due": body.get("due"),
            "updated": "2024-01-06T00:00:00.000Z",
        },
    )
    monkeypatch.setattr(
        "services.tasks.services.patch_task",
        lambda _svc, list_id, task_id, body: {
            "title": body.get("title", "Move me"),
            "id": task_id,
            "status": body.get("status", "needsAction"),
            "notes": body.get("notes", "note"),
            "due": body.get("due", "2024-12-01T00:00:00.000Z"),
            "updated": "2024-01-07T00:00:00.000Z",
        },
    )
    monkeypatch.setattr(
        "services.tasks.services.api_move_task",
        lambda _svc, src_id, task_id, dest_id: {
            "title": "Move me",
            "id": task_id,
            "status": "needsAction",
            "notes": "note",
            "due": "2024-12-01T00:00:00.000Z",
            "updated": "2024-01-08T00:00:00.000Z",
        },
    )

    from services.tasks import (
        complete_task,
        create_task,
        create_task_list,
        move_task,
        update_task,
    )

    created_list = create_task_list("Projects")
    assert created_list["name"] == "Projects"

    created_task = create_task("General", "New task", notes="details")
    assert created_task["title"] == "New task"
    assert created_task["list_name"] == "General"

    completed = complete_task("General", "task-move")
    assert completed["open"] is False

    updated = update_task("General", "task-move", title="Updated title")
    assert updated["title"] == "Updated title"

    moved = move_task("General", "task-move", "Work")
    assert moved["list_name"] == "Work"
