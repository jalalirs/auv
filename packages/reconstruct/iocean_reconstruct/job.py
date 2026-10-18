"""A dive video made into a reef in 3D, as the platform runs it.

    python -m iocean_reconstruct.job '<brief>'

The brief (services/control-plane/internal/reconstructing):

    {"video": {"objectId", "name", "path"},      the video, under /work/inputs
     "name": "...", "label": "...",
     "cameraHeightM": 1.92,                       the camera's height over the reef;
                                                  assumed 1.92 when not given
     "start": {"lat", "lon"},                     where the video starts; recorded only
     "fps": 2,                                    frames taken a second
     "tape": "auto" | "keep",                     a survey tape painted out, or left
     "effort": "full" | "quick",                  quick: a short training, to try
     "camera": {"model": "OPENCV", "params": "fx,fy,cx,cy,k1,k2,p1,p2"}}
                                                  a known calibration, at the frames' size

What it does, each step said as {"progress": {...}} on stdout:

  frames       the video's frames, --fps a second, 1600 wide at most
  cameras      COLMAP: features, sequential matching, the global mapper, the
               largest model undistorted
  tape         CoralscapesV2's 'transect line' and 'transect tools' in every
               frame; when there is a tape, a quick model finds it in 3D and
               completes the masks, and LaMa paints it out of every frame
  pieces       the swim cut into overlapping stretches, each trained on its own
               (3DGRUT 3DGUT): one model of a long video is too big for one card
  frame        the reef levelled, centred and in metres (splat_place.py,
               asset_frame.py); every piece moved into that frame (bake_splats.py)
  surface      the ground the splats stand on (splat_surface.py)
  trim         the video's water taken out, the edge faded (trim_splats.py)
  parts        each piece as NuRec splats at half precision
  cover        the cover the frames show, by CoralscapesV2's groups
  package      reconstruction.tar: reconstruction.json, parts/, surface.f32,
               surface.json, path.json, preview.jpg, previews/

It is an asset in its own frame, mapped nowhere: putting it on a map is a
separate step (the mapping job and Resolve). Run inside iocean/reconstruct-video.
Scratch is IOCEAN_JOB_SCRATCH; a step whose work is already there is not done
again, so a run that stopped can be run again on the same scratch.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback

INPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_INPUTS", "/work/inputs"))
OUTPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_OUTPUTS", "/work/outputs"))
SCRATCH = pathlib.Path(os.environ.get("IOCEAN_JOB_SCRATCH") or OUTPUTS / "scratch")
SPLAT = pathlib.Path(os.environ.get("IOCEAN_SPLAT", "/opt/iocean/splat"))
MODELS = pathlib.Path(os.environ.get("IOCEAN_MODELS", "/opt/iocean/models"))
GRUT = pathlib.Path(os.environ.get("IOCEAN_3DGRUT", "/workspace"))
COVER_GROUPS = pathlib.Path(os.environ.get("IOCEAN_COVER_GROUPS", "/opt/iocean/cover/cover.yaml"))
COLMAP = os.environ.get("IOCEAN_COLMAP", "colmap")

ASSUMED_CAMERA_HEIGHT = 1.92
# Frames each piece owns, and how many more either side it is trained on so
# its own edge is good (the Red Sea video's three pieces: 260 and 30).
OWN, OVERLAP = 260, 30
# A NuRec part at half precision is about 120 bytes a splat, and USD reads a
# .usdz only below 2 GB.
MOST_SPLATS = 9_000_000
TAPE_HALF_WIDTH_M = 0.0125


def tell(step: str, say: str, **detail) -> None:
    print(json.dumps({"progress": {"step": step, "say": say, **detail}}), flush=True)


def done(name: str) -> bool:
    return (SCRATCH / f".done-{name}").is_file()


def mark(name: str, said: dict | None = None) -> None:
    (SCRATCH / f".done-{name}").write_text(json.dumps(said or {}))


def said_by(name: str) -> dict:
    return json.loads((SCRATCH / f".done-{name}").read_text())


def run(step: str, argv: list[str], *, cwd: pathlib.Path | None = None, log: pathlib.Path | None = None,
        lines: bool = True) -> list[str]:
    """A tool run to its end; the JSON lines it prints are passed on, the rest
    kept for when it fails."""
    out = open(log, "a") if log else None
    proc = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            cwd=str(cwd or SCRATCH), errors="replace")
    said = []
    for line in proc.stdout:
        if out:
            out.write(line)
        line = line.rstrip()
        said.append(line)
        del said[:-400]
        if lines and line.startswith("{"):
            tell(step, line[:2000])
    if out:
        out.close()
    if proc.wait() != 0:
        raise RuntimeError(f"{pathlib.Path(str(argv[1] if argv[0] == sys.executable else argv[0])).name} failed: "
                           + " | ".join(said[-8:]))
    return said


def last_json(said: list[str]) -> dict:
    for line in reversed(said):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


def python(script: str, *args) -> list:
    return [sys.executable, str(SPLAT / script), *args]


# -- frames -----------------------------------------------------------------------------------------

def frames(brief: dict) -> dict:
    import cv2

    images = SCRATCH / "frames"
    if done("frames"):
        return said_by("frames")
    images.mkdir(parents=True, exist_ok=True)
    video = INPUTS / brief["video"]["path"]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"the video {brief['video'].get('name', video.name)} could not be read")
    rate = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(brief.get("fps") or 2.0)
    duration = total / rate if total else 0.0
    tell("frames", f"{duration / 60:.1f} min of {width}x{height} at {rate:.2f} fps; taking {fps:g} a second",
         durationS=round(duration, 1), width=width, height=height, fps=round(rate, 3))
    scale = min(1.0, 1600.0 / max(width, 1))
    size = (int(round(width * scale / 2)) * 2, int(round(height * scale / 2)) * 2)
    i, kept, next_t = 0, 0, 0.0
    while True:
        if not cap.grab():
            break
        t = i / rate
        i += 1
        if t + 1e-6 < next_t:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            break
        next_t += 1.0 / fps
        if scale < 1.0:
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
        kept += 1
        cv2.imwrite(str(images / f"{kept:05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if kept % 100 == 0:
            tell("frames", f"{kept} frames", n=int(t), of=int(duration))
    cap.release()
    if kept < 20:
        raise RuntimeError(f"only {kept} frames could be taken from the video; a reef needs a swim of a minute or more")
    said = {"frames": kept, "video": {"name": brief["video"].get("name", video.name), "durationS": round(duration, 1),
                                      "fps": round(rate, 3), "width": width, "height": height},
            "size": list(size), "every": round(1.0 / fps, 3)}
    mark("frames", said)
    tell("frames", f"{kept} frames at {size[0]}x{size[1]}", frames=kept)
    return said


# -- cameras ----------------------------------------------------------------------------------------

def registered_in(model: pathlib.Path) -> int:
    said = run("cameras", [COLMAP, "model_analyzer", "--path", model], lines=False)
    for line in said:
        m = re.search(r"Registered images:\s*(\d+)", line)
        if m:
            return int(m.group(1))
    return 0


def cameras(brief: dict, frames_said: dict) -> dict:
    if done("cameras"):
        return said_by("cameras")
    db, images, logs = SCRATCH / "colmap.db", SCRATCH / "frames", SCRATCH / "logs"
    logs.mkdir(exist_ok=True)
    camera = brief.get("camera") or {}
    extract = [COLMAP, "feature_extractor", "--database_path", db, "--image_path", images,
               "--ImageReader.single_camera", "1", "--ImageReader.camera_model", camera.get("model", "OPENCV"),
               "--FeatureExtraction.use_gpu", "1"]
    if camera.get("params"):
        extract += ["--ImageReader.camera_params", camera["params"]]
    if not done("features"):
        db.unlink(missing_ok=True)
        tell("cameras", "finding features in every frame")
        run("cameras", extract, log=logs / "features.log", lines=False)
        mark("features")
    if not done("matches"):
        tell("cameras", "matching each frame with the 15 either side")
        run("cameras", [COLMAP, "sequential_matcher", "--database_path", db, "--SequentialMatching.overlap", "15",
                        "--FeatureMatching.use_gpu", "1"], log=logs / "match.log", lines=False)
        mark("matches")
    if not camera.get("params") and not done("calibrated"):
        # The global mapper rests on each camera's focal length; with no
        # calibration given, it is estimated from the matches first.
        tell("cameras", "estimating the camera's focal length from the matches")
        run("cameras", [COLMAP, "view_graph_calibrator", "--database_path", db], log=logs / "calibrate.log",
            lines=False)
        mark("calibrated")
    mapped = SCRATCH / "sparse"
    if not done("mapped"):
        shutil.rmtree(mapped, ignore_errors=True)
        mapped.mkdir()
        tell("cameras", "solving every camera and the reef's points (COLMAP's global mapper)")
        run("cameras", [COLMAP, "global_mapper", "--database_path", db, "--image_path", images,
                        "--output_path", mapped], log=logs / "mapper.log", lines=False)
        mark("mapped")
    models = sorted(p for p in mapped.iterdir() if p.is_dir())
    if not models:
        raise RuntimeError("COLMAP could not place the cameras: the frames did not match one another "
                           "(too fast, too dark, too much open water?)")
    counted = [(registered_in(m), m) for m in models]
    most, best = max(counted)
    tell("cameras", f"{most} of {frames_said['frames']} frames placed"
         + (f" ({len(models)} separate models; the largest kept)" if len(models) > 1 else ""),
         registered=most, frames=frames_said["frames"], models=len(models))
    if most < max(20, 0.3 * frames_said["frames"]):
        raise RuntimeError(f"COLMAP placed only {most} of {frames_said['frames']} frames in one model; "
                           "the swim breaks into pieces it could not join")
    dense, data = SCRATCH / "undistorted", SCRATCH / "data"
    shutil.rmtree(dense, ignore_errors=True)
    shutil.rmtree(data, ignore_errors=True)
    run("cameras", [COLMAP, "image_undistorter", "--image_path", images, "--input_path", best,
                    "--output_path", dense, "--output_type", "COLMAP"], log=logs / "undistort.log", lines=False)
    (data / "sparse" / "0").mkdir(parents=True)
    (dense / "images").rename(data / "images")
    for f in (dense / "sparse").glob("*.bin"):
        shutil.move(str(f), data / "sparse" / "0" / f.name)
    (data / "text").mkdir()
    run("cameras", [COLMAP, "model_converter", "--input_path", data / "sparse" / "0",
                    "--output_path", data / "text", "--output_type", "TXT"], lines=False)
    shutil.rmtree(dense, ignore_errors=True)
    said = {"registered": most, "models": len(models)}
    mark("cameras", said)
    return said


# -- training ---------------------------------------------------------------------------------------

def grut_copy() -> pathlib.Path:
    """3DGRUT's code where it can write: it compiles its kernels into its own
    folders when it first runs, and the image's root is read-only."""
    copy = SCRATCH / "3dgrut"
    if not (copy / "train.py").is_file():
        shutil.rmtree(copy, ignore_errors=True)
        copy.mkdir()
        for item in GRUT.iterdir():
            if item.name in (".venv", ".git", "thirdparty"):
                continue
            (shutil.copytree if item.is_dir() else shutil.copy2)(item, copy / item.name)
        (copy / "thirdparty").symlink_to(GRUT / "thirdparty")
        # Its metrics build a VGG for LPIPS when training starts, and VGG's
        # weights are fetched from the network, which a job does not have.
        # LPIPS is only used in validation, which colmap_3dgut never runs.
        trainer = copy / "threedgrut" / "trainer.py"
        text = trainer.read_text()
        lpips = 'lpips=LearnedPerceptualImagePatchSimilarity(net_type="vgg", normalize=True).to(self.device),'
        if lpips in text:
            trainer.write_text(text.replace(lpips, "lpips=None,"))
    return copy


