#!/bin/sh
set -eu

workspace=${1:?workspace path is required}
cd "$workspace"

# This runs as a non-root UID with a temporary HOME. Replace it with the
# project's deterministic dependency setup using container-installed tools.
# Declare required host variable names in benchmark.yaml's setup_environment.
# Keep credentials (including authenticated URLs) out of output and workspace files.
if [ -f requirements.txt ]; then
  python3 -m venv .venv
  .venv/bin/pip install --disable-pip-version-check -r requirements.txt
fi
