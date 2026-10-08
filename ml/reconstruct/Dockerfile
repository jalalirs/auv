# A reef patch in 3D from a dive video: COLMAP for structure from motion and
# dense stereo (CUDA), Python around it for frames, orientation, scale and
# export to USD for the places.
#
#   docker compose -f ml/reconstruct/compose.yaml run --rm reconstruct video --video /data/raw/... --name NAME
FROM colmap/colmap:20260907.8077

RUN apt-get update && apt-get install -y --no-install-recommends python3-pip python3-venv && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir \
        "numpy<2.3" "pyyaml>=6" "pillow>=10" "av>=12" "open3d>=0.19" "usd-core>=24.11" "pytest>=8"

COPY ml/reconstruct /src/ml/reconstruct
ENV PATH=/venv/bin:$PATH \
    PYTHONPATH=/src/ml/reconstruct \
    IOCEAN_ML_DATA=/data \
    PYTHONUNBUFFERED=1
WORKDIR /src/ml/reconstruct
ENTRYPOINT ["python3", "-m", "iocean_reconstruct.cli"]
