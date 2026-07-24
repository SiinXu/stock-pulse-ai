"""Distribution contract for the runtime-bundled Futu SDK."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_futu_sdk_is_pinned_and_verified_in_docker() -> None:
    requirements = _read("requirements.txt")
    dockerfile = _read("docker/Dockerfile")

    assert requirements.count("futu-api==10.8.6808") == 1
    assert (
        'HOME=/tmp/futu-sdk-smoke-home python -c '
        '"import alphasift.dsa_adapter; import futu"'
    ) in dockerfile
    assert "rm -rf /tmp/futu-sdk-smoke-home" in dockerfile


def test_futu_broker_module_is_copied_by_existing_docker_source_boundary() -> None:
    dockerfile = _read("docker/Dockerfile")

    assert "COPY src/ ./src/" in dockerfile
    assert (REPO_ROOT / "src/brokers/futu/portfolio.py").is_file()