def train(step: str, data: pathlib.Path, name: str, quick: bool, *, downsample: int = 1,
          iterations: int | None = None) -> pathlib.Path:
    """One model trained; densifying less when the card runs out of memory."""
    runs = SCRATCH / "runs"
    found = sorted((runs / name).glob("*/ckpt_last.pt"))
    if found and done(f"train-{name}"):
        return found[-1]
    code, logs = grut_copy(), SCRATCH / "logs"
    steps = iterations or (4000 if quick else 30000)
    for grad in ("0.0002", "0.0003", "0.0004"):
        shutil.rmtree(runs / name, ignore_errors=True)
        log = logs / f"train-{name}.log"
        log.unlink(missing_ok=True)
        argv = [sys.executable, "train.py", "--config-name", "apps/colmap_3dgut.yaml", f"path={data}",
                f"out_dir={runs}", f"experiment_name={name}", f"dataset.downsample_factor={downsample}",
                "export_usd.enabled=false", f"n_iterations={steps}", "compute_extra_metrics=false",
                f"strategy.densify.clone_grad_threshold={grad}", f"strategy.densify.split_grad_threshold={grad}",
                f"hydra.run.dir={SCRATCH / 'hydra' / name}"]
        with open(log, "w") as out:
            proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, cwd=str(code))
            last = 0.0
            while proc.poll() is None:
                time.sleep(20)
                if time.time() - last > 120:
                    last = time.time()
                    at = _training_step(log)
                    if at:
                        tell(step, f"{name}: step {at[0]:,} of {at[1]:,}", n=at[0], of=at[1])
        tail = log.read_text(errors="replace")[-6000:]
        found = sorted((runs / name).glob("*/ckpt_last.pt"))
        if proc.returncode == 0 and found:
            mark(f"train-{name}", {"grad": grad})
            return found[-1]
        if "OutOfMemoryError" not in tail and "out of memory" not in tail:
            raise RuntimeError(f"training {name} failed: " + " | ".join(tail.strip().splitlines()[-8:]))
        tell(step, f"{name}: the card ran out of memory; densifying less (gradient {grad} was too low)")
    raise RuntimeError(f"training {name} ran out of memory even densifying least")


