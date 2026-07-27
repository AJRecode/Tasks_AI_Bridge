"""Shared Google Tasks API helpers."""


def fetch_task_lists(service) -> list[dict]:
    """Return all Google Tasks task lists."""
    task_lists: list[dict] = []
    page_token = None

    while True:
        response = (
            service.tasklists()
            .list(maxResults=100, pageToken=page_token)
            .execute()
        )
        task_lists.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return task_lists


def insert_task_list(service, title: str) -> dict:
    """Create a new task list."""
    return service.tasklists().insert(body={"title": title}).execute()


def fetch_tasks(
    service,
    task_list_id: str,
    *,
    show_completed: bool = True,
    show_hidden: bool = True,
) -> list[dict]:
    """Return all tasks from one task list, following nextPageToken until exhausted.

    Google paginates tasks.list (max 100 per page). Completed tasks that were
    checked off in first-party clients (web/mobile) are often marked hidden; they
    require showHidden=True even when showCompleted=True. See Google Tasks
    tasks.list docs.
    """
    tasks: list[dict] = []
    page_token = None

    while True:
        request = service.tasks().list(
            tasklist=task_list_id,
            maxResults=100,
            showCompleted=show_completed,
            showHidden=show_hidden,
            showDeleted=False,
        )
        if page_token:
            request = request.pageToken(page_token)

        response = request.execute()
        tasks.extend(response.get("items") or [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return tasks


def insert_task(service, task_list_id: str, body: dict) -> dict:
    """Create a task in one list."""
    return (
        service.tasks()
        .insert(tasklist=task_list_id, body=body)
        .execute()
    )


def patch_task(service, task_list_id: str, task_id: str, body: dict) -> dict:
    """Update fields on an existing task."""
    return (
        service.tasks()
        .patch(tasklist=task_list_id, task=task_id, body=body)
        .execute()
    )


def move_task(
    service,
    source_task_list_id: str,
    task_id: str,
    destination_task_list_id: str,
) -> dict:
    """Move a task to another task list."""
    return (
        service.tasks()
        .move(
            tasklist=source_task_list_id,
            task=task_id,
            destinationTasklist=destination_task_list_id,
        )
        .execute()
    )
