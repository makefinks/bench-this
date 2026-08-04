import importlib.util
from pathlib import Path


SCRIPT = Path("scripts/sync_vendored_runner.py").resolve()


def load_script():
    spec = importlib.util.spec_from_file_location("sync_vendored_runner", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_comparison_detects_file_and_content_drift(tmp_path):
    module = load_script()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "runner.py").write_text("canonical\n")
    (destination / "runner.py").write_text("drifted\n")
    (destination / "extra.py").write_text("extra\n")

    assert module._different(source, destination) == ["extra.py", "runner.py"]
