import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "bench-this"


def test_skill_metadata_matches_its_directory() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == SKILL_ROOT.name
    assert isinstance(metadata.get("description"), str)
    assert metadata["description"].strip()
    assert body.strip()


def test_local_markdown_links_resolve() -> None:
    missing = []
    paths = [ROOT / "README.md", ROOT / "AGENTS.md", *SKILL_ROOT.rglob("*.md")]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"(?<!!)\[[^]]*\]\(([^)]+)\)", text):
            target = target.strip().split()[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")

    assert missing == []


