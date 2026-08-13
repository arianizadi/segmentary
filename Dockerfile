# syntax=docker/dockerfile:1.7

# Python is compiled in a disposable CUDA build stage so the runtime image stays
# on NVIDIA's CUDA 12.8 stack while using the project's exact Python 3.11 line.
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION} AS python-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG PYTHON_VERSION=3.11.15
ARG PYTHON_SHA256=f4de1b10bd6c70cbb9fa1cd71fc5038b832747a74ee59d599c69ce4846defb50
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libbz2-dev \
        libffi-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        uuid-dev \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/python-build
RUN curl --fail --location --retry 5 \
        "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" \
        --output Python.tgz \
    && echo "${PYTHON_SHA256}  Python.tgz" | sha256sum --check --strict \
    && tar --extract --gzip --file Python.tgz --strip-components=1 \
    && ./configure \
        --prefix=/opt/python \
        --enable-shared \
        --with-ensurepip=install \
    && make --jobs="$(nproc)" \
    && make install \
    && cd / \
    && rm -rf /tmp/python-build

ENV LD_LIBRARY_PATH=/opt/python/lib:${LD_LIBRARY_PATH}
WORKDIR /

FROM python-builder AS wheel-builder

RUN /opt/python/bin/python3.11 -m pip install --no-cache-dir \
        pip==26.2.1 \
        setuptools==78.1.0 \
        wheel==0.47.0

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs ./configs
COPY taxonomy ./taxonomy
COPY splits ./splits
RUN /opt/python/bin/python3.11 -m pip wheel \
        --no-build-isolation \
        --no-deps \
        --wheel-dir /wheels \
        .

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION} AS runtime

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libbz2-1.0 \
        libffi8 \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        liblzma5 \
        libncursesw6 \
        libreadline8 \
        libsqlite3-0 \
        libssl3 \
        libuuid1 \
        tini \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /opt/python /opt/python
RUN echo "/opt/python/lib" > /etc/ld.so.conf.d/python.conf \
    && ldconfig \
    && ln -s /opt/python/bin/python3.11 /usr/local/bin/python

ENV PATH=/opt/python/bin:${PATH} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    XDG_CACHE_HOME=/cache

COPY --from=wheel-builder /wheels /tmp/wheels
RUN python -m pip install --no-cache-dir \
        pip==26.2.1 \
        setuptools==78.1.0 \
        wheel==0.47.0 \
    && python -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu128 \
        torch==2.11.0 \
        torchvision==0.26.0 \
    && python -m pip install --no-cache-dir /tmp/wheels/segmentary-*.whl \
    && python -m pip check \
    && rm -rf /tmp/wheels

RUN groupadd --gid 10001 segmentary \
    && useradd --uid 10001 --gid segmentary --create-home --shell /bin/bash segmentary \
    && install --directory --owner=segmentary --group=segmentary /cache /workspace /runs

ENV HOME=/home/segmentary

WORKDIR /workspace
COPY --chown=segmentary:segmentary configs ./configs
COPY --chown=segmentary:segmentary taxonomy ./taxonomy
COPY --chown=segmentary:segmentary scripts ./scripts
COPY --chown=segmentary:segmentary README.md LICENSE ./

USER segmentary

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["segmentary-train", "--help"]
