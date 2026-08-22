#!/usr/bin/env python3
"""Create one pinned benchmark treatment without hand-written YAML."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Optional


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SUPPORTED_HARNESSES = {"copilot", "omp", "opencode", "pi"}
SUPPORTED_OPENCODE_PROVIDERS = {
    "amazon-bedrock",
    "github-copilot",
    "openai",
    "opencode",
    "opencode-go",
}
SUPPORTED_OMP_PROVIDERS = {"amazon-bedrock", "github-copilot", "openai-codex"}
SUPPORTED_PI_PROVIDERS = {"amazon-bedrock", "openai-codex"}
GITHUB_COPILOT_BUSINESS_BASE_URL = "https://api.business.githubcopilot.com"
AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+$")


def _id(value: str, label: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must use lowercase letters, digits, and hyphens")
    return value


def _default_id(harness: str, provider: Optional[str], model: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    provider_part = f"{provider}-" if provider else ""
    return _id(f"{harness}-{provider_part}{slug}"[:63].rstrip("-"), "configuration id")


def _skill_name(skill_dir: Path) -> str:
    manifest = skill_dir / "SKILL.md"
    if not manifest.is_file():
        raise ValueError(f"skill is missing SKILL.md: {skill_dir}")
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"skill has no YAML frontmatter: {manifest}")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
            _id(name, "skill name")
            if skill_dir.name != name:
                raise ValueError(f"skill directory {skill_dir.name!r} must match name {name!r}")
            return name
    else:
        raise ValueError(f"skill frontmatter is missing name: {manifest}")


def _reject_symlinks(root: Path, label: str) -> None:
    if root.is_symlink() or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError(f"{label} must not contain symlinks: {root}")


def create_configuration(
    repository: Path,
    *,
    model: str,
    auth_profile: str,
    harness: str = "opencode",
    provider: Optional[str] = None,
    github_copilot_business: bool = False,
    bedrock_region: Optional[str] = None,
    config_id: Optional[str] = None,
    skills: Iterable[Path] = (),
) -> Path:
    """Create an atomic configuration directory and return its final path."""

    repository = repository.expanduser().resolve()
    benchmark_dir = repository / "benchmarks"
    if not (benchmark_dir / "benchmark.yaml").is_file():
        raise ValueError(f"benchmark scaffold not found: {benchmark_dir}")
    if harness not in SUPPORTED_HARNESSES:
        raise ValueError(f"harness must be one of: {', '.join(sorted(SUPPORTED_HARNESSES))}")
    if harness == "opencode" and provider not in SUPPORTED_OPENCODE_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_OPENCODE_PROVIDERS))
        raise ValueError(f"OpenCode configurations require --provider: {supported}")
    if harness == "omp" and provider not in SUPPORTED_OMP_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_OMP_PROVIDERS))
        raise ValueError(f"OMP configurations require --provider: {supported}")
    if harness == "pi" and provider not in SUPPORTED_PI_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PI_PROVIDERS))
        raise ValueError(f"Pi configurations require --provider: {supported}")
    if harness == "copilot" and provider is not None:
        raise ValueError(
            "--provider applies only to OpenCode, Oh My Pi, and Pi configurations"
        )
    if github_copilot_business and (harness != "opencode" or provider != "github-copilot"):
        raise ValueError(
            "--github-copilot-business requires --harness opencode "
            "--provider github-copilot"
        )
    if provider == "amazon-bedrock":
        if not bedrock_region or not AWS_REGION_PATTERN.fullmatch(bedrock_region):
            raise ValueError(
                "Amazon Bedrock configurations require a valid --bedrock-region"
            )
    elif bedrock_region is not None:
        raise ValueError("--bedrock-region applies only to Amazon Bedrock")
    if not model.strip() or model == "auto":
        raise ValueError("model must be explicitly pinned")
    _id(auth_profile, "auth profile")
    skill_dirs = [path.expanduser().resolve() for path in skills]
    config_id = (
        _id(config_id, "configuration id")
        if config_id
        else _default_id(harness, provider, model)
    )
    config_root = benchmark_dir / "configurations"
    config_root.mkdir(parents=True, exist_ok=True)
    destination = config_root / config_id
    if destination.exists():
        raise ValueError(f"configuration already exists: {destination}")

    skill_names = []
    for skill_dir in skill_dirs:
        if not skill_dir.is_dir():
            raise ValueError(f"skill directory does not exist: {skill_dir}")
        _reject_symlinks(skill_dir, "skill")
        skill_names.append(_skill_name(skill_dir))
    if len(set(skill_names)) != len(skill_names):
        raise ValueError("skill names must be unique")

    temporary = Path(tempfile.mkdtemp(prefix=".configuration-", dir=config_root))
    try:
        (temporary / "harness").mkdir()
        (temporary / "workspace").mkdir()
        manifest_lines = [f"id: {config_id}", f"harness: {harness}"]
        if harness in {"opencode", "omp", "pi"}:
            manifest_lines.extend(
                [
                    f"provider: {provider}",
                    f"model: {model}",
                ]
            )
            if harness == "opencode":
                manifest_lines.append("agent: build")
            if provider == "amazon-bedrock":
                manifest_lines.append(f"region: {bedrock_region}")
        else:
            manifest_lines.append(f"model: {model}")
        manifest_lines.extend(
            [
                "harness_config: harness",
                "workspace_config: workspace",
                f"auth_profile: {auth_profile}",
                "arguments: []",
            ]
        )
        (temporary / "configuration.yaml").write_text(
            "\n".join(manifest_lines) + "\n", encoding="utf-8"
        )

        if harness == "opencode":
            qualified_model = f"{provider}/{model}"
            opencode: Dict[str, object] = {
                "$schema": "https://opencode.ai/config.json",
                "enabled_providers": [provider],
                "small_model": qualified_model,
                "share": "disabled",
            }
            if github_copilot_business:
                opencode["provider"] = {
                    "github-copilot": {
                        "options": {"baseURL": GITHUB_COPILOT_BUSINESS_BASE_URL}
                    }
                }
            elif provider == "amazon-bedrock":
                opencode["provider"] = {
                    "amazon-bedrock": {
                        "options": {"region": bedrock_region}
                    }
                }
            if skill_names:
                opencode["permission"] = {"skill": {"*": "allow"}}
            (temporary / "harness" / "opencode.json").write_text(
                json.dumps(opencode, indent=2) + "\n", encoding="utf-8"
            )
        skill_root = temporary / "workspace" / ".agents" / "skills"
        for skill_dir, name in zip(skill_dirs, skill_names):
            shutil.copytree(
                skill_dir,
                skill_root / name,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
        temporary.rename(destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--harness", default="opencode", choices=sorted(SUPPORTED_HARNESSES))
    parser.add_argument(
        "--provider",
        choices=sorted(
            SUPPORTED_OPENCODE_PROVIDERS
            | SUPPORTED_OMP_PROVIDERS
            | SUPPORTED_PI_PROVIDERS
        ),
    )
    parser.add_argument("--github-copilot-business", action="store_true")
    parser.add_argument("--bedrock-region")
    parser.add_argument("--model", required=True)
    parser.add_argument("--auth-profile", required=True)
    parser.add_argument("--id", dest="config_id")
    parser.add_argument("--skill", action="append", default=[], type=Path)
    args = parser.parse_args()
    try:
        destination = create_configuration(
            args.repository,
            model=args.model,
            auth_profile=args.auth_profile,
            harness=args.harness,
            provider=args.provider,
            github_copilot_business=args.github_copilot_business,
            bedrock_region=args.bedrock_region,
            config_id=args.config_id,
            skills=args.skill,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