def _training_step(log: pathlib.Path) -> tuple[int, int] | None:
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8000))
            text = f.read().decode(errors="replace")
    except OSError:
        return None
    hits = re.findall(r"(\d+)/(\d+) \[", text)
    return (int(hits[-1][0]), int(hits[-1][1])) if hits else None


# -- tape -------------------------------------------------------------------------------------------

def tape(brief: dict, quick: bool) -> dict:
    data = SCRATCH / "data"
    if done("tape"):
        return said_by("tape")
    if brief.get("tape", "auto") == "keep":
        said = {"found": False, "paintedOut": False, "why": "kept, as asked"}
        mark("tape", said)
        return said
    masks = SCRATCH / "tape-masks"
    names = sorted(p.stem for p in (data / "images").glob("*.jpg"))
    tell("tape", "looking for a survey tape in every frame (CoralscapesV2)")
    seg = last_json(run("tape", python("segment_tape.py", MODELS / "coralscapes", data / "images", masks), lines=False))
    with_tape = int(seg.get("withTape", 0))
    if with_tape < max(10, 0.03 * len(names)):
        said = {"found": False, "paintedOut": False, "framesWithTape": with_tape,
                "why": f"in {with_tape} of {len(names)} frames: no tape to take out"}
        mark("tape", said)
        tell("tape", said["why"])
        return said
    tell("tape", f"a tape in {with_tape} of {len(names)} frames; finding it in 3D", framesWithTape=with_tape)
    ckpt = train("tape", data, "tape-finder", quick, downsample=2, iterations=3000 if quick else 8000)
    # The tape's width in COLMAP's units, from a quick frame of the quick model.
    look = SCRATCH / "tape-frame"
    run("tape", python("splat_place.py", ckpt, "-", data / "text", look, "--camera-height",
                       brief.get("cameraHeightM") or ASSUMED_CAMERA_HEIGHT), lines=False)
    import numpy as np

    scale = float(np.load(look / "frame.npz")["scale"])
    run("tape", python("recolour_tape.py", ckpt, data / "text", masks, SCRATCH / "tape-recoloured.pt",
                       f"1:{len(names)}", "--save-tape", SCRATCH / "tape.npy"))
    (SCRATCH / "tape-recoloured.pt").unlink(missing_ok=True)
    run("tape", python("masks_from_splats.py", data / "text", masks, SCRATCH / "tape-masks-3d", data / "images",
                       SCRATCH / "tape.npy", "--half-width", f"{TAPE_HALF_WIDTH_M / scale:.6g}"), lines=False)
    tell("tape", f"painting the tape out of {len(names)} frames (LaMa)")
    painted = SCRATCH / "painted"
    run("tape", python("lama_tape.py", data / "images", SCRATCH / "tape-masks-3d", painted), lines=False)
    # The frames trained on from here are the painted ones; the video's own
    # are kept for the cover and the previews.
    (data / "images").rename(SCRATCH / "frames-undistorted")
    painted.rename(data / "images")
    shutil.rmtree(SCRATCH / "runs" / "tape-finder", ignore_errors=True)
    said = {"found": True, "paintedOut": True, "framesWithTape": with_tape,
            "how": "CoralscapesV2 'transect line' and 'transect tools', completed from the tape found in 3D, "
                   "painted out by LaMa before the reef was trained"}
    mark("tape", said)
    return said


