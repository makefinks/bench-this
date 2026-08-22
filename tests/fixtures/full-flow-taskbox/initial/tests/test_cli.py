"""Public CLI tests for Taskbox."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TaskboxCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary.name) / "tasks.json"

    def tearDown(self):
        self.temporary.cleanup()

    def run_taskbox(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "taskbox",
                "--store",
                str(self.store),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_add_and_list_tasks(self):
        added = self.run_taskbox("add", "  Write report  ")
        self.assertEqual(added.returncode, 0, added.stderr)
        listed = self.run_taskbox("list", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(
            json.loads(listed.stdout),
            [{"id": 1, "title": "Write report", "completed": False}],
        )

    def test_empty_title_is_rejected(self):
        result = self.run_taskbox("add", "   ")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not be empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
