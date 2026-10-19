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


def needs_of(said: dict | None) -> dict:
    said = said or {}
    needs = {}
    if said.get("gpu_memory"):
        needs["gpuMemoryBytes"] = bytes_of(said["gpu_memory"])
    if said.get("cpu"):
        needs["cpu"] = float(said["cpu"])
    if said.get("memory"):
        needs["memoryBytes"] = bytes_of(said["memory"])
    if said.get("gpu") or needs.get("gpuMemoryBytes"):
        needs["gpu"] = True
    return needs


def catalogue(brief: dict, src: pathlib.Path) -> list[dict]:
    """The controllers in the source, each {slug, name, controller ("file.py:Class",
    or "" to be found), rate, needs, requirements}:

      the brief's own controller          one, as the brief says
      iocean.toml with [[controller]]     each entry (a repository of several)
      folders holding a controller.py     each, named after its folder
      iocean.toml with controller = ...   one, as before
      nothing said                        the one Controller subclass found
    """
    toml = {}
    if (src / "iocean.toml").is_file():
        try:
            toml = tomllib.loads((src / "iocean.toml").read_text())
        except tomllib.TOMLDecodeError as bad:
            raise Refused(f"iocean.toml does not read: {bad}") from None
    rate = float(brief.get("rateHz") or toml.get("rate") or 20.0)

    def requirements_for(entry: str) -> pathlib.Path | None:
        folder = (src / entry.split(":")[0]).parent if entry else src
        for where in (folder, src):
            if (where / "requirements.txt").is_file():
                return where / "requirements.txt"
        return None

    def one(slug, name, entry, needs, r):
        return {"slug": slug or "", "name": name or "", "controller": entry or "", "rate": float(r or rate),
                "needs": needs_of(needs), "requirements": requirements_for(entry or "")}

    if brief.get("controller"):
        return [one(brief.get("slug"), brief.get("name"), brief["controller"], toml.get("needs"), None)]
    listed = toml.get("controller")
    found: list[dict] = []
    if isinstance(listed, list):
        for c in listed:
            if not isinstance(c, dict) or not c.get("entry"):
                raise Refused("every [[controller]] in iocean.toml needs an entry = \"file.py:Class\"")
            found.append(one(c.get("slug"), c.get("name"), c["entry"], c.get("needs"), c.get("rate")))
    folders = sorted(p for p in (src / "controllers").glob("*/controller.py")) if (src / "controllers").is_dir() else []
    named = {f["controller"].split(":")[0] for f in found}
    for f in folders:
        rel = f.relative_to(src).as_posix()
        if rel not in named:
            folder_toml = {}
            if (f.parent / "iocean.toml").is_file():
                folder_toml = tomllib.loads((f.parent / "iocean.toml").read_text())
            found.append(one(folder_toml.get("slug") or f.parent.name, folder_toml.get("name"),
                             folder_toml.get("controller") and f"{f.parent.relative_to(src).as_posix()}/{folder_toml['controller']}" or rel,
                             folder_toml.get("needs"), folder_toml.get("rate")))
    if found:
        wanted = brief.get("controllers")
        if wanted:
            found = [f for f in found if f["slug"] in wanted]
            if not found:
                raise Refused("none of the controllers asked for is in the source")
        return found
    if isinstance(listed, str):
        return [one(brief.get("slug") or toml.get("slug"), brief.get("name") or toml.get("name"), listed,
                    toml.get("needs"), toml.get("rate"))]
    return [one(brief.get("slug") or toml.get("slug"), brief.get("name") or toml.get("name"), "",
                toml.get("needs"), toml.get("rate"))]


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

