#!/usr/bin/env python3
"""Tasks Bridge menu bar controller for macOS.

Wraps start_tasks_bridge.sh so you can start, stop, and check status from the
menu bar without Automator or manual Terminal commands.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path

import rumps

MCP_URL = "http://127.0.0.1:8000/mcp"
INSPECTOR_URL = "http://127.0.0.1:6274"


def _project_dir() -> Path:
    env = os.environ.get("TASKS_BRIDGE_PROJECT_DIR", "").strip()
    if env:
        return Path(env)

    marker = Path(__file__).resolve().parent / ".project_path"
    if marker.is_file():
        return Path(marker.read_text().strip())

    # macos/menubar/tasks_bridge_menubar.py -> repo root
    return Path(__file__).resolve().parents[2]


PROJECT_DIR = _project_dir()
BRIDGE_SCRIPT = PROJECT_DIR / "start_tasks_bridge.sh"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    if not BRIDGE_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing bridge script: {BRIDGE_SCRIPT}")
    return subprocess.run(
        [str(BRIDGE_SCRIPT), *args],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_status(output: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"^\s+(UP|DOWN|STALE|N/A)\s+", line)
        if not match:
            continue
        state = match.group(1)
        if "MCP server" in line or "http://127.0.0.1:8000/mcp" in line:
            states["mcp"] = state
        elif "tunnel-client" in line:
            states["tunnel"] = state
        elif "Inspector" in line:
            states["inspector"] = state
    return states


def _status_summary() -> tuple[str, dict[str, str]]:
    result = _run_script("--status")
    output = (result.stdout or "") + (result.stderr or "")
    states = _parse_status(output)
    if not states:
        return output.strip() or "Could not read bridge status.", states

    parts = []
    for key, label in (
        ("mcp", "MCP"),
        ("tunnel", "Tunnel"),
        ("inspector", "Inspector"),
    ):
        if key in states:
            parts.append(f"{label}: {states[key]}")
    summary = ", ".join(parts) if parts else "Status unknown"
    return summary, states


def _menubar_title(states: dict[str, str]) -> str:
    """Use short visible text — single Unicode glyphs are easy to miss in the menu bar."""
    if states.get("mcp") == "UP" and states.get("tunnel") in {"UP", "N/A"}:
        return "TB ✓"
    if states.get("mcp") in {"UP", "STALE"}:
        return "TB ◐"
    return "TB"


class TasksBridgeMenubarApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Tasks Bridge", title="TB", quit_button=None)
        self._busy = False

        self.start_item = rumps.MenuItem("Start Bridge", callback=self.start_bridge)
        self.stop_item = rumps.MenuItem("Stop Bridge", callback=self.stop_bridge)
        self.restart_item = rumps.MenuItem("Restart Bridge", callback=self.restart_bridge)
        self.status_item = rumps.MenuItem("Show Status", callback=self.show_status)
        self.inspector_item = rumps.MenuItem("Open Inspector", callback=self.open_inspector)
        self.mcp_item = rumps.MenuItem("Copy MCP URL", callback=self.copy_mcp_url)
        self.quit_item = rumps.MenuItem("Quit Menu Bar App", callback=self.quit_app)

        self.menu = [
            self.start_item,
            self.stop_item,
            self.restart_item,
            None,
            self.status_item,
            self.inspector_item,
            self.mcp_item,
            None,
            self.quit_item,
        ]

        if not BRIDGE_SCRIPT.is_file():
            rumps.notification(
                "Tasks Bridge",
                "Project not found",
                f"Expected start_tasks_bridge.sh at {BRIDGE_SCRIPT}",
            )

        self.refresh_status()

    @rumps.timer(30)
    def refresh_status(self, _=None) -> None:
        if self._busy:
            return
        try:
            summary, states = _status_summary()
        except Exception as exc:
            self.title = "TB !"
            self.status_item.title = f"Status: error ({exc})"
            return

        self.title = _menubar_title(states)
        self.status_item.title = f"Status: {summary}"

    def _run_async(self, label: str, command: list[str], *, on_success: str | None = None) -> None:
        if self._busy:
            rumps.notification("Tasks Bridge", "Busy", "Already running a bridge action.")
            return

        self._busy = True
        self.title = "TB …"

        def worker() -> None:
            try:
                result = subprocess.run(
                    command,
                    cwd=PROJECT_DIR,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                output = (result.stdout or "") + (result.stderr or "")
                if result.returncode != 0 and "Some services need attention" not in output:
                    rumps.notification(
                        "Tasks Bridge",
                        f"{label} failed",
                        output.strip()[-180:] or f"Exit code {result.returncode}",
                    )
                elif on_success:
                    rumps.notification("Tasks Bridge", label, on_success)
            except Exception as exc:
                rumps.notification("Tasks Bridge", f"{label} failed", str(exc))
            finally:
                self._busy = False
                self.refresh_status()

        threading.Thread(target=worker, daemon=True).start()

    @rumps.clicked("Start Bridge")
    def start_bridge(self, _=None) -> None:
        self._run_async(
            "Start",
            [str(BRIDGE_SCRIPT)],
            on_success="Starting MCP, tunnel, and Inspector windows.",
        )

    @rumps.clicked("Stop Bridge")
    def stop_bridge(self, _=None) -> None:
        self._run_async("Stop", [str(BRIDGE_SCRIPT), "--stop"], on_success="Bridge stopped.")

    @rumps.clicked("Restart Bridge")
    def restart_bridge(self, _=None) -> None:
        def worker() -> None:
            self._busy = True
            self.title = "TB …"
            try:
                stop = _run_script("--stop")
                start = _run_script()
                output = (stop.stdout or "") + (start.stdout or "") + (start.stderr or "")
                if start.returncode != 0 and "Some services need attention" not in output:
                    rumps.notification(
                        "Tasks Bridge",
                        "Restart failed",
                        output.strip()[-180:] or f"Exit code {start.returncode}",
                    )
                else:
                    rumps.notification(
                        "Tasks Bridge",
                        "Restart",
                        "Bridge restarted (MCP, tunnel, Inspector).",
                    )
            except Exception as exc:
                rumps.notification("Tasks Bridge", "Restart failed", str(exc))
            finally:
                self._busy = False
                self.refresh_status()

        if self._busy:
            rumps.notification("Tasks Bridge", "Busy", "Already running a bridge action.")
            return
        threading.Thread(target=worker, daemon=True).start()

    @rumps.clicked("Show Status")
    def show_status(self, _=None) -> None:
        try:
            summary, _states = _status_summary()
        except Exception as exc:
            rumps.notification("Tasks Bridge", "Status error", str(exc))
            return
        rumps.notification("Tasks Bridge", "Current status", summary)

    @rumps.clicked("Open Inspector")
    def open_inspector(self, _=None) -> None:
        subprocess.run(["open", INSPECTOR_URL], check=False)

    @rumps.clicked("Copy MCP URL")
    def copy_mcp_url(self, _=None) -> None:
        rumps.clipboard.set(MCP_URL)
        rumps.notification("Tasks Bridge", "Copied", MCP_URL)

    @rumps.clicked("Quit Menu Bar App")
    def quit_app(self, _=None) -> None:
        rumps.quit_application()


def main() -> None:
    TasksBridgeMenubarApp().run()


if __name__ == "__main__":
    main()
