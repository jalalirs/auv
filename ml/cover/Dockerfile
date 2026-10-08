# Coral cover from underwater imagery: run CoralscapesV2's segmentation model
# over its test split and over photo mosaics, and write cover maps.
#
# PyTorch with CUDA and Hugging Face's transformers for the model, GDAL
# (through rasterio's wheels) for the mosaics, pyarrow for the test set.
#
#   docker compose -f ml/cover/compose.yaml run --rm cover check
#
# or `just ml-cover check` from the repository.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

RUN pip install --no-cache-dir \
        "numpy<2.3" "pyyaml>=6" "rasterio>=1.4" "pillow>=10" "pyarrow>=15" \
        "transformers>=5.0,<6" "safetensors>=0.4" "huggingface_hub>=0.30" "pytest>=8"

COPY ml/cover /src/ml/cover

ENV PYTHONPATH=/src/ml/cover \
    IOCEAN_ML_DATA=/data \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PYTHONUNBUFFERED=1
WORKDIR /src/ml/cover
ENTRYPOINT ["python", "-m", "iocean_cover.cli"]
