import json
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest


VIEWER = Path(__file__).resolve().parents[1] / "src/agent_bench/template/benchmarks/viewer.html"


class FrontierLabels(HTMLParser):
    def __init__(self):
        super().__init__()
        self.labels = []
        self.in_label = False

    def handle_starttag(self, tag, attrs):
        self.in_label = tag == "text" and dict(attrs).get("class") == "frontier-point-label"
        if self.in_label:
            self.labels.append("")

    def handle_data(self, data):
        if self.in_label:
            self.labels[-1] += data

    def handle_endtag(self, tag):
        if tag == "text":
            self.in_label = False


@pytest.mark.parametrize("names", [
    ["synthetic-harness-provider-long-model-baseline", "synthetic-harness-provider-long-model-search"],
    ["long-configuration-with-<search>&-α", "short"],
])
def test_frontier_labels_preserve_complete_configuration_identity(names):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the viewer's JavaScript")
    script = re.search(r"<script>(.*?)</script>", VIEWER.read_text(), re.DOTALL).group(1)
    rows = [
        {"task": "synthetic", "configuration": name, "passed": True,
         "estimated_cost_usd": index + 1, "group_results": {"behavior": True}}
        for index, name in enumerate(names)
    ]
    # Stub browser APIs only; execute the real grouping, rendering, and escaping code.
    driver = """
const vm = require('node:vm');
const nodes = new Map();
const getNode = (id) => {
  if (!nodes.has(id)) nodes.set(id, {
    style: {}, innerHTML: '', addEventListener() {},
    querySelector() { return this; }, querySelectorAll() { return []; },
  });
  return nodes.get(id);
};
vm.runInNewContext(SCRIPT + '\\nrenderFrontier(groupByConfiguration(ROWS));', {
  ROWS, document: { getElementById: getNode, querySelectorAll: () => [] },
  matchMedia: () => ({ matches: true }),
});
process.stdout.write(getNode('frontier').innerHTML);
"""
    result = subprocess.run(
        [node, "-e", "const SCRIPT = " + json.dumps(script) + "; const ROWS = "
         + json.dumps(rows) + ";\n" + driver],
        capture_output=True, text=True, check=True, timeout=30,
    )
    parser = FrontierLabels()
    parser.feed(result.stdout)
    assert sorted(parser.labels) == sorted(names)
