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


def test_skill_documents_shared_provider_key_setup() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    bedrock_references = list(
        (SKILL_ROOT / "references/configuration/harnesses").glob(
            "*/providers/amazon-bedrock.md"
        )
    )

    assert "auth set-key" in skill
    assert not (SKILL_ROOT / "scripts/provision_auth.py").exists()
    assert len(bedrock_references) == 4
    for reference in bedrock_references:
        text = reference.read_text(encoding="utf-8")
        assert "auth set-key --provider amazon-bedrock" in text
        assert "--api-key 'YOUR_API_KEY'" in text
        assert "provision_auth.py" not in text


def test_opencode_openrouter_documentation_covers_shared_key_setup() -> None:
    reference = (
        SKILL_ROOT
        / "references/configuration/harnesses/opencode/providers/openrouter.md"
    ).read_text(encoding="utf-8")

    assert "--provider openrouter" in reference
    assert "auth set-key --provider openrouter" in reference
    assert "--api-key 'YOUR_API_KEY'" in reference
    assert "OPENROUTER_API_KEY" in reference


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


