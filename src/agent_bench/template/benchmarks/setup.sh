#!/bin/sh
set -eu

workspace=${1:?workspace path is required}
cd "$workspace"

# This runs as a non-root UID with a temporary HOME. Replace it with the
# project's deterministic dependency setup without relying on host tools,
# credentials, or services that the evaluator cannot safely use.
if [ -f requirements.txt ]; then
  python3 -m venv .venv
  .venv/bin/pip install --disable-pip-version-check -r requirements.txt
fi
