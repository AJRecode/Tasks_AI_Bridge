"""Cognitive layer for Google Tasks — intended for AI and other callers."""

from googleapiclient.discovery import build

from services.tasks.google_auth import get_credentials
from services.tasks.google_tasks import (
    fetch_task_lists,
    fetch_tasks,
    insert_task,
    insert_task_list,
    move_task as api_move_task,
    patch_task,
)

_service = None


def _get_service():
    global _service
    if _service is None:
        creds = get_credentials()
        _service = build("tasks", "v1", credentials=creds, cache_discovery=False)
    return _service


def _normalize_task_list(task_list: dict) -> dict:
    return {
        "name": task_list.get("title", ""),
        "id": task_list.get("id", ""),
        "updated": task_list.get("updated", ""),
    }


def _normalize_task(task: dict, list_name: str) -> dict:
    status = task.get("status", "needsAction")
    return {
        "title": task.get("title", ""),
        "status": status,
        "open": status != "completed",
        "due": task.get("due"),
        "notes": task.get("notes", ""),
        "list_name": list_name,
        "id": task.get("id", ""),
        "updated": task.get("updated", ""),
    }


def _raw_task_lists() -> list[dict]:
    return fetch_task_lists(_get_service())


def _resolve_task_list(list_name: str) -> dict:
    query = list_name.strip().casefold()
    if not query:
        raise ValueError("list_name must not be empty.")

    task_lists = _raw_task_lists()
    if not task_lists:
        raise ValueError("No Google Task lists were found.")

    exact_matches = [
        task_list
        for task_list in task_lists
        if task_list.get("title", "").casefold() == query
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        names = [task_list.get("title", "<untitled>") for task_list in exact_matches]
        raise ValueError(f"Multiple task lists match {list_name!r}: {', '.join(names)}")

    partial_matches = [
        task_list
        for task_list in task_lists
        if query in task_list.get("title", "").casefold()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        names = [task_list.get("title", "<untitled>") for task_list in partial_matches]
        raise ValueError(
            f"Multiple task lists match {list_name!r}. Be more specific. "
            f"Matches: {', '.join(names)}"
        )

    available = [task_list.get("title", "<untitled>") for task_list in task_lists]
    raise ValueError(
        f"No task list matches {list_name!r}. Available lists: {', '.join(available)}"
    )


def get_task_lists() -> list[dict]:
    """Return all task lists in a caller-friendly shape."""
    return [_normalize_task_list(task_list) for task_list in _raw_task_lists()]


def create_task_list(list_name: str) -> dict:
    """Create a new task list."""
    title = list_name.strip()
    if not title:
        raise ValueError("list_name must not be empty.")

    for task_list in _raw_task_lists():
        if task_list.get("title", "").casefold() == title.casefold():
            raise ValueError(f"A task list named {title!r} already exists.")

    raw_list = insert_task_list(_get_service(), title)
    return _normalize_task_list(raw_list)


def get_tasks(list_name: str) -> list[dict]:
    """Return all tasks from one list, identified by name."""
    task_list = _resolve_task_list(list_name)
    list_title = task_list.get("title", "")
    raw_tasks = fetch_tasks(_get_service(), task_list["id"])
    return [_normalize_task(task, list_title) for task in raw_tasks]


def search_tasks(text: str) -> list[dict]:
    """Search task titles and notes across all lists."""
    query = text.strip().casefold()
    if not query:
        raise ValueError("Search text must not be empty.")

    matches: list[dict] = []
    for task_list in _raw_task_lists():
        list_title = task_list.get("title", "")
        for task in fetch_tasks(_get_service(), task_list["id"]):
            haystack = " ".join(
                [
                    task.get("title", ""),
                    task.get("notes", ""),
                ]
            ).casefold()
            if query in haystack:
                matches.append(_normalize_task(task, list_title))

    return matches


def get_open_tasks(list_name: str) -> list[dict]:
    """Return incomplete tasks from one list, identified by name."""
    return [task for task in get_tasks(list_name) if task["open"]]


def _find_task_in_list(list_name: str, task_id: str) -> tuple[dict, dict]:
    task_list = _resolve_task_list(list_name)
    for task in fetch_tasks(_get_service(), task_list["id"]):
        if task.get("id") == task_id:
            return task, task_list
    raise ValueError(
        f"No task with id {task_id!r} in list {list_name!r}. "
        "Use get_open_tasks or search_tasks to find a valid id."
    )


def create_task(
    list_name: str,
    title: str,
    notes: str = "",
    due: str | None = None,
) -> dict:
    """Create a new task in one list, identified by name."""
    task_title = title.strip()
    if not task_title:
        raise ValueError("title must not be empty.")

    task_list = _resolve_task_list(list_name)
    list_title = task_list.get("title", "")

    body: dict = {"title": task_title}
    if notes.strip():
        body["notes"] = notes.strip()
    if due is not None and due.strip():
        body["due"] = due.strip()

    raw_task = insert_task(_get_service(), task_list["id"], body)
    return _normalize_task(raw_task, list_title)


def complete_task(list_name: str, task_id: str) -> dict:
    """Mark one task completed in a list, identified by list name and task id."""
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("task_id must not be empty.")

    _, task_list = _find_task_in_list(list_name, task_id)
    list_title = task_list.get("title", "")

    raw_task = patch_task(
        _get_service(),
        task_list["id"],
        task_id,
        {"status": "completed"},
    )
    return _normalize_task(raw_task, list_title)


def update_task(
    list_name: str,
    task_id: str,
    *,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
) -> dict:
    """Update one task in a list. Omitted fields are left unchanged.

    Pass notes="" to clear notes. Pass due="" to clear the due date.
    """
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("task_id must not be empty.")

    body: dict = {}
    if title is not None:
        task_title = title.strip()
        if not task_title:
            raise ValueError("title must not be empty when provided.")
        body["title"] = task_title
    if notes is not None:
        body["notes"] = notes.strip()
    if due is not None:
        due_value = due.strip()
        body["due"] = due_value or None

    if not body:
        raise ValueError("Provide at least one of title, notes, or due to update.")

    _, task_list = _find_task_in_list(list_name, task_id)
    list_title = task_list.get("title", "")

    raw_task = patch_task(_get_service(), task_list["id"], task_id, body)
    return _normalize_task(raw_task, list_title)


def move_task(
    from_list_name: str,
    task_id: str,
    to_list_name: str,
) -> dict:
    """Move a task from one list to another, identified by list names."""
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("task_id must not be empty.")

    source_list = _resolve_task_list(from_list_name)
    destination_list = _resolve_task_list(to_list_name)

    if source_list["id"] == destination_list["id"]:
        raise ValueError(
            f"Source and destination are the same list ({source_list.get('title', from_list_name)!r})."
        )

    _, _ = _find_task_in_list(from_list_name, task_id)
    destination_title = destination_list.get("title", "")

    try:
        moved = api_move_task(
            _get_service(),
            source_list["id"],
            task_id,
            destination_list["id"],
        )
    except Exception as exc:
        message = str(exc)
        if "recurrent" in message.casefold() or "recurring" in message.casefold():
            raise ValueError(
                "Recurring tasks cannot be moved between lists with the Google Tasks API."
            ) from exc
        raise

    return _normalize_task(moved, destination_title)
