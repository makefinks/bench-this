"""Persistent task-list operations."""

import json
from pathlib import Path


class StoreError(Exception):
    """A task operation could not be completed."""


class Store:
    """Read and write one JSON task list."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {"revision": 0, "tasks": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def add(self, title: str) -> dict:
        title = title.strip()
        if not title:
            raise StoreError("task title must not be empty")
        state = self.load()
        task = {
            "id": max((task["id"] for task in state["tasks"]), default=0) + 1,
            "title": title,
            "completed": False,
        }
        state["tasks"].append(task)
        state["revision"] += 1
        self.save(state)
        return task