def build_one(c: dict, src: pathlib.Path, said: dict, deps_cache: dict) -> dict:
    """One controller: its packages, its checks, its image. A report of it."""
    out: dict = {"ok": False, "checks": {}, "slug": c["slug"], "name": c["name"]}
    try:
        deps = SCRATCH / "deps" / (c["slug"] or "one")
        req = c["requirements"]
        if req is not None:
            key = req.read_bytes()
            if key in deps_cache:
                deps = deps_cache[key]
            else:
                shutil.rmtree(deps, ignore_errors=True)
                deps.mkdir(parents=True)
                tell("packages", f"{c['slug'] or 'the controller'}: installing {req.relative_to(src).as_posix()}")
                run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
                     "--target", deps, "-r", req], timeout=1800, env={"PIP_NO_INPUT": "1"})
                deps_cache[key] = deps
        extra = [SDK, deps, src]

        found = python(FIND, src, SDK, deps, c["controller"], timeout=120, extra=extra)
        if found.get("refused"):
            raise Refused(found["refused"])
        slug = c["slug"] or re.sub(r"[^a-z0-9]+", "-", pathlib.Path(found["controller"].split(":")[0]).stem.lower()).strip("-")
        if not SLUG.match(slug):
            raise Refused(f"{slug!r} is not a usable slug: lower case letters, digits and dashes, 2 to 63")
        name = c["name"] or found["controller"].split(":")[1]
        out.update(controller=found["controller"], vehicle=found["vehicle"], commands=found["commands"], slug=slug, name=name)
        out["checks"]["vehicle"] = {"ok": not found["problems"], "problems": found["problems"]}
        tell("check", f"{slug}: {found['controller']} flies the {found['vehicle']}"
             if not found["problems"] else f"{slug}: cannot fly the {found['vehicle']}: " + "; ".join(found["problems"]))
        if found["problems"]:
            raise Refused("it cannot fly the vehicle it was written for: " + "; ".join(found["problems"]))

        file, _, cls = found["controller"].partition(":")
        try:
            tank = python(TANK, f"{src / file}:{cls}", SDK, deps, TANK_SECONDS, timeout=TANK_TIMEOUT, extra=extra)
        except subprocess.TimeoutExpired:
            raise Refused(f"it did not finish {TANK_SECONDS:.0f} s in the tank within {TANK_TIMEOUT} s") from None
        score = tank["score"]
        score = round(score, 4) if isinstance(score, (int, float)) and score == score else None
        out["checks"]["tank"] = {"ok": True, "seconds": round(tank["seconds"], 1), "score": score,
                                 "said": tank["said"], "wallSeconds": tank["wall"]}
        tell("check", f"{slug}: the tank: {tank['said']}")

        out["subscribes"] = ["/depth", "/imu/data"] + (["/dvl/twist"] if "dvl" in found["carries"] else [])
        out["publishes"] = ["/cmd_vel" if found["commands"] == "wrench" else "/thruster_cmd"]
        out["needs"] = c["needs"]
        out["wantsGpu"] = bool(c["needs"].get("gpu"))

        layers = [(*oci.layer_of(oci.files_under(SDK / "iocean", "/opt/coral_city_sdk/iocean")
                                 + oci.files_under(src, "/opt/controller/source")), "the SDK and the controller's source")]
        if deps.is_dir() and any(deps.iterdir()):
            layers.append((*oci.layer_of(oci.files_under(deps, "/opt/controller/packages")), "its Python packages"))
        built = oci.assemble(
            BASE, SCRATCH / "layout", layers,
            env={"PYTHONPATH": "/opt/coral_city_sdk:/opt/controller/packages:/opt/controller/source", "PYTHONUNBUFFERED": "1"},
            entrypoint=["/bin/bash", "-lc", "source /opt/ros/jazzy/setup.bash && exec python3 -m iocean.ros "
                        f"/opt/controller/source/{file}:{cls} --rate {c['rate']:g}"],
            labels={"io.iocean.controller": found["controller"], "io.iocean.slug": slug,
                    **({"io.iocean.commit": said["commit"]} if said.get("commit") else {})},
            tag=slug)
        out.update(imageDigest=built["digest"], layers=built["layers"], sizeBytes=built["sizeBytes"],
                   image=slug, ok=True)
        out["_built"] = built
        tell("image", f"{slug}: {built['layers']} layers, {built['sizeBytes'] / 2 ** 20:.0f} MB", digest=built["digest"])
    except Refused as why:
        out["failure"] = str(why)
        tell("check", f"{out.get('slug') or 'a controller'}: refused: {why}"[:2000])
    except subprocess.TimeoutExpired as late:
        out["failure"] = f"it took too long: {late}"
    return out


def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "home").mkdir(exist_ok=True)
    os.environ.update(HOME=str(SCRATCH / "home"), TMPDIR=str(SCRATCH))
    report: dict = {"ok": False, "controllers": []}
    try:
        src, said = source(brief)
        report["source"] = {k: said.get(k) for k in ("kind", "url", "ref", "commit", "path", "objectId", "name") if said.get(k)}
        listed = catalogue(brief, src)
        tell("find", f"{len(listed)} controller{'s' if len(listed) != 1 else ''}"
             + (": " + ", ".join(c["slug"] for c in listed if c["slug"]) if any(c["slug"] for c in listed) else ""),
             controllers=len(listed))
        cache: dict = {}
        for i, c in enumerate(listed):
            tell("controller", f"{c['slug'] or 'the controller'}", n=i + 1, of=len(listed))
            report["controllers"].append(build_one(c, src, said, cache))
        slugs = [c["slug"] for c in report["controllers"] if c.get("slug")]
        if len(slugs) != len(set(slugs)):
            raise Refused("two controllers have the same slug: " + ", ".join(sorted({s for s in slugs if slugs.count(s) > 1})))
        report["ok"] = any(c["ok"] for c in report["controllers"])
        if not report["ok"]:
            report["failure"] = "no controller in the source could be built: " + "; ".join(
                f"{c.get('slug') or '?'}: {c.get('failure')}" for c in report["controllers"])
    except Refused as why:
        report["failure"] = str(why)
        tell("failed", str(why)[:2000])
    except Exception as failed:
        traceback.print_exc()
        report["failure"] = f"the build broke: {failed}"
        tell("failed", report["failure"][:2000])
    report["seconds"] = round(time.time() - started)
    built = [c.pop("_built") for c in report["controllers"] if "_built" in c]
    (OUTPUTS / "report.json").write_text(json.dumps(report, indent=1))
    # Every declared output must exist or the worker fails the job and the
    # report saying why is lost. images.oci.tar is one OCI layout holding
    # every controller built, each named by its slug in index.json and
    # sharing the base's blobs; it is an empty tar when none was built.
    import tarfile
    if built:
        oci.finish(SCRATCH / "layout", built)
        oci.tar_layout(SCRATCH / "layout", OUTPUTS / "images.oci.tar")
    else:
        with tarfile.open(OUTPUTS / "images.oci.tar", "w"):
            pass
    if SCRATCH.is_relative_to(OUTPUTS) and not os.environ.get("IOCEAN_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    built = [c for c in report["controllers"] if c.get("ok")]
    tell("done" if report["ok"] else "failed",
         f"{len(built)} of {len(report['controllers'])} built" + (": " + ", ".join(c["slug"] for c in built) if built else "")
         if report["controllers"] else report.get("failure", "nothing built"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
