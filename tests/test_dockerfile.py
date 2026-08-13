"""Static production-container contract checks (the daemon is not always accessible)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_pins_the_supported_cuda_python_and_torch_stack() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "ARG CUDA_VERSION=12.8.1" in dockerfile
    assert "cudnn-runtime-ubuntu${UBUNTU_VERSION}" in dockerfile
    assert "ARG PYTHON_VERSION=3.11.15" in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cu128" in dockerfile
    assert "torch==2.11.0" in dockerfile
    assert "torchvision==0.26.0" in dockerfile


def test_dockerfile_installs_project_pins_and_drops_root() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "python -m pip install --no-cache-dir /tmp/wheels/segmentary-*.whl" in dockerfile
    assert "python -m pip check" in dockerfile
    assert "USER segmentary" in dockerfile
    assert dockerfile.index("USER segmentary") < dockerfile.index("ENTRYPOINT")
    assert "tensorrt==" not in dockerfile


def test_wheel_builder_has_every_declared_data_file_source() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    wheel_command = dockerfile.index("RUN /opt/python/bin/python3.11 -m pip wheel")
    for source in (
        "COPY pyproject.toml README.md LICENSE ./",
        "COPY src ./src",
        "COPY configs ./configs",
        "COPY taxonomy ./taxonomy",
        "COPY splits ./splits",
    ):
        assert source in dockerfile
        assert dockerfile.index(source) < wheel_command


def test_docker_context_excludes_credentials_data_and_weights() -> None:
    ignored = set((ROOT / ".dockerignore").read_text().splitlines())
    for required in (".git", ".env", "*.netrc", "cookies.txt", "data", "runs", "*.pth"):
        assert required in ignored
