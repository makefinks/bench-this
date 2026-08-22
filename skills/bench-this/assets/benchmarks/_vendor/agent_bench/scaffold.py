"""Generate a repository-local benchmark runner that remains independently usable."""

import hashlib
import importlib.metadata
import re
import shutil
from pathlib import Path

import yaml

from .errors import ConfigurationError


def _pyyaml_license_path() -> Path:
    """Locate the MIT license beside vendored PyYAML or in its installed metadata."""

    package_license = Path(yaml.__file__).parent / "LICENSE"
    if package_license.is_file():
        return package_license

    try:
        distribution = importlib.metadata.distribution("PyYAML")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ConfigurationError("cannot locate the PyYAML distribution license") from exc
    for relative in distribution.files or ():
        if Path(relative).name == "LICENSE":
            license_path = Path(distribution.locate_file(relative))
            if license_path.is_file():
                return license_path
    raise ConfigurationError("the PyYAML distribution does not include its LICENSE file")


def _third_party_notice() -> str:
    """Record the exact dependency version and upstream source shipped by the runner."""

    return (
        "# Third-party software\n\n"
        f"- PyYAML {yaml.__version__} — https://github.com/yaml/pyyaml — MIT License\n\n"
        "The complete PyYAML license is available at `yaml/LICENSE`.\n"
    )


def _image_name(project_root: Path) -> str:
    """Create a stable local image tag that cannot collide with another checkout."""

    slug = re.sub(r"[^a-z0-9]+", "-", project_root.name.lower()).strip("-") or "project"
    digest = hashlib.sha256(str(project_root).encode()).hexdigest()[:8]
    return f"agent-bench-{slug[:40].rstrip('-')}-{digest}"


def _set_image_name(destination: Path, project_root: Path) -> None:
    path = destination / "benchmark.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["image"]["name"] = _image_name(project_root)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def scaffold(project_root: Path) -> Path:
    """Copy templates and vendor runtime Python dependencies into benchmarks/."""

    project_root = project_root.resolve()
    destination = project_root / "benchmarks"
    if destination.exists() and any(destination.iterdir()):
        raise ConfigurationError(f"refusing to overwrite non-empty {destination}")
    template = Path(__file__).parent / "template" / "benchmarks"
    shutil.copytree(template, destination, dirs_exist_ok=True)
    _set_image_name(destination, project_root)
    for relative in (
        "tasks/example/public",
        "tasks/example/public-tests",
    ):
        (destination / relative).mkdir(parents=True, exist_ok=True)

    vendor_root = destination / "_vendor"
    vendor = vendor_root / "agent_bench"
    source = Path(__file__).parent
    # Vendoring keeps historical benchmarks runnable even if this package or
    # creator skill is later removed from the developer's machine.
    shutil.copytree(
        source,
        vendor,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # PyYAML gracefully falls back to its pure-Python loader when the optional C
    # extension is absent, so copying the package is portable across host systems.
    shutil.copytree(
        Path(yaml.__file__).parent,
        vendor_root / "yaml",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "_yaml*.so"),
    )
    shutil.copy2(_pyyaml_license_path(), vendor_root / "yaml" / "LICENSE")
    (vendor_root / "THIRD_PARTY_NOTICES.md").write_text(
        _third_party_notice(), encoding="utf-8"
    )
    (destination / "setup.sh").chmod(0o755)
    (destination / "run.py").chmod(0o755)
    (destination / "tasks" / "example" / "hidden-tests" / "run.sh").chmod(0o755)
    (destination / "tasks" / "example" / "public-tests" / "run.sh").chmod(0o755)
    return destination
