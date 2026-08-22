"""Taskbox command-line interface."""

import argparse
import json
from pathlib import Path
import sys

from .store import Store, StoreError


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="taskbox")
    value.add_argument("--store", type=Path, required=True)
    commands = value.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add")
    add.add_argument("title")

    listing = commands.add_parser("list")
    listing.add_argument("--json", action="store_true")
    return value


def main(argv=None) -> int:
    arguments = parser().parse_args(argv)
    store = Store(arguments.store)
    try:
        if arguments.command == "add":
            print(json.dumps(store.add(arguments.title)))
            return 0
        tasks = store.load()["tasks"]
        if arguments.json:
            print(json.dumps(tasks))
        else:
            for task in tasks:
                marker = "x" if task["completed"] else " "
                print(f"{task['id']:>3} [{marker}] {task['title']}")
        return 0
    except (OSError, ValueError, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