# -- pieces -----------------------------------------------------------------------------------------

def pieces_of(n: int) -> list[dict]:
    k = max(1, round(n / OWN))
    edges = [round(i * n / k) for i in range(k + 1)]
    out = []
    for i in range(k):
        lo, hi = edges[i] + 1, edges[i + 1]
        out.append({"name": f"piece-{i + 1}", "first": lo, "last": hi,
                    "trainFirst": max(1, lo - OVERLAP), "trainLast": min(n, hi + OVERLAP)})
    return out


def pieces(quick: bool) -> list[dict]:
    data = SCRATCH / "data"
    names = sorted(p.name for p in (data / "images").glob("*.jpg"))
    said = pieces_of(len(names))
    tell("pieces", f"{len(names)} frames in {len(said)} pieces of about {OWN}, trained one after another",
         pieces=[[p["first"], p["last"]] for p in said])
    for i, piece in enumerate(said):
        root = SCRATCH / "pieces" / piece["name"]
        if not done(f"data-{piece['name']}"):
            shutil.rmtree(root, ignore_errors=True)
            (root / "images").mkdir(parents=True)
            (root / "sparse" / "0").mkdir(parents=True)
            keep = names[piece["trainFirst"] - 1:piece["trainLast"]]
            drop = SCRATCH / f"drop-{piece['name']}.txt"
            drop.write_text("\n".join(sorted(set(names) - set(keep))) + "\n")
            run("pieces", [COLMAP, "image_deleter", "--input_path", data / "sparse" / "0",
                           "--output_path", root / "sparse" / "0", "--image_names_path", drop], lines=False)
            for name in keep:
                os.link(data / "images" / name, root / "images" / name)
            mark(f"data-{piece['name']}")
        tell("pieces", f"training {piece['name']} (frames {piece['trainFirst']} to {piece['trainLast']})",
             n=i + 1, of=len(said))
        piece["checkpoint"] = str(train("pieces", root, piece["name"], quick))
    return said


