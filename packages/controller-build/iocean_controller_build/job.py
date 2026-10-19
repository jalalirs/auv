"""A controller built from its source, as the platform runs it.

    python3 -m iocean_controller_build.job '<brief>'

The brief (services/control-plane/internal/controllerbuild):

    {"source": {"kind": "zip", "path": "source/our.zip", "objectId", "name"}
             | {"kind": "git", "url": "https://github.com/owner/repo", "ref": "main", "path": "sub/folder"},
     "slug": "...", "name": "...", "controller": "file.py:Class", "rateHz": 20}

The source may say what it is in an iocean.toml at its root:

    controller = "hold.py:DepthHold"     # else the one Controller subclass found
    name = "Depth hold"
    slug = "depth-hold"
    rate = 20
    [needs]
    gpu = true
    gpu_memory = "8G"
    cpu = 2
    memory = "4G"

and its Python packages in a requirements.txt, installed beside it.

What it does, each step said as {"progress": {...}} on stdout:

  source    the zip unpacked, or the repository cloned at its ref (the commit
            recorded)
  find      the controller: the brief's, the toml's, or the one subclass
  packages  requirements.txt installed into a folder of its own
  check     the SDK's own check that it can fly the vehicle it was written
            for, then a short run in the SDK's tank (the runtime's physics,
            headless): it must start, answer every tick and not raise
  image     the image assembled on the ROS 2 base (oci.py): the SDK and the
            source in one layer, its packages in another; the same command
            `iocean deploy` gives it
  report    report.json, and image.oci.tar when every check passed

The image is registered by the control plane, which can reach the platform's
registry; this job reaches nothing but the source's host and the package
index.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import tomllib
import traceback
import zipfile

from . import oci

INPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_INPUTS", "/work/inputs"))
OUTPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_OUTPUTS", "/work/outputs"))
SCRATCH = pathlib.Path(os.environ.get("IOCEAN_JOB_SCRATCH") or OUTPUTS / "scratch")
SDK = pathlib.Path(os.environ.get("IOCEAN_SDK", "/opt/iocean/sdk"))
RUNTIME = pathlib.Path(os.environ.get("IOCEAN_RUNTIME", "/opt/iocean/runtime"))
BASE = pathlib.Path(os.environ.get("IOCEAN_CONTROLLER_BASE", "/opt/iocean/base-oci"))

TANK_SECONDS = 20.0
TANK_TIMEOUT = 180
MOST_UNPACKED = 2 << 30
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class Refused(Exception):
    """The source cannot be built, for a reason its owner can act on."""


def tell(step: str, say: str, **detail) -> None:
    print(json.dumps({"progress": {"step": step, "say": say, **detail}}), flush=True)


def run(argv: list, *, cwd: pathlib.Path | None = None, timeout: int = 900, env: dict | None = None) -> str:
    done = subprocess.run([str(a) for a in argv], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(env or {})})
    if done.returncode != 0:
        said = (done.stderr.strip() or done.stdout.strip()).splitlines()[-12:]
        raise Refused(f"{pathlib.Path(str(argv[0])).name} {argv[1] if len(argv) > 1 else ''} failed: " + " | ".join(said))
    return done.stdout


# -- the source -------------------------------------------------------------------------------------

def unzip(archive: pathlib.Path, into: pathlib.Path) -> None:
    """Unpacked within itself: no absolute paths, no climbing out, no links,
    and no more than MOST_UNPACKED."""
    total = 0
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            target = (into / name).resolve()
            if name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts or not target.is_relative_to(into.resolve()):
                raise Refused(f"the zip names a file outside itself: {name}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise Refused(f"the zip holds a link, which a controller's source does not need: {name}")
            total += info.file_size
            if total > MOST_UNPACKED:
                raise Refused("the zip unpacks to more than 2 GB")
        z.extractall(into)
    # A zip of a folder: its one top folder is the source.
    entries = [p for p in into.iterdir() if p.name not in ("__MACOSX",)]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for p in inner.iterdir():
            shutil.move(str(p), into / p.name)
        inner.rmdir()


def source(brief: dict) -> tuple[pathlib.Path, dict]:
    said = dict(brief["source"])
    src = SCRATCH / "src"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    if said["kind"] == "zip":
        tell("source", f"unpacking {said.get('name') or 'the zip'}")
        unzip(INPUTS / said["path"], src)
    elif said["kind"] == "git":
        url, ref = said["url"], said.get("ref") or ""
        if not re.match(r"^https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+?(\.git)?/?$", url):
            raise Refused("only a public GitHub repository, https://github.com/owner/repo, can be built from")
        tell("source", f"cloning {url}" + (f" at {ref}" if ref else ""))
        env = {"GIT_TERMINAL_PROMPT": "0", "HOME": str(SCRATCH / "home")}
        if ref and not re.fullmatch(r"[0-9a-f]{7,40}", ref):
            run(["git", "clone", "--depth", "1", "--branch", ref, url, src], env=env, timeout=600)
        else:
            run(["git", "clone", "--depth", "50", url, src], env=env, timeout=600)
            if ref:
                run(["git", "checkout", "--quiet", ref], cwd=src, env=env)
        said["commit"] = run(["git", "rev-parse", "HEAD"], cwd=src, env=env).strip()
        shutil.rmtree(src / ".git", ignore_errors=True)
        tell("source", f"at commit {said['commit'][:12]}", commit=said["commit"])
    else:
        raise Refused(f"no source of kind {said['kind']!r}")
    # For git, "path" is the folder within the repository; for a zip it is
    # where the upload was staged, and the zip's own top folder is the source.
    sub = (said.get("path") or "").strip("/") if said["kind"] == "git" else ""
    if sub:
        if ".." in pathlib.PurePosixPath(sub).parts:
            raise Refused("the folder may not climb out of the source")
        src = src / sub
        if not src.is_dir():
            raise Refused(f"the source has no folder {sub}")
    return src, said


# -- what it is -----------------------------------------------------------------------------------

def bytes_of(said) -> int:
    if isinstance(said, (int, float)):
        return int(said)
    m = re.fullmatch(r"\s*([0-9.]+)\s*([KMGT]?)i?B?\s*", str(said), re.I)
    if not m:
        raise Refused(f"cannot read {said!r} as a size (say 8G or 512M)")
    return int(float(m.group(1)) * 1024 ** "_KMGT".index(m.group(2).upper() or "_"))


def described(brief: dict, src: pathlib.Path) -> dict:
    toml = {}
    if (src / "iocean.toml").is_file():
        try:
            toml = tomllib.loads((src / "iocean.toml").read_text())
        except tomllib.TOMLDecodeError as bad:
            raise Refused(f"iocean.toml does not read: {bad}") from None
    needs_said = toml.get("needs") or {}
    needs = {}
    if needs_said.get("gpu_memory"):
        needs["gpuMemoryBytes"] = bytes_of(needs_said["gpu_memory"])
    if needs_said.get("cpu"):
        needs["cpu"] = float(needs_said["cpu"])
    if needs_said.get("memory"):
        needs["memoryBytes"] = bytes_of(needs_said["memory"])
    if needs_said.get("gpu") or needs.get("gpuMemoryBytes"):
        needs["gpu"] = True
    return {"controller": brief.get("controller") or toml.get("controller") or "",
            "name": brief.get("name") or toml.get("name") or "",
            "slug": brief.get("slug") or toml.get("slug") or "",
            "rate": float(brief.get("rateHz") or toml.get("rate") or 20.0), "needs": needs}


FIND = r'''
import inspect, json, pathlib, sys
sys.path[:0] = [sys.argv[2], sys.argv[3]]
from iocean.controller import Controller
from iocean.loading import controller_from
src, spec = pathlib.Path(sys.argv[1]), sys.argv[4]
if not spec:
    found = []
    for f in sorted(src.rglob("*.py")):
        rel = f.relative_to(src)
        if any(p.startswith(".") or p in ("tests", "test", "__pycache__") for p in rel.parts) or f.name.startswith("test_"):
            continue
        text = f.read_text(errors="replace")
        if "Controller" not in text:
            continue
        try:
            cls = controller_from(str(f))
        except SystemExit as said:
            if "several" in str(said):
                print(json.dumps({"refused": f"{rel} defines several controllers; name one in iocean.toml (controller = \"{rel}:Name\")"})); sys.exit(0)
            continue
        except Exception:
            continue
        found.append(f"{rel}:{cls.__name__}")
    if len(found) != 1:
        print(json.dumps({"refused": "no Controller subclass in the source" if not found else
                          f"several controllers ({', '.join(found)}); name one in iocean.toml"})); sys.exit(0)
    spec = found[0]
file, _, name = spec.partition(":")
cls = controller_from(f"{src / file}:{name}" if name else str(src / file))
controller = cls()
vehicle = controller.described
problems = vehicle.check(cls)
print(json.dumps({"controller": f"{file}:{cls.__name__}", "vehicle": vehicle.name, "slugOfVehicle": cls.vehicle,
                  "commands": cls.commands, "carries": list(vehicle.carries), "problems": problems}))
'''

TANK = r'''
import json, sys, time
sys.path[:0] = [sys.argv[2], sys.argv[3]]
from iocean.loading import controller_from
from iocean.tank import Tank
cls = controller_from(sys.argv[1])
started = time.time()
report = Tank(cls.vehicle, seconds=float(sys.argv[4])).run(cls())
print(json.dumps({"score": report.score if report.score == report.score else None, "seconds": report.seconds, "said": str(report),
                  "wall": round(time.time() - started, 1)}))
'''


def python(code: str, *args, timeout: int, extra: list[pathlib.Path]) -> dict:
    env = {"PYTHONPATH": os.pathsep.join(str(p) for p in extra), "IOCEAN_RUNTIME": str(RUNTIME),
           "HOME": str(SCRATCH / "home"), "MPLCONFIGDIR": str(SCRATCH / "home")}
    out = run([sys.executable, "-c", code, *args], timeout=timeout, env=env)
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    if not lines:
        raise Refused("the check said nothing it could read")
    return json.loads(lines[-1])


# -- the whole of it ---------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "home").mkdir(exist_ok=True)
    os.environ.update(HOME=str(SCRATCH / "home"), TMPDIR=str(SCRATCH))
    report: dict = {"ok": False, "checks": {}}
    try:
        src, said = source(brief)
        report["source"] = {k: said.get(k) for k in ("kind", "url", "ref", "commit", "path", "objectId", "name") if said.get(k)}
        meta = described(brief, src)

        deps = SCRATCH / "deps"
        shutil.rmtree(deps, ignore_errors=True)
        if (src / "requirements.txt").is_file():
            tell("packages", "installing requirements.txt")
            deps.mkdir()
            run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
                 "--target", deps, "-r", src / "requirements.txt"], timeout=1800, env={"PIP_NO_INPUT": "1"})
            tell("packages", f"{sum(1 for _ in deps.iterdir())} packages installed")
        extra = [SDK, deps, src]

        tell("find", "finding the controller")
        found = python(FIND, src, SDK, deps, meta["controller"], timeout=120, extra=extra)
        if found.get("refused"):
            raise Refused(found["refused"])
        slug = meta["slug"] or re.sub(r"[^a-z0-9]+", "-", pathlib.Path(found["controller"].split(":")[0]).stem.lower()).strip("-")
        if not SLUG.match(slug):
            raise Refused(f"{slug!r} is not a usable slug: lower case letters, digits and dashes, 2 to 63")
        name = meta["name"] or found["controller"].split(":")[1]
        report.update(controller=found["controller"], vehicle=found["vehicle"], commands=found["commands"],
                      slug=slug, name=name)
        report["checks"]["vehicle"] = {"ok": not found["problems"], "problems": found["problems"]}
        tell("check", f"{found['controller']} flies the {found['vehicle']}"
             if not found["problems"] else f"{found['controller']} cannot fly the {found['vehicle']}: " + "; ".join(found["problems"]))
        if found["problems"]:
            raise Refused("it cannot fly the vehicle it was written for: " + "; ".join(found["problems"]))

        tell("check", f"{TANK_SECONDS:.0f} s in the tank")
        file, _, cls = found["controller"].partition(":")
        try:
            tank = python(TANK, f"{src / file}:{cls}", SDK, deps, TANK_SECONDS, timeout=TANK_TIMEOUT, extra=extra)
        except subprocess.TimeoutExpired:
            raise Refused(f"it did not finish {TANK_SECONDS:.0f} s in the tank within {TANK_TIMEOUT} s") from None
        score = tank["score"]
        # No task in the tank, no score: null, not NaN, which JSON cannot say.
        score = round(score, 4) if isinstance(score, (int, float)) and score == score else None
        report["checks"]["tank"] = {"ok": True, "seconds": round(tank["seconds"], 1), "score": score,
                                    "said": tank["said"], "wallSeconds": tank["wall"]}
        tell("check", f"the tank: {tank['said']}")

        # What it will use, from the vehicle it was written for (as `iocean deploy` says it).
        report["subscribes"] = ["/depth", "/imu/data"] + (["/dvl/twist"] if "dvl" in found["carries"] else [])
        report["publishes"] = ["/cmd_vel" if found["commands"] == "wrench" else "/thruster_cmd"]
        report["needs"] = meta["needs"]
        report["wantsGpu"] = bool(meta["needs"].get("gpu"))

        tell("image", "assembling the image on the ROS 2 base")
        layers = [(*oci.layer_of(oci.files_under(SDK / "iocean", "/opt/coral_city_sdk/iocean")
                                 + oci.files_under(src, "/opt/controller/source")), "the SDK and the controller's source")]
        if deps.is_dir() and any(deps.iterdir()):
            layers.append((*oci.layer_of(oci.files_under(deps, "/opt/controller/packages")), "its Python packages"))
        built = oci.assemble(
            BASE, SCRATCH / "image",
            [(packed, diff_id, what) for packed, diff_id, what in layers],
            env={"PYTHONPATH": "/opt/coral_city_sdk:/opt/controller/packages:/opt/controller/source",
                 "PYTHONUNBUFFERED": "1"},
            entrypoint=["/bin/bash", "-lc", "source /opt/ros/jazzy/setup.bash && exec python3 -m iocean.ros "
                        f"/opt/controller/source/{file}:{cls} --rate {meta['rate']:g}"],
            labels={"io.iocean.controller": found["controller"], "io.iocean.slug": slug,
                    **({"io.iocean.commit": said["commit"]} if said.get("commit") else {})},
            tag=slug)
        oci.tar_layout(SCRATCH / "image", OUTPUTS / "image.oci.tar")
        report.update(imageDigest=built["digest"], layers=built["layers"], sizeBytes=built["sizeBytes"], ok=True)
        tell("image", f"{built['layers']} layers, {built['sizeBytes'] / 2 ** 20:.0f} MB", digest=built["digest"])
    except Refused as why:
        report["failure"] = str(why)
        tell("failed", str(why)[:2000])
    except Exception as failed:
        traceback.print_exc()
        report["failure"] = f"the build broke: {failed}"
        tell("failed", report["failure"][:2000])
    report["seconds"] = round(time.time() - started)
    (OUTPUTS / "report.json").write_text(json.dumps(report, indent=1))
    if not report["ok"]:
        # Every declared output must exist or the worker fails the job and
        # the report saying why is lost; an empty tar stands for no image.
        import tarfile
        with tarfile.open(OUTPUTS / "image.oci.tar", "w"):
            pass
    if SCRATCH.is_relative_to(OUTPUTS) and not os.environ.get("IOCEAN_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    if report["ok"]:
        tell("done", f"{report['name']} built: {report['controller']}, {report['checks']['tank']['said']}",
             digest=report["imageDigest"])
        return 0
    # A source that cannot be built is still a finished build: its report
    # says why, and the job succeeds so the report is collected.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
