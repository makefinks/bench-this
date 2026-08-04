#!/usr/bin/env python3
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "_vendor"))

from agent_bench.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["--benchmark-dir", str(HERE), *sys.argv[1:]]))

