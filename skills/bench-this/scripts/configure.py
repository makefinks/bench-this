#!/usr/bin/env python3
"""Create one catalog-validated benchmark treatment without hand-written YAML."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional


SKILL_ROOT = Path(__file__).resolve().parents[1]
VENDOR = SKILL_ROOT / "assets" / "benchmarks" / "_vendor"
sys.path.insert(0, str(VENDOR))

import yaml

from agent_bench.catalog import HARNESS_CATALOG, resolve_selection
from agent_bench.config import ID_PATTERN, load_configuration
from agent_bench.errors import ConfigurationError
from agent_bench.writers import write_native_configuration


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
                raise ValueError(
                    f"skill directory {skill_dir.name!r} must match name {name!r}"
                )
            return name
    else:
        raise ValueError(f"skill frontmatter is missing name: {manifest}")
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
    bedrock_wire_api: Optional[str] = None,
    agent: Optional[str] = None,
    arguments: Iterable[str] = (),
    config_id: Optional[str] = None,
    skills: Iterable[Path] = (),
) -> Path:
    """Create one atomic treatment from the bundled catalog and canonical loader."""

    repository = repository.expanduser().resolve()
    benchmark_dir = repository / "benchmarks"
    if not (benchmark_dir / "benchmark.yaml").is_file():
        raise ValueError(f"benchmark scaffold not found: {benchmark_dir}")
    harness_spec, provider_spec = resolve_selection(harness, provider)
    provider = provider_spec.id

    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if model == "auto" and not provider_spec.allow_automatic_model:
        raise ValueError("model must be explicitly pinned")
    if github_copilot_business and "github_copilot_business" not in provider_spec.allowed_fields:
        raise ValueError(
            "--github-copilot-business requires --harness opencode "
            "--provider github-copilot"
        )
    if "region" in provider_spec.required_fields:
        if not bedrock_region:
            raise ValueError(
                "Amazon Bedrock configurations require a valid --bedrock-region"
            )
    elif bedrock_region is not None:
        raise ValueError("--bedrock-region applies only to Amazon Bedrock")
    if bedrock_wire_api is not None and "wire_api" not in provider_spec.allowed_fields:
        raise ValueError("--bedrock-wire-api applies only to Amazon Bedrock")
    if bedrock_wire_api is not None and bedrock_wire_api not in {
        "completions",
        "responses",
    }:
        raise ValueError("--bedrock-wire-api must be one of: completions, responses")
    if agent is not None and "agent" not in harness_spec.allowed_fields:
        raise ValueError(f"--agent does not apply to {harness_spec.display_name}")
    arguments = list(arguments)
    if not all(isinstance(argument, str) for argument in arguments):
        raise ValueError("arguments must be strings")

    _id(auth_profile, "auth profile")
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

    skill_dirs = [path.expanduser().resolve() for path in skills]
    skill_names = []
    for skill_dir in skill_dirs:
        if not skill_dir.is_dir():
            raise ValueError(f"skill directory does not exist: {skill_dir}")
        _reject_symlinks(skill_dir, "skill")
        skill_names.append(_skill_name(skill_dir))
    if len(set(skill_names)) != len(skill_names):
        raise ValueError("skill names must be unique")

    staging_root = Path(
        tempfile.mkdtemp(prefix=".configuration-", dir=config_root)
    )
    temporary = staging_root / config_id
    try:
        (temporary / "harness").mkdir(parents=True)
        (temporary / "workspace").mkdir()
        manifest = dict(harness_spec.generator_defaults)
        manifest.update({"id": config_id, "harness": harness})
        if provider is not None:
            manifest["provider"] = provider
        manifest["model"] = model
        if agent is not None:
            manifest["agent"] = agent
        if bedrock_region is not None:
            manifest["region"] = bedrock_region
        if bedrock_wire_api is not None:
            manifest["wire_api"] = bedrock_wire_api
        if github_copilot_business:
            manifest["github_copilot_business"] = True
        manifest.update(
            {
                "harness_config": "harness",
                "workspace_config": "workspace",
                "auth_profile": auth_profile,
                "arguments": arguments,
            }
        )
        manifest_path = temporary / "configuration.yaml"
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )
        config = load_configuration(manifest_path)
        write_native_configuration(config, skill_names)

        skill_root = temporary / "workspace" / ".agents" / "skills"
        for skill_dir, name in zip(skill_dirs, skill_names):
            shutil.copytree(
                skill_dir,
                skill_root / name,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
        temporary.rename(destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--harness", default="opencode", choices=sorted(HARNESS_CATALOG))
    parser.add_argument(
        "--provider",
        choices=sorted(
            {
                provider
                for harness in HARNESS_CATALOG.values()
                for provider in harness.providers
                if provider is not None
            }
        ),
    )
    parser.add_argument("--github-copilot-business", action="store_true")
    parser.add_argument("--bedrock-region")
    parser.add_argument(
        "--bedrock-wire-api", choices=["completions", "responses"]
    )
    parser.add_argument("--agent")
    parser.add_argument("--argument", action="append", default=[])
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
            bedrock_wire_api=args.bedrock_wire_api,
            agent=args.agent,
            arguments=args.argument,
            config_id=args.config_id,
            skills=args.skill,
        )
    except (ValueError, ConfigurationError) as exc:
        parser.error(str(exc))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