# -- the asset's own frame, ground and parts ----------------------------------------------------------

def asset(brief: dict, said_pieces: list[dict], tape_said: dict) -> dict:
    import numpy as np
    import torch

    data, out = SCRATCH / "data", SCRATCH / "asset"
    if done("asset"):
        return said_by("asset")
    (out / "parts").mkdir(parents=True, exist_ok=True)
    height = brief.get("cameraHeightM")
    joined = SCRATCH / "joined.pt"
    tell("frame", "levelling the reef and putting it in metres")
    run("frame", python("join_splats.py", data / "text", joined,
                        *[f"{p['checkpoint']}:{p['first']}:{p['last']}" for p in said_pieces]))
    place = SCRATCH / "place"
    placed = last_json(run("frame", python(
        "splat_place.py", joined, "-", data / "text", place, "--camera-height", height or ASSUMED_CAMERA_HEIGHT,
        *(["--camera-height-from", "given with the video"] if height else []),
        "--video", json.dumps({"name": brief["video"].get("name")}))))
    joined.unlink(missing_ok=True)
    run("frame", python("asset_frame.py", place, SCRATCH / "align-asset.json"))
    baked = []
    for p in said_pieces:
        b = SCRATCH / f"{p['name']}-baked.pt"
        if not b.is_file():
            run("frame", python("bake_splats.py", p["checkpoint"], "-", SCRATCH / "align-asset.json", b,
                                SCRATCH / "align-baked.json"))
        baked.append(b)
    tell("surface", "the ground the splats stand on")
    surface = last_json(run("surface", python("splat_surface.py", SCRATCH / "align-baked.json", out, *baked)))
    (SCRATCH / "identity.json").write_text(json.dumps({"matrix": np.eye(4).tolist(), "dz": 0.0}))
    parts = []
    code = grut_copy()
    for i, (p, b) in enumerate(zip(said_pieces, baked)):
        t = SCRATCH / f"{p['name']}-trimmed.pt"
        trimmed = last_json(run("trim", python("trim_splats.py", b, t, SCRATCH / "identity.json", out,
                                               "--translate", "0,0,0")))
        ck = torch.load(t, map_location="cpu", weights_only=False)
        n = int(ck["positions"].shape[0])
        if n > MOST_SPLATS:
            # The faintest go: a part has to stay under what USD reads.
            keep = torch.argsort(ck["density"][:, 0].detach(), descending=True)[:MOST_SPLATS].sort().values
            with torch.no_grad():
                for key in ("positions", "rotation", "scale", "density", "features_albedo", "features_specular"):
                    if ck.get(key) is not None and ck[key].numel():
                        ck[key] = torch.nn.Parameter(ck[key].detach()[keep].contiguous(), requires_grad=True)
            torch.save(ck, t)
            tell("trim", f"{p['name']}: {n:,} splats, the faintest taken off to {MOST_SPLATS:,}")
            n = MOST_SPLATS
        del ck
        usdz = out / "parts" / f"part-{i + 1}.usdz"
        tell("parts", f"{p['name']} as NuRec splats", n=i + 1, of=len(said_pieces))
        run("parts", [sys.executable, "-m", "threedgrut.export.scripts.export_usd", "--checkpoint", t,
                      "--output", usdz, "--format", "nurec", "--no-cameras", "--no-background", "--half",
                      "--no-transform"], cwd=code, lines=False)
        shutil.move(str(t), out / "parts" / f"part-{i + 1}.pt")
        b.unlink(missing_ok=True)
        parts.append({"part": f"parts/part-{i + 1}.usdz", "checkpoint": f"parts/part-{i + 1}.pt",
                      "first": p["first"], "last": p["last"], "splats": n, "trimmed": trimmed})
    align = json.loads((SCRATCH / "align-baked.json").read_text())
    (out / "path.json").write_text(json.dumps({k: align[k] for k in ("frames", "focalMm", "apertureMm", "image")}
                                              | {"frame": "the reconstruction's own"}, indent=1))
    said = {"parts": parts, "placed": placed, "surface": surface,
            "scale": json.loads((place / "patch" / "patch.json").read_text())["scale"]}
    mark("asset", said)
    return said


