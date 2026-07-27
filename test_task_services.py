"""Smoke test for task_services.py.

Description:
    Exercises the four public task_services functions against your live Google
    Tasks account. This is a manual integration test, not a mocked unit test.
    It verifies auth, API access, list-name resolution, normalization, search,
    and basic error handling.

Usage:
    From the project folder with the virtualenv active:

        source .venv/bin/activate
        python test_task_services.py

    Optional: test a specific list by name:

        python test_task_services.py "Health"

    Optional: search for a specific word:

        python test_task_services.py "Health" "call"

Requirements:
    - credentials.json and token.json in this folder
    - Google Tasks API enabled for the OAuth project
    - Network access to Google APIs

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
"""

import json
import sys

from task_services import get_open_tasks, get_task_lists, get_tasks, search_tasks


def _print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def _expect_value_error(label: str, func) -> bool:
    try:
        func()
    except ValueError as exc:
        print(f"OK: {label} -> {exc}")
        return True

    print(f"FAIL: {label} should have raised ValueError")
    return False


def main() -> int:
    list_name_arg = sys.argv[1] if len(sys.argv) > 1 else None
    search_text_arg = sys.argv[2] if len(sys.argv) > 2 else None

    passed = True

    _print_section("get_task_lists()")
    lists = get_task_lists()
    print(f"Found {len(lists)} list(s)")
    for task_list in lists:
        print(f"  - {task_list['name']}")

    if not lists:
        print("No task lists found; stopping early.")
        return 0

    list_name = list_name_arg or lists[0]["name"]
    print(f"\nUsing list: {list_name!r}")

    _print_section(f"get_tasks({list_name!r})")
    tasks = get_tasks(list_name)
    print(f"Found {len(tasks)} task(s)")
    for task in tasks[:5]:
        mark = "x" if not task["open"] else " "
        print(f"  [{mark}] {task['title']}")
    if len(tasks) > 5:
        print(f"  ... and {len(tasks) - 5} more")

    _print_section(f"get_open_tasks({list_name!r})")
    open_tasks = get_open_tasks(list_name)
    print(f"Found {len(open_tasks)} open task(s)")
    for task in open_tasks[:5]:
        print(f"  [ ] {task['title']}")

    search_text = search_text_arg
    if search_text is None and tasks:
        search_text = tasks[0]["title"][:10].strip()

    _print_section("search_tasks(...)")
    if search_text:
        print(f"Searching for: {search_text!r}")
        matches = search_tasks(search_text)
        print(f"Found {len(matches)} match(es)")
        for match in matches[:5]:
            print(f"  - [{match['list_name']}] {match['title']}")
        if len(matches) > 5:
            print(f"  ... and {len(matches) - 5} more")
    else:
        print("Skipped: no search text provided and chosen list has no tasks.")

    _print_section("sample normalized output")
    sample = {
        "list": lists[0],
        "task": tasks[0] if tasks else None,
        "open_task": open_tasks[0] if open_tasks else None,
    }
    print(json.dumps(sample, indent=2))

    _print_section("error handling")
    passed &= _expect_value_error(
        "invalid list name",
        lambda: get_tasks("this-list-does-not-exist-xyz"),
    )
    passed &= _expect_value_error(
        "empty search text",
        lambda: search_tasks("   "),
    )

    _print_section("result")
    if passed:
        print("All checks passed.")
        return 0

    print("One or more checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
