# syntax=docker/dockerfile:1.17
#
# The places module as the platform runs it: a place built from its data, as a
# job (python -m iocean_places.job '<brief>'; services/control-plane/internal/building).
#
# Built from the repository root with what is not in the repository beside it:
#
#   depth-models/unet-v1/       model.onnx and its meta, from ml/depth runs
#   depth-models/unet-v2-final/
#   coral-library/red-sea/      tools/coral-library, one folder per assemblage
#   coral-library/hawaii/
#   coral-library/caribbean/
#   ground-surfaces/*.jpg       the Poly Haven CC0 maps make-site lays the
#                               ground with (soft_*, hard_*, seabed_*), so a
#                               build does not depend on fetching them
#
#   docker build -f packages/places/Dockerfile -t iocean/places:r1 .
#
# Run from source rather than installed: the package's own install list does
# not yet name its fetch and models subpackages. The tools sit where they sit
# in the repository, because they find the places module, the materials and
# the water table by their own path.

FROM python:3.12-slim

# rasterio's wheel carries GDAL but not the XML parser GDAL is linked against.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "numpy>=1.26,<3" "scipy>=1.11" "pillow>=10" "matplotlib>=3.8" \
        "rasterio>=1.3.10" "onnxruntime>=1.18" "requests>=2.31" "h5py>=3.10" "tifffile>=2024.1.30"

WORKDIR /opt/iocean
COPY packages/places/iocean_places /opt/iocean/packages/places/iocean_places
COPY depth-models /opt/iocean/depth-models
# The ground and the reef: what tools/make-site and tools/aim-water read.
COPY tools/make-site tools/aim-water tools/built.py tools/reef.py tools/coral.py tools/coral_hd.py \
     tools/corallite.py tools/scanned.py tools/zonation.py tools/sediment.py tools/fringing.py \
     /opt/iocean/tools/
COPY catalog/materials /opt/iocean/catalog/materials
COPY services/sim-runtime/coral/water.py /opt/iocean/services/sim-runtime/coral/water.py
COPY coral-library /opt/iocean/coral-library
COPY ground-surfaces /opt/iocean/ground-surfaces

ENV PYTHONPATH=/opt/iocean/packages/places \
    PYTHONUNBUFFERED=1 \
    IOCEAN_DEPTH_MODELS=/opt/iocean/depth-models \
    IOCEAN_TOOLS=/opt/iocean/tools \
    IOCEAN_CORAL_LIBRARY=/opt/iocean/coral-library \
    IOCEAN_GROUND_SURFACES=/opt/iocean/ground-surfaces \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib

# The sandbox runs it read-only, with no capabilities, as nobody in particular.
USER 65534:65534
ENTRYPOINT []
CMD ["python", "-m", "iocean_places.job", "--help"]