# -- what the frames show ------------------------------------------------------------------------------

def cover(images: pathlib.Path, most: int = 60) -> dict:
    import numpy as np
    import torch
    import yaml
    from PIL import Image
    from transformers import SegformerForSemanticSegmentation

    if done("cover"):
        return said_by("cover")
    groups_of = yaml.safe_load(COVER_GROUPS.read_text())["groups"]
    model_dir = MODELS / "coralscapes"
    model = SegformerForSemanticSegmentation.from_pretrained(model_dir).cuda().eval().half()
    where = {label: g for g, labels in groups_of.items() for label in labels}
    names = list(groups_of)
    lookup = np.full(max(model.config.id2label) + 1, names.index("not_seabed"))
    for i, label in model.config.id2label.items():
        if label in where:
            lookup[int(i)] = names.index(where[label])
    pre = json.loads((model_dir / "preprocessor_config.json").read_text())
    mean = torch.tensor(pre.get("image_mean", [0.485, 0.456, 0.406])).view(1, 3, 1, 1).cuda().half()
    std = torch.tensor(pre.get("image_std", [0.229, 0.224, 0.225])).view(1, 3, 1, 1).cuda().half()
    files = sorted(images.glob("*.jpg"))
    files = files[::max(1, len(files) // most)]
    counts = np.zeros(len(names))
    with torch.no_grad():
        for f in files:
            rgb = Image.open(f).convert("RGB")
            W, H = rgb.size
            x = torch.from_numpy(np.asarray(rgb.resize((1024, int(1024 * H / W / 32 + 0.5) * 32)), dtype=np.float32) / 255.0)
            label = model(pixel_values=((x.permute(2, 0, 1)[None].cuda().half()) - mean) / std).logits.argmax(1)[0]
            counts += np.bincount(lookup[label.cpu().numpy().ravel()], minlength=len(names))
    seabed = counts.sum() - counts[names.index("not_seabed")]
    shares = {n: round(float(counts[i] / seabed), 4) for i, n in enumerate(names) if n != "not_seabed"} if seabed else {}
    said = {"kind": "derived", "from": f"CoralscapesV2 SegFormer on {len(files)} of the video's frames, "
                                       "share of the seabed pixels by ml/cover's groups",
            "frames": len(files), "shares": shares}
    mark("cover", said)
    del model
    torch.cuda.empty_cache()
    return said


def previews(out: pathlib.Path, images: pathlib.Path, parts: list[dict]) -> list[str]:
    """A picture from above of what was rebuilt, with the swim over it, and a
    few of the video's frames along it."""
    import numpy as np
    import torch
    from PIL import Image, ImageDraw

    SH_C0 = 0.28209479177387814
    xy, rgb, z = [], [], []
    for p in parts:
        ck = torch.load(out / p["checkpoint"], map_location="cpu", weights_only=False)
        pos = ck["positions"].detach().float().numpy()
        alpha = torch.sigmoid(ck["density"].detach().float()).numpy()[:, 0]
        keep = alpha > 0.3
        xy.append(pos[keep, :2])
        z.append(pos[keep, 2])
        rgb.append(np.clip(0.5 + SH_C0 * ck["features_albedo"].detach().float().numpy()[keep], 0, 1))
        del ck
    xy, z, rgb = np.concatenate(xy), np.concatenate(z), np.concatenate(rgb)
    lo, hi = np.percentile(xy, 0.2, axis=0), np.percentile(xy, 99.8, axis=0)
    cell = max(0.02, float((hi - lo).max()) / 2400)
    w, h = (np.ceil((hi - lo) / cell).astype(int) + 1)
    ij = ((xy - lo) / cell).astype(int)
    inside = (ij[:, 0] >= 0) & (ij[:, 0] < w) & (ij[:, 1] >= 0) & (ij[:, 1] < h)
    ij, z, rgb = ij[inside], z[inside], rgb[inside]
    order = np.argsort(z)                                         # the highest last, so it is the one kept
    image = np.full((h, w, 3), 0.08)
    image[h - 1 - ij[order, 1], ij[order, 0]] = rgb[order]
    picture = Image.fromarray((image * 255).astype(np.uint8))
    path = json.loads((out / "path.json").read_text())["frames"]
    draw = ImageDraw.Draw(picture)
    pts = [((f["eye"][0] - lo[0]) / cell, h - 1 - (f["eye"][1] - lo[1]) / cell) for f in path]
    draw.line(pts, fill=(255, 210, 60), width=max(2, w // 600))
    r = max(4, w // 250)
    draw.ellipse([pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r], fill=(80, 255, 120))
    picture.save(out / "preview.jpg", quality=88)
    (out / "previews").mkdir(exist_ok=True)
    files = sorted(images.glob("*.jpg"))
    named = []
    for k, f in enumerate(files[::max(1, len(files) // 6)][:6]):
        one = Image.open(f).convert("RGB")
        one.thumbnail((640, 640))
        one.save(out / "previews" / f"frame-{k + 1}.jpg", quality=85)
        named.append(f"previews/frame-{k + 1}.jpg")
    return named


# -- the whole of it ----------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    quick = brief.get("effort") == "quick"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "logs").mkdir(exist_ok=True)
    # The image's root is read-only; whatever a library caches or compiles goes here.
    home = SCRATCH / "home"
    home.mkdir(exist_ok=True)
    os.environ.update(HOME=str(home), TMPDIR=str(SCRATCH / "tmp"), TORCH_HOME=str(MODELS / "torch"),
                      TORCH_EXTENSIONS_DIR=str(SCRATCH / "torch-extensions"), HF_HUB_OFFLINE="1",
                      TRANSFORMERS_OFFLINE="1", MPLCONFIGDIR=str(home / "matplotlib"),
                      PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    (SCRATCH / "tmp").mkdir(exist_ok=True)
    timings = {}

    def timed(name, fn, *args):
        t = time.time()
        result = fn(*args)
        timings[name] = round(time.time() - t)
        return result

    try:
        frames_said = timed("frames", frames, brief)
        cameras_said = timed("cameras", cameras, brief, frames_said)
        tape_said = timed("tape", tape, brief, quick)
        pieces_said = timed("pieces", pieces, quick)
        asset_said = timed("asset", asset, brief, pieces_said, tape_said)
        out = SCRATCH / "asset"
        originals = SCRATCH / "frames-undistorted"
        if not originals.is_dir():
            originals = SCRATCH / "data" / "images"
        tell("cover", "what the frames show")
        cover_said = timed("cover", cover, originals)
        tell("package", "a picture from above and a few frames")
        shown = previews(out, SCRATCH / "data" / "images", asset_said["parts"])
    except Exception as failed:
        traceback.print_exc()
        tell("failed", str(failed)[:2000])
        return 1

    import numpy as np

    path = json.loads((out / "path.json").read_text())["frames"]
    eyes = np.array([f["eye"] for f in path])
    travel = eyes[-1, :2] - eyes[0, :2]
    surface = json.loads((out / "surface.json").read_text())
    manifest = {
        "name": brief.get("label") or brief.get("name") or pathlib.Path(brief["video"].get("name", "video")).stem,
        "label": brief.get("label", ""),
        "kind": "gaussian-splats",
        "frame": "the reconstruction's own: metres, z up, the origin at the reef's centre on its own ground, "
                 "x along the reef's long axis; mapping it onto a place is a separate step",
        "video": frames_said["video"], "frames": frames_said["frames"], "every": frames_said["every"],
        "registered": cameras_said["registered"],
        "pieces": [{k: p[k] for k in ("part", "checkpoint", "first", "last", "splats")} for p in asset_said["parts"]],
        "trimmed": [p["trimmed"] for p in asset_said["parts"]],
        "extentM": asset_said["placed"].get("extentM"),
        "scale": asset_said["scale"],
        "surface": {"file": "surface.f32", "meta": "surface.json", "rows": surface["rows"],
                    "columns": surface["columns"], "cellM": surface["cellM"], "origin": surface["origin"]},
        "path": "path.json", "pathLengthM": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).sum()), 1),
        "start": brief.get("start"),
        "startEye": [round(float(v), 3) for v in eyes[0]],
        "headingDeg": round(math.degrees(math.atan2(travel[0], travel[1])) % 360, 1),
        "cover": cover_said, "tape": tape_said,
        "preview": "preview.jpg", "previews": shown,
        "effort": "quick" if quick else "full",
        "made": {"tool": "COLMAP global mapper, 3DGRUT 3DGUT, iocean ml/splat", "recipe": "reconstruct-video/v1",
                 "seconds": round(time.time() - started), "timings": timings},
    }
    (out / "reconstruction.json").write_text(json.dumps(manifest, indent=1))
    tell("package", "packing the reconstruction")
    with tarfile.open(OUTPUTS / "reconstruction.tar", "w") as archive:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                archive.add(f, arcname=str(f.relative_to(out)))
    if SCRATCH.is_relative_to(OUTPUTS) and not os.environ.get("IOCEAN_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    tell("done", f"{manifest['name']}: {len(manifest['pieces'])} pieces, {sum(p['splats'] for p in manifest['pieces']):,} "
                 f"splats, {manifest['pathLengthM']} m of swim",
         seconds=manifest["made"]["seconds"], registered=manifest["registered"], extentM=manifest["extentM"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
