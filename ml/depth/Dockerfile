# The depth model: build its dataset, train it, evaluate it.
#
# PyTorch with CUDA for training, and GDAL (through rasterio's wheels) for
# building the dataset: the NOAA lidar and the Sentinel-2 archive are read
# here, not on the host. The code runs from source, with the places package
# beside it, because the dataset is cut on the places module's grid.
#
#   docker compose -f ml/depth/compose.yaml run --rm depth train --config train/unet-v1.yaml
#
# or `just ml-depth train --config train/unet-v1.yaml` from the repository.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

RUN pip install --no-cache-dir \
        "numpy<2.3" "pyyaml>=6" "rasterio>=1.4" "scipy>=1.11" "pillow>=10" "matplotlib>=3.8" \
        "requests>=2.31" "h5py>=3.10" "pytest>=8"

COPY packages/places /src/packages/places
COPY ml/depth /src/ml/depth

ENV PYTHONPATH=/src/ml/depth:/src/packages/places \
    IOCEAN_ML_DATA=/data \
    PYTHONUNBUFFERED=1
WORKDIR /src/ml/depth
ENTRYPOINT ["python", "-m", "iocean_depth.cli"]
