FROM python@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libopengl0 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    numpy==2.3.2 \
    pymeshlab==2025.7.post1 \
    usd-core==25.11

WORKDIR /workspace
ENTRYPOINT ["python", "/workspace/projects/002_red_sea_digital_twin/pipelines/reef_ingest/prepare_reefs4d.py"]
