# syntax=docker/dockerfile:1.17
#
# The places module as the platform runs it: a place built from its data, as a
# job (python -m iocean_places.job '<brief>'; services/control-plane/internal/building).
#
# Built from the repository root with the depth models beside it:
#
#   depth-models/unet-v1/       model.onnx and its meta, from ml/depth runs
#   depth-models/unet-v2-final/
#
#   docker build -f packages/places/Dockerfile -t iocean/places:r1 .
#
# Run from source rather than installed: the package's own install list does
# not yet name its fetch and models subpackages.

FROM python:3.12-slim

RUN pip install --no-cache-dir \
        "numpy>=1.26,<3" "scipy>=1.11" "pillow>=10" "matplotlib>=3.8" \
        "rasterio>=1.3.10" "onnxruntime>=1.18" "requests>=2.31" "h5py>=3.10" "tifffile>=2024.1.30"

WORKDIR /opt/iocean
COPY packages/places/iocean_places /opt/iocean/places/iocean_places
COPY depth-models /opt/iocean/depth-models

ENV PYTHONPATH=/opt/iocean/places \
    PYTHONUNBUFFERED=1 \
    IOCEAN_DEPTH_MODELS=/opt/iocean/depth-models \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib

# The sandbox runs it read-only, with no capabilities, as nobody in particular.
USER 65534:65534
ENTRYPOINT []
CMD ["python", "-m", "iocean_places.job", "--help"]
