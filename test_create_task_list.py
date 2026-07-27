"""Smoke test for create_task_list in task_services.py.

Usage:
    source .venv/bin/activate
    python test_create_task_list.py
"""

import sys
import uuid

from task_services import create_task_list, get_task_lists

TEST_PREFIX = "[MCP-TEST-LIST]"


def _expect_value_error(label: str, func) -> bool:
    try:
        func()
    except ValueError as exc:
        print(f"OK: {label} -> {exc}")
        return True

    print(f"FAIL: {label} should have raised ValueError")
    return False


def main() -> int:
    passed = True
    list_name = f"{TEST_PREFIX} {uuid.uuid4().hex[:8]}"

    print(f"Creating list: {list_name!r}")
    created = create_task_list(list_name)
    print("Created:", created)

    if set(created.keys()) != {"name", "id", "updated"}:
        print("FAIL: normalized output should contain name, id, updated")
        return 1

    if created["name"] != list_name:
        print("FAIL: created list name mismatch")
        return 1

    if not created["id"]:
        print("FAIL: created list id is empty")
        return 1

    names = [task_list["name"] for task_list in get_task_lists()]
    if list_name not in names:
        print("FAIL: created list not found in get_task_lists()")
        return 1

    print("\n=== error handling ===")
    passed &= _expect_value_error(
        "blank list name",
        lambda: create_task_list("   "),
    )
    passed &= _expect_value_error(
        "duplicate list name",
        lambda: create_task_list(list_name),
    )
    passed &= _expect_value_error(
        "case-insensitive duplicate",
        lambda: create_task_list(list_name.upper()),
    )

    print("\n=== result ===")
    if passed:
        print("All checks passed.")
        return 0

    print("One or more checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
