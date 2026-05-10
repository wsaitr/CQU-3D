FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    CUDA_HOME=/usr/local/cuda \
    PIP_NO_CACHE_DIR=1 \
    D2DGS_ROOT=/workspace/repo/services/dynamic-2dgs \
    WHEELHOUSE=/workspace/repo/infra/docker/wheels

WORKDIR /workspace/repo

RUN set -eux; \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i 's|http://archive.ubuntu.com/ubuntu|https://mirrors.ustc.edu.cn/ubuntu|g' /etc/apt/sources.list; \
            sed -i 's|http://security.ubuntu.com/ubuntu|https://mirrors.ustc.edu.cn/ubuntu|g' /etc/apt/sources.list; \
        fi; \
        if [ -d /etc/apt/sources.list.d ]; then \
            find /etc/apt/sources.list.d -type f \( -name '*.list' -o -name '*.sources' \) -print0 \
                | xargs -0 -r sed -i 's|http://archive.ubuntu.com/ubuntu|https://mirrors.ustc.edu.cn/ubuntu|g; s|http://security.ubuntu.com/ubuntu|https://mirrors.ustc.edu.cn/ubuntu|g'; \
        fi; \
        apt-get update -o Acquire::Retries=5 \
        && apt-get install -y --no-install-recommends \
        python3 \
        python3-dev \
        python3-pip \
        python-is-python3 \
        build-essential \
        cmake \
        ninja-build \
        ffmpeg \
        curl \
        git \
        colmap \
        libegl1 \
        libx11-6 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY apps/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt \
    && python -m pip install \
        filelock==3.28.0 \
        fsspec==2026.3.0 \
        jinja2==3.1.6 \
        markupsafe==3.0.3 \
        mpmath==1.3.0 \
        networkx==3.4.2 \
        pillow==12.2.0 \
        requests==2.33.1 \
        sympy==1.14.0 \
        triton==2.1.0 \
        "numpy<2"

COPY apps/worker /workspace/repo/apps/worker
COPY packages /workspace/repo/packages
COPY --from=dynamic2dgs . /workspace/repo/services/dynamic-2dgs
COPY --from=wheelhouse . /workspace/repo/infra/docker/wheels
COPY infra/docker/install-d2dgs-deps.sh /workspace/repo/infra/docker/install-d2dgs-deps.sh
COPY infra/docker/worker-entrypoint.sh /workspace/repo/infra/docker/worker-entrypoint.sh

RUN chmod +x /workspace/repo/infra/docker/worker-entrypoint.sh \
    && chmod +x /workspace/repo/infra/docker/install-d2dgs-deps.sh \
    && /workspace/repo/infra/docker/install-d2dgs-deps.sh

CMD ["/workspace/repo/infra/docker/worker-entrypoint.sh"]
