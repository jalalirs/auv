"""An OCI image written by hand: a base image's layout, with layers added.

A controller's image is always the same base (ROS 2 with numpy) and a few
files on top, so it is assembled rather than built: no Docker daemon, no
root, nothing the job's sandbox does not allow. The base arrives as an OCI
image layout (what `docker save` writes); each added layer is a gzipped tar
made here, byte for byte the same for the same files (sorted, owned by root,
dated at the epoch), so the same source makes the same digest.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import pathlib
import shutil
import tarfile

MANIFEST = "application/vnd.oci.image.manifest.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"
LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"
INDEX = "application/vnd.oci.image.index.v1+json"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class Layout:
    """An OCI image layout on disk: oci-layout, index.json, blobs/sha256/."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    def blob(self, digest: str) -> pathlib.Path:
        return self.root / "blobs" / "sha256" / digest.split(":", 1)[1]

    def read(self, digest: str) -> bytes:
        return self.blob(digest).read_bytes()

    def write(self, data: bytes) -> str:
        digest = _sha(data)
        path = self.blob(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return digest

    def manifest(self, platform: tuple[str, str] = ("linux", "amd64")) -> tuple[str, dict]:
        """The image manifest for a platform: through an index if there is one."""
        index = json.loads((self.root / "index.json").read_text())
        for entry in index["manifests"]:
            found = self._follow(entry, platform)
            if found:
                return found
        raise ValueError(f"the base has no image for {platform[0]}/{platform[1]}")

    def _follow(self, entry: dict, platform: tuple[str, str]) -> tuple[str, dict] | None:
        doc = json.loads(self.read(entry["digest"]))
        kind = doc.get("mediaType") or entry.get("mediaType", "")
        if "index" in kind or "manifest.list" in kind:
            for child in doc["manifests"]:
                p = child.get("platform", {})
                if p.get("architecture", platform[1]) == platform[1] and p.get("os", platform[0]) == platform[0]:
                    found = self._follow(child, platform)
                    if found:
                        return found
            return None
        return entry["digest"], doc


def oci_type(media: str) -> str:
    """A layer's media type as OCI names it: `docker save` may write Docker's
    names, and a layer keeps its own compression (saved ones are plain tar)."""
    if media in (LAYER, "application/vnd.docker.image.rootfs.diff.tar.gzip"):
        return LAYER
    if media in ("application/vnd.oci.image.layer.v1.tar", "application/vnd.docker.image.rootfs.diff.tar"):
        return "application/vnd.oci.image.layer.v1.tar"
    return media


def layer_of(files: list[tuple[str, pathlib.Path]]) -> tuple[bytes, str]:
    """A layer from (path in the image, file on disk) pairs; directories are
    made as needed. Returns the gzipped layer and its diff id (the digest of
    the tar before compression)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        made: set[str] = set()
        for inside, source in sorted(files, key=lambda f: f[0]):
            inside = inside.lstrip("/")
            parts = inside.split("/")
            for i in range(1, len(parts)):
                folder = "/".join(parts[:i])
                if folder not in made:
                    made.add(folder)
                    info = tarfile.TarInfo(folder)
                    info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, 0
                    tar.addfile(info)
            info = tarfile.TarInfo(inside)
            data = source.read_bytes()
            info.size, info.mtime = len(data), 0
            info.mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
            tar.addfile(info, io.BytesIO(data))
    plain = raw.getvalue()
    packed = io.BytesIO()
    with gzip.GzipFile(fileobj=packed, mode="wb", mtime=0) as gz:
        gz.write(plain)
    return packed.getvalue(), _sha(plain)


def files_under(folder: pathlib.Path, inside: str, skip=("__pycache__", ".git")) -> list[tuple[str, pathlib.Path]]:
    """Every file under a folder, as (path in the image, file) pairs."""
    out = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and not any(part in skip for part in f.relative_to(folder).parts):
            out.append((f"{inside.rstrip('/')}/{f.relative_to(folder).as_posix()}", f))
    return out


def assemble(base: pathlib.Path, out: pathlib.Path, layers: list[tuple[bytes, str, str]],
             env: dict[str, str], entrypoint: list[str], labels: dict[str, str], tag: str = "latest") -> dict:
    """The base image with `layers` ((gzipped, diff id, what it is)) on top,
    `env` merged into its environment, `entrypoint` set; written as a layout
    at `out`. Returns the manifest's digest and sizes."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out, ignore=shutil.ignore_patterns("index.json", "manifest.json", "repositories"))
    layout = Layout(out)
    _, manifest = Layout(base).manifest()
    config = json.loads(Layout(base).read(manifest["config"]["digest"]))
    given = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in config.get("config", {}).get("Env", []) if "=" in e}
    given.update(env)
    config.setdefault("config", {})["Env"] = [f"{k}={v}" for k, v in given.items()]
    config["config"]["Entrypoint"] = entrypoint
    config["config"]["Cmd"] = None
    config["config"]["Labels"] = {**(config["config"].get("Labels") or {}), **labels}
    for packed, diff_id, said in layers:
        digest = layout.write(packed)
        config["rootfs"]["diff_ids"].append(diff_id)
        config.setdefault("history", []).append({"created_by": f"iocean controller build: {said}"})
        manifest["layers"].append({"mediaType": LAYER, "digest": digest, "size": len(packed)})
    config_bytes = json.dumps(config, separators=(",", ":"), sort_keys=True).encode()
    manifest = {"schemaVersion": 2, "mediaType": MANIFEST,
                "config": {"mediaType": CONFIG, "digest": layout.write(config_bytes), "size": len(config_bytes)},
                "layers": [{**layer, "mediaType": oci_type(layer["mediaType"])} for layer in manifest["layers"]]}
    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    digest = layout.write(manifest_bytes)
    (out / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))
    (out / "index.json").write_text(json.dumps({"schemaVersion": 2, "mediaType": INDEX, "manifests": [
        {"mediaType": MANIFEST, "digest": digest, "size": len(manifest_bytes),
         "platform": {"architecture": "amd64", "os": "linux"},
         "annotations": {"org.opencontainers.image.ref.name": tag, "io.containerd.image.name": f"iocean/controller:{tag}"}}]}))
    # And the manifest Docker's own loader reads, as `docker save` writes it,
    # so the image also loads with `docker load` (a registry reads index.json).
    (out / "manifest.json").write_text(json.dumps([{
        "Config": f"blobs/sha256/{manifest['config']['digest'].split(':', 1)[1]}",
        "RepoTags": [f"iocean/controller:{tag}"],
        "Layers": [f"blobs/sha256/{layer['digest'].split(':', 1)[1]}" for layer in manifest["layers"]]}]))
    # Only the blobs this image uses: the base's own index and manifests go.
    used = {manifest["config"]["digest"], digest, *(layer["digest"] for layer in manifest["layers"])}
    for blob in (out / "blobs" / "sha256").iterdir():
        if f"sha256:{blob.name}" not in used:
            blob.unlink()
    return {"digest": digest, "layers": len(manifest["layers"]),
            "sizeBytes": sum(layer["size"] for layer in manifest["layers"]) + len(config_bytes)}


def tar_layout(layout: pathlib.Path, out: pathlib.Path) -> None:
    with tarfile.open(out, "w") as tar:
        for f in sorted(layout.rglob("*")):
            if f.is_file():
                tar.add(f, arcname=f.relative_to(layout).as_posix())
