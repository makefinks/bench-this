#!/bin/sh
# Stage viewer.html with the dev fixture and open it in your browser.
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
stage=$(mktemp -d)
mkdir -p "$stage/results"
cp "$root/src/agent_bench/template/benchmarks/viewer.html" "$stage/"
cp "$root/dev-fixtures/viewer/viewer-data.js" "$stage/results/"
url="file://$stage/viewer.html"
echo "$url"
if [ "$(uname)" = "Darwin" ]; then open "$url"; else xdg-open "$url"; fi
