# syntax=docker/dockerfile:1.17
#
# A dive video made into a reef in 3D, as the platform runs it
# (python -m iocean_reconstruct.job '<brief>';
# services/control-plane/internal/reconstructing).
#
# 3DGRUT trains the splats; COLMAP, from the reconstruct image, places the
# cameras, and is copied in with every library it was linked against, kept to
# itself (/opt/colmap/lib), so it cannot change what 3DGRUT loads. The weights
# are in the image, because the job runs with no network:
#
#   models/coralscapes/              CoralscapesV2's SegFormer (config.json,
#                                    model.safetensors, preprocessor_config.json)
#   models/torch/hub/checkpoints/    big-lama.pt, for simple-lama-inpainting
#
# Built from a folder holding packages/reconstruct, ml/splat,
# ml/cover/configs/cover.yaml and models/ in those places:
#
#   docker build -f packages/reconstruct/Dockerfile -t iocean/reconstruct-video:r1 .

FROM iocean/ml-reconstruct:dev AS colmap
RUN mkdir -p /opt/colmap/bin /opt/colmap/lib \
 && cp /usr/local/bin/colmap /opt/colmap/bin/ \
 && ldd /usr/local/bin/colmap | awk '/=>/ {print $3}' \
    | grep -vE '/(libc|libm|libdl|libpthread|librt|libcuda|libnvidia[^/]*)\.so|ld-linux' \
    | xargs -I{} cp -L {} /opt/colmap/lib/ \
 && cp -L /lib/x86_64-linux-gnu/libmkl_*.so /opt/colmap/lib/
# MKL opens its kernels (libmkl_def, libmkl_vml_def) by name when it first
# solves, which ldd does not see: without them the global mapper died at its
# first rotation average.

FROM iocean/3dgrut:dev

COPY --from=colmap /opt/colmap /opt/colmap
RUN printf '#!/bin/sh\nLD_LIBRARY_PATH=/opt/colmap/lib exec /opt/colmap/bin/colmap "$@"\n' > /usr/local/bin/colmap \
 && chmod 755 /usr/local/bin/colmap \
 && colmap help > /dev/null

RUN /workspace/.venv/bin/pip install --no-cache-dir "transformers>=4.44,<5" fire \
 && /workspace/.venv/bin/pip install --no-cache-dir --no-deps simple-lama-inpainting

COPY models /opt/iocean/models
COPY ml/splat /opt/iocean/splat
COPY ml/cover/configs/cover.yaml /opt/iocean/cover/cover.yaml
COPY packages/reconstruct/iocean_reconstruct /opt/iocean/reconstruct/iocean_reconstruct
RUN chmod -R a+rX /opt/iocean

ENV PATH=/workspace/.venv/bin:$PATH \
    PYTHONPATH=/opt/iocean/reconstruct \
    PYTHONUNBUFFERED=1 \
    IOCEAN_SPLAT=/opt/iocean/splat \
    IOCEAN_MODELS=/opt/iocean/models \
    IOCEAN_3DGRUT=/workspace \
    IOCEAN_COVER_GROUPS=/opt/iocean/cover/cover.yaml \
    HOME=/tmp

# The sandbox runs it read-only, with no capabilities, as nobody in particular.
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT []
CMD ["python", "-m", "iocean_reconstruct.job", "--help"]
