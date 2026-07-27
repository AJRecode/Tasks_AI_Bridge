"""Smoke test for write operations in task_services.py.

Creates a disposable task, verifies it is open, completes it, verifies closed.
Does not delete the task (Google Tasks keeps completed items).

Usage:
    source .venv/bin/activate
    python test_write_task_services.py
    python test_write_task_services.py "General"
    python test_write_task_services.py "General" "AI Integration Lab"

Optional second argument runs a move-to-list check before completing the task.
If you previously used read-only access, delete token.json only if re-consent
does not start automatically.
"""

import sys
import uuid

from task_services import complete_task, create_task, get_open_tasks, move_task, update_task

TEST_PREFIX = "[MCP-TEST]"


def main() -> int:
    list_name = sys.argv[1] if len(sys.argv) > 1 else "General"
    to_list_name = sys.argv[2] if len(sys.argv) > 2 else None
    title = f"{TEST_PREFIX} {uuid.uuid4().hex[:8]}"

    print(f"Using list: {list_name!r}")
    print(f"Creating task: {title!r}")

    created = create_task(list_name, title, notes="Write smoke test")
    print("Created:", created)

    if not created["open"]:
        print("FAIL: new task should be open")
        return 1

    open_matches = [task for task in get_open_tasks(list_name) if task["id"] == created["id"]]
    if len(open_matches) != 1:
        print("FAIL: created task not found in get_open_tasks()")
        return 1

    active_list = list_name
    if to_list_name:
        print(f"Moving task to list: {to_list_name!r}")
        moved = move_task(list_name, created["id"], to_list_name)
        print("Moved:", moved)
        if moved["list_name"] != to_list_name and to_list_name.casefold() not in moved["list_name"].casefold():
            print("FAIL: moved task list_name mismatch")
            return 1
        in_dest = [task for task in get_open_tasks(to_list_name) if task["id"] == created["id"]]
        if len(in_dest) != 1:
            print("FAIL: moved task not found in destination list")
            return 1
        in_source = [task for task in get_open_tasks(list_name) if task["id"] == created["id"]]
        if in_source:
            print("FAIL: moved task still appears in source list open tasks")
            return 1
        active_list = to_list_name

    updated = update_task(
        active_list,
        created["id"],
        title=f"{title} (updated)",
        notes="Updated notes",
        due="2026-12-31T00:00:00.000Z",
    )
    print("Updated:", updated)
    if updated["title"] != f"{title} (updated)":
        print("FAIL: updated title mismatch")
        return 1
    if updated["notes"] != "Updated notes":
        print("FAIL: updated notes mismatch")
        return 1
    if not updated["due"]:
        print("FAIL: updated due should be set")
        return 1

    cleared_notes = update_task(active_list, created["id"], notes="")
    print("Cleared notes:", cleared_notes)
    if cleared_notes["notes"]:
        print("FAIL: notes should be cleared")
        return 1

    completed = complete_task(active_list, created["id"])
    print("Completed:", completed)

    if completed["open"]:
        print("FAIL: task should be completed")
        return 1

    still_open = [task for task in get_open_tasks(active_list) if task["id"] == created["id"]]
    if still_open:
        print("FAIL: completed task still appears in get_open_tasks()")
        return 1

    print("All write checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
